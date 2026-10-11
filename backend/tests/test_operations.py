import hashlib
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Event, Incident, IncidentEvent, SourceReceipt, utcnow
from app.operations import export_audit, maintain, retention_candidates
from app.operations import main as operations_main
from tests.test_sources import connect, record


def test_retention_rejects_short_windows():
    with pytest.raises(ValueError, match="7 days"):
        retention_candidates(1)


def test_operator_writes_require_exact_database_confirmation(client, db, monkeypatch):
    before = db.query(Event).count()
    monkeypatch.setattr(
        "sys.argv",
        [
            "operations",
            "retention",
            "--days",
            "30",
            "--apply",
            "--confirm-database",
            "not-the-selected-database",
        ],
    )
    with pytest.raises(SystemExit) as error:
        operations_main()
    assert error.value.code == 2
    assert db.query(Event).count() == before


def test_retention_dry_run_preserves_data_and_protects_evidence(client, tokens, db):
    source, headers = connect(client, tokens)
    result = client.post(
        f"/api/v1/sources/{source['id']}/events", headers=headers, json=record()
    ).json()
    row = db.get(Event, result["event_id"])
    row.timestamp = row.created_at = utcnow() - timedelta(days=40)
    db.commit()
    assert maintain(db, 30)["eligible_events_in_batch"] == 1
    assert db.get(Event, row.id) is not None
    incident = Incident(title="Preserved evidence", severity="high")
    db.add(incident)
    db.flush()
    db.add(IncidentEvent(event_id=row.id, incident_id=incident.id))
    db.commit()
    assert maintain(db, 30)["eligible_events_in_batch"] == 0


def test_retention_keeps_replay_tombstones(client, tokens, db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Retention writes are PostgreSQL-only")
    source, headers = connect(client, tokens)
    payload = record()
    url = f"/api/v1/sources/{source['id']}/events"
    response = client.post(url, headers=headers, json=payload).json()
    row = db.get(Event, response["event_id"])
    row.timestamp = row.created_at = utcnow() - timedelta(days=40)
    db.commit()
    assert maintain(db, 30, apply=True)["eligible_events_in_batch"] == 1
    db.expire_all()
    assert db.get(Event, row.id) is None
    assert db.scalar(select(SourceReceipt)).event_id == response["event_id"]
    replay = client.post(url, headers=headers, json=payload)
    assert replay.status_code == 201 and replay.json() == {
        "event_id": response["event_id"],
        "duplicate": True,
    }
    assert db.scalar(select(Event)) is None
    assert client.post(url, headers=headers, json={**payload, "line": "different"}).status_code in {
        409,
        422,
    }


def test_audit_export_is_private_exclusive_and_verifiable(client, db, tmp_path):
    output = tmp_path / "audit.jsonl"
    report = export_audit(db, output, 0, "0" * 64)
    assert output.stat().st_mode & 0o077 == 0
    digest = "0" * 64
    for line in output.read_text().splitlines():
        row = json.loads(line)
        payload = json.dumps(row["entry"], sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256((digest + "\n" + payload).encode()).hexdigest()
        assert row["sha256"] == digest
    assert report["sha256"] == digest
    assert report["last_id"] == db.scalars(select(AuditLog.id).order_by(AuditLog.id.desc())).first()
    with pytest.raises(FileExistsError):
        export_audit(db, output, 0, "0" * 64)
