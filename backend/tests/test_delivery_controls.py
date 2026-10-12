from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import Alert, LogSource, NotificationOutbox, utcnow
from app.notifications import claim, deliver_once, validate_destination
from app.services.redaction import redact
from tests.test_pipeline import event, send
from tests.test_sources import connect, record


def test_outbox_commits_with_alert_and_retries_with_stable_id(client, tokens, db):
    send(client, tokens, event(event_type="privilege_escalation"))
    row = db.scalar(select(NotificationOutbox))
    assert row and row.alert_id == db.scalar(select(Alert.id))
    identifier = row.id
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(503 if len(requests) == 1 else 200)

    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        assert deliver_once(
            db, transport, "https://alerts.example/receive", "test-only-webhook-token"
        )
        db.refresh(row)
        assert row.delivered_at is None and row.last_error == "destination_rejected"
        assert not deliver_once(db, transport, "https://alerts.example/receive")
        assert deliver_once(
            db,
            transport,
            "https://alerts.example/receive",
            now=row.next_attempt_at + timedelta(seconds=1),
        )
    assert (
        requests[0].headers["Idempotency-Key"]
        == requests[1].headers["Idempotency-Key"]
        == identifier
    )
    db.refresh(row)
    assert row.attempts == 2 and row.delivered_at is not None
    assert "test-only-webhook-token" not in str(row.payload) + row.last_error


def test_outbox_leases_survive_worker_death_without_duplicate_claims(client, tokens, db):
    send(client, tokens, event(event_type="privilege_escalation"))
    now = utcnow()
    first = claim(db, "worker-one", now)
    assert first and claim(db, "worker-two", now) is None
    second = claim(db, "worker-two", now + timedelta(seconds=61))
    assert second["id"] == first["id"]


def test_postgres_outbox_claim_is_exclusive_across_workers(client, tokens, db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Concurrent row locking requires PostgreSQL")
    send(client, tokens, event(event_type="privilege_escalation"))

    def worker(index):
        with SessionLocal() as session:
            return claim(session, f"worker-{index}", utcnow())

    with ThreadPoolExecutor(max_workers=2) as executor:
        items = list(executor.map(worker, range(2)))
    assert sum(item is not None for item in items) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://alerts.example/hook",
        "https://evil.example/hook",
        "https://alerts.example:8443/hook",
        "https://user:secret@alerts.example/hook",
        "https://alerts.example/hook?secret=x",
    ],
)
def test_notifications_reject_unapproved_destinations(url):
    with pytest.raises(ValueError):
        validate_destination(url, ["alerts.example"])


def test_collector_key_expiry_and_bounded_rotation_preserve_replay(client, tokens, db):
    source, old_key = connect(client, tokens)
    base = f"/api/v1/sources/{source['id']}"
    payload = record()
    initial = client.post(base + "/events", headers=old_key, json=payload)
    rotated = client.post(
        base + "/rotate-key", headers=tokens["admin"], json={"overlap_seconds": 300}
    )
    assert rotated.status_code == 200
    new_key = {"Authorization": "Bearer " + rotated.json()["collector_key"]}
    for key in (old_key, new_key):
        replay = client.post(base + "/events", headers=key, json=payload)
        assert replay.status_code == 201 and replay.json()["event_id"] == initial.json()["event_id"]
        assert replay.json()["duplicate"]
    row = db.get(LogSource, source["id"])
    row.previous_token_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post(base + "/events", headers=old_key, json=payload).status_code == 401
    row.token_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post(base + "/events", headers=new_key, json=payload).status_code == 401
    listed = client.get("/api/v1/sources", headers=tokens["admin"]).json()["items"][0]
    assert listed["status"] == "key_expired" and "previous_token_hash" not in listed
    assert (
        client.post(
            base + "/rotate-key", headers=tokens["admin"], json={"overlap_seconds": 601}
        ).status_code
        == 422
    )
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 0


def test_server_redaction_protects_direct_ingestion_and_nested_metadata(client, tokens):
    value = {
        "nested": [{"access_token": "test-only-private-token"}],
        "url": "https://user:private@service.example/path?session=private",
        "jwt": "eyJtest.test.test",
    }
    safe = redact(value)
    assert "test-only-private-token" not in str(safe) and "private" not in str(safe)
    result = send(client, tokens, event(message="Bearer test-only-private-token", metadata=value))
    assert "test-only-private-token" not in str(result) and "eyJtest.test.test" not in str(result)
