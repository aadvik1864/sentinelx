from collections import Counter
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event as sqlalchemy_event

from app.api import dashboard as dashboard_api
from app.models import Event


def test_empty_dashboard_has_zero_counts_and_full_chart(client, tokens):
    response = client.get("/api/v1/dashboard", headers=tokens["viewer"])
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["total_events"] == metrics["unique_source_ips"] == 0
    assert metrics["events_per_second"] == 0
    assert metrics["top_ips"] == metrics["event_types"] == []
    assert len(metrics["activity"]) == 25
    assert all(row["events"] == 0 for row in metrics["activity"])


def test_dashboard_rollups_match_independent_counts(client, tokens, db, monkeypatch):
    now = datetime(2026, 10, 12, 12, 34, 56)
    monkeypatch.setattr(dashboard_api, "utcnow", lambda: now)
    rows = []
    for index in range(30):
        rows.append(
            Event(
                timestamp=now - timedelta(hours=index % 27),
                source="linux",
                event_type=f"fixture-kind-{index % 9}",
                severity="low",
                source_ip=None if index % 5 == 0 else f"203.0.113.{index % 8 + 10}",
                hostname="fixture",
                message="Synthetic metric fixture",
                details={},
                created_at=now - timedelta(seconds=index * 4),
            )
        )
    # Exact rolling-window and receipt-minute boundaries, including a real null IP.
    rows.extend(
        [
            Event(
                timestamp=now - timedelta(hours=24),
                source="linux",
                event_type="boundary",
                severity="low",
                source_ip=None,
                hostname="fixture",
                message="Boundary",
                details={},
                created_at=now - timedelta(seconds=60),
            ),
            Event(
                timestamp=now - timedelta(hours=24, microseconds=1),
                source="linux",
                event_type="outside",
                severity="low",
                source_ip="203.0.113.99",
                hostname="fixture",
                message="Outside",
                details={},
                created_at=now,
            ),
        ]
    )
    db.add_all(rows)
    db.commit()
    included = [row for row in rows if row.timestamp >= now - timedelta(hours=24)]
    ips = Counter(row.source_ip for row in included if row.source_ip is not None)
    kinds = Counter(row.event_type for row in included)
    hours = Counter(str(row.timestamp)[:13] for row in included)
    metrics = client.get("/api/v1/dashboard", headers=tokens["viewer"]).json()
    assert metrics["total_events"] == len(included)
    assert metrics["unique_source_ips"] == len(ips)
    assert metrics["top_ips"] == [
        {"ip": ip, "count": count}
        for ip, count in sorted(ips.items(), key=lambda row: (-row[1], row[0]))[:5]
    ]
    assert metrics["event_types"] == [
        {"type": kind, "count": count}
        for kind, count in sorted(kinds.items(), key=lambda row: (-row[1], row[0]))[:5]
    ]
    assert sum(row["events"] for row in metrics["activity"]) == len(included)
    for row in metrics["activity"]:
        assert row["events"] == hours.get(row["timestamp"].replace("T", " ")[:13], 0)
    assert metrics["events_per_second"] == round(
        sum(row.created_at >= now - timedelta(minutes=1) for row in rows) / 60, 2
    )


def test_postgres_daily_rollups_use_one_history_scan(client, db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("GROUPING SETS optimization is PostgreSQL-only")
    queries = []

    def record(connection, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    sqlalchemy_event.listen(db.bind, "before_cursor_execute", record)
    try:
        metrics = dashboard_api.daily_event_metrics(db, datetime(2026, 10, 11))
    finally:
        sqlalchemy_event.remove(db.bind, "before_cursor_execute", record)
    assert metrics == (0, 0, {}, [], [])
    assert len(queries) == 1 and "GROUPING SETS" in queries[0]


def test_high_cardinality_groups_keep_top_lists_bounded(client, tokens, db, monkeypatch):
    now = datetime(2026, 10, 12, 12, 34, 56)
    monkeypatch.setattr(dashboard_api, "utcnow", lambda: now)
    for index in range(128):
        db.add(
            Event(
                timestamp=now,
                source="linux",
                event_type=f"kind-{index:03}",
                severity="low",
                source_ip=f"203.0.113.{index + 1}",
                hostname="fixture",
                message="High cardinality fixture",
                details={},
                created_at=now,
            )
        )
    # A large null-address group must not hide one of the top five real addresses.
    for _ in range(10):
        db.add(
            Event(
                timestamp=now,
                source="linux",
                event_type="null-address",
                severity="low",
                source_ip=None,
                hostname="fixture",
                message="Null address fixture",
                details={},
                created_at=now,
            )
        )
    db.commit()
    transferred = []

    def record_rows(connection, cursor, statement, parameters, context, executemany):
        if "GROUPING SETS" in statement:
            transferred.append(cursor.rowcount)

    sqlalchemy_event.listen(db.bind, "after_cursor_execute", record_rows)
    try:
        response = client.get("/api/v1/dashboard", headers=tokens["viewer"])
    finally:
        sqlalchemy_event.remove(db.bind, "after_cursor_execute", record_rows)
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["total_events"] == 138 and metrics["unique_source_ips"] == 128
    assert len(metrics["top_ips"]) == len(metrics["event_types"]) == 5
    assert all(row["ip"] is not None for row in metrics["top_ips"])
    assert metrics["event_types"][0] == {"type": "null-address", "count": 10}
    if db.bind.dialect.name == "postgresql":
        # One hour + total + five addresses + five kinds, not all 258 distinct groups.
        assert transferred == [12]
