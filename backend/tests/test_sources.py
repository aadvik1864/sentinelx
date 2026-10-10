import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Request
from sqlalchemy import func, select

from app.api.sources import source_view
from app.core.config import Settings, get_settings
from app.core.security import token_digest
from app.models import Alert, AuditLog, Event, LogSource, SourceReceipt, utcnow
from app.services import telemetry


def connect(client, tokens, kind="linux", hostname="my-server"):
    response = client.post(
        "/api/v1/sources",
        headers=tokens["admin"],
        json={
            "name": "My server",
            "kind": kind,
            "hostname": hostname,
            "log_path": "/var/log/auth.log",
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    return result["source"], {"Authorization": f"Bearer {result['collector_key']}"}


def record(index=0, **changes):
    return {
        "record_key": f"source-record-{index:016d}",
        "line": "sshd: Failed password for alice from 203.0.113.10 port 22 ssh2",
        "timestamp": (datetime.now(UTC) - timedelta(seconds=30)).isoformat(),
        **changes,
    }


def test_source_credentials_and_permissions(client, tokens, db):
    source, key = connect(client, tokens)
    row = db.get(LogSource, source["id"])
    assert row.token_hash == token_digest(key["Authorization"].split(" ")[1])
    assert "token_hash" not in source
    assert source["status"] == "not_connected"
    for role, expected in [("admin", 200), ("analyst", 200), ("viewer", 403)]:
        response = client.get("/api/v1/sources", headers=tokens[role])
        assert response.status_code == expected
        assert "sxcol_" not in response.text
        assert row.token_hash not in response.text
    for role in ["analyst", "viewer"]:
        assert (
            client.post(
                "/api/v1/sources",
                headers=tokens[role],
                json={"name": "Denied", "kind": "linux", "hostname": "host"},
            ).status_code
            == 403
        )
        assert (
            client.patch(
                f"/api/v1/sources/{row.id}", headers=tokens[role], json={"enabled": False}
            ).status_code
            == 403
        )
        assert (
            client.post(f"/api/v1/sources/{row.id}/rotate-key", headers=tokens[role]).status_code
            == 403
        )
    assert client.get("/api/v1/events", headers=key).status_code == 401
    assert client.get("/api/v1/sources", headers=key).status_code == 401
    assert (
        client.post(
            f"/api/v1/sources/{row.id}/events", headers=tokens["admin"], json=record()
        ).status_code
        == 401
    )
    actions = list(db.scalars(select(AuditLog).where(AuditLog.action == "CREATE_LOG_SOURCE")))
    assert len(actions) == 1
    assert "sxcol_" not in json.dumps(actions[0].details)


def test_preserved_time_transactional_replay_and_filter(client, tokens, db):
    source, key = connect(client, tokens)
    other, _ = connect(client, tokens)
    payload = record()
    url = f"/api/v1/sources/{source['id']}/events"
    first = client.post(url, headers=key, json=payload)
    replay = client.post(url, headers=key, json=payload)
    assert first.status_code == replay.status_code == 201
    assert first.json()["event_id"] == replay.json()["event_id"]
    assert replay.json()["duplicate"] is True
    assert db.scalar(select(func.count()).select_from(Event)) == 1
    assert db.scalar(select(func.count()).select_from(SourceReceipt)) == 1
    row = db.get(LogSource, source["id"])
    assert row.total_events == 1
    event = db.get(Event, first.json()["event_id"])
    assert event.timestamp == datetime.fromisoformat(payload["timestamp"]).replace(tzinfo=None)
    assert event.details == {
        "invalid_user": False,
        "source_id": row.id,
        "simulated": False,
        "provenance": "collector",
    }
    assert row.last_event_timestamp == event.timestamp
    assert (
        client.post(url, headers=key, json={**payload, "line": "different content"}).status_code
        == 409
    )
    assert (
        client.post(f"/api/v1/sources/{other['id']}/events", headers=key, json=payload).status_code
        == 401
    )
    assert (
        client.get(f"/api/v1/events?source_id={row.id}", headers=tokens["analyst"]).json()["total"]
        == 1
    )
    assert (
        client.get(f"/api/v1/events?source_id={other['id']}", headers=tokens["analyst"]).json()[
            "total"
        ]
        == 0
    )


def test_pause_resume_and_rotation(client, tokens):
    source, key = connect(client, tokens)
    url = f"/api/v1/sources/{source['id']}"
    assert (
        client.post(url + "/heartbeat", headers=key, json={"state": "listening"}).status_code == 200
    )
    response = client.patch(url, headers=tokens["admin"], json={"enabled": False})
    assert response.json()["status"] == "paused"
    assert client.post(url + "/events", headers=key, json=record()).status_code == 403
    client.patch(url, headers=tokens["admin"], json={"enabled": True})
    new_key = client.post(url + "/rotate-key", headers=tokens["admin"]).json()["collector_key"]
    assert (
        client.post(url + "/heartbeat", headers=key, json={"state": "listening"}).status_code == 401
    )
    assert (
        client.post(
            url + "/heartbeat",
            headers={"Authorization": "Bearer " + new_key},
            json={"state": "listening"},
        ).status_code
        == 200
    )


@pytest.mark.parametrize("kind", ["linux", "application", "nginx"])
def test_missing_occurrence_time_is_rejected(client, tokens, kind):
    source, key = connect(client, tokens, kind=kind)
    line = "sshd: some activity" if kind == "linux" else '{"message":"Activity","http_status":200}'
    response = client.post(
        f"/api/v1/sources/{source['id']}/events",
        headers=key,
        json=record(line=line, timestamp=None),
    )
    assert response.status_code == 422


def test_json_web_redacts_query_and_application_scope(client, tokens, db):
    web, web_key = connect(client, tokens, kind="nginx")
    timestamp = datetime.now(UTC).isoformat()
    line = json.dumps(
        {
            "timestamp": timestamp,
            "ip": "203.0.113.10",
            "method": "GET",
            "path": "/signin?token=do-not-store",
            "http_status": 403,
        }
    )
    response = client.post(
        f"/api/v1/sources/{web['id']}/events",
        headers=web_key,
        json=record(line=line, timestamp=None),
    )
    assert response.status_code == 201
    event = db.get(Event, response.json()["event_id"])
    assert event.details["path"] == "/signin"
    assert "do-not-store" not in event.message
    rules = client.get("/api/v1/rules", headers=tokens["admin"]).json()["items"]
    for rule in rules:
        client.patch(
            f"/api/v1/rules/{rule['id']}",
            headers=tokens["admin"],
            json={"config": {"sources": ["linux"]}},
        )
    app, app_key = connect(client, tokens, kind="application")
    line = json.dumps(
        {
            "timestamp": timestamp,
            "event_type": "authentication_failure",
            "message": "Sign-in rejected",
            "ip": "203.0.113.10",
            "username": "alice",
        }
    )
    for index in range(12):
        response = client.post(
            f"/api/v1/sources/{app['id']}/events",
            headers=app_key,
            json=record(index, line=line, timestamp=None),
        )
        assert response.status_code == 201, response.text
    assert db.scalar(select(func.count()).select_from(Alert)) == 0


def test_concurrent_source_replay(client, tokens, db):
    source, key = connect(client, tokens)
    payload = record()

    def submit(_):
        return client.post(f"/api/v1/sources/{source['id']}/events", headers=key, json=payload)

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(submit, range(4)))
    assert all(response.status_code == 201 for response in responses)
    assert sum(not response.json()["duplicate"] for response in responses) == 1
    assert db.scalar(select(func.count()).select_from(Event)) == 1
    assert db.get(LogSource, source["id"]).total_events == 1


def test_concurrent_distinct_records_keep_correct_source_total(client, tokens, db):
    source, key = connect(client, tokens)

    def submit(index):
        return client.post(
            f"/api/v1/sources/{source['id']}/events", headers=key, json=record(index)
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(submit, range(4)))
    assert all(response.status_code == 201 for response in responses)
    assert db.scalar(select(func.count()).select_from(Event)) == 4
    db.expire_all()
    assert db.get(LogSource, source["id"]).total_events == 4


def test_source_health_and_safe_error_codes(client, tokens, db):
    source, key = connect(client, tokens)
    url = f"/api/v1/sources/{source['id']}/heartbeat"
    assert (
        client.post(
            url, headers=key, json={"state": "error", "error": "file_unavailable"}
        ).status_code
        == 200
    )
    item = client.get("/api/v1/sources", headers=tokens["admin"]).json()["items"][0]
    assert item["status"] == "error"
    assert "read permissions" in item["last_error"]
    assert (
        client.post(url, headers=key, json={"state": "error", "error": "password=leak"}).status_code
        == 422
    )
    client.post(url, headers=key, json={"state": "listening"})
    item = client.get("/api/v1/sources", headers=tokens["admin"]).json()["items"][0]
    assert item["status"] == "waiting"
    db.expire_all()
    row = db.get(LogSource, source["id"])
    row.last_heartbeat_at = utcnow() - timedelta(seconds=100)
    assert source_view(row)["status"] == "offline"
    row.last_heartbeat_at = utcnow()
    row.last_event_at = utcnow()
    assert source_view(row)["status"] == "receiving"


def test_agent_download(client, tokens):
    response = client.get("/api/v1/sources/agent", headers=tokens["analyst"])
    assert response.status_code == 200
    assert "class FileTailer" in response.text
    assert client.get("/api/v1/sources/agent", headers=tokens["viewer"]).status_code == 403


def test_live_monitoring_cannot_enable_demo():
    with pytest.raises(ValueError, match="Live monitoring requires"):
        Settings(live_monitoring=True, demo_mode=True, seed_demo=False)


def test_application_telemetry_excludes_polling_and_secrets(monkeypatch):
    monkeypatch.setattr(get_settings(), "live_monitoring", True)
    emitted = []
    monkeypatch.setattr(telemetry.logger, "info", lambda line: emitted.append(json.loads(line)))

    def request(path, method="GET"):
        return Request(
            {
                "type": "http",
                "path": path,
                "method": method,
                "headers": [],
                "query_string": b"password=private",
                "client": ("127.0.0.1", 1234),
            }
        )

    for path in ["/health/ready", "/api/v1/incidents", "/api/v1/rules", "/api/v1/auth/me"]:
        telemetry.record_request(request(path), 200)
    telemetry.record_request(request("/api/v1/sources/1/events", "POST"), 201)
    assert not emitted
    telemetry.record_request(request("/api/v1/incidents/1/notes", "POST"), 201)
    telemetry.emit_activity(
        request("/api/v1/auth/login", "POST"),
        "authentication_failure",
        "Sign-in rejected",
        username="alice",
    )
    assert len(emitted) == 2
    assert "private" not in json.dumps(emitted)
    assert emitted[1]["event_type"] == "authentication_failure"
