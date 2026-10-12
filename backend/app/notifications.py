"""Explicit outbox-to-webhook delivery. At-least-once; receivers must deduplicate IDs."""

import argparse
import json
import os
import time
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, or_, select, update
from sqlalchemy.orm import sessionmaker

from app.models import NotificationOutbox, utcnow


def validate_destination(value, allowed_hosts):
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or url.hostname not in allowed_hosts
        or url.port not in {None, 443}
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "Delivery requires an explicitly allowlisted HTTPS destination on port 443"
        )
    return value


def claim(db, owner, now):
    row = db.scalar(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.delivered_at.is_(None),
            NotificationOutbox.next_attempt_at <= now,
            or_(NotificationOutbox.lease_until.is_(None), NotificationOutbox.lease_until <= now),
        )
        .order_by(NotificationOutbox.created_at, NotificationOutbox.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if not row:
        return None
    # Conditional update also protects SQLite test/development workers without row locks.
    changed = db.execute(
        update(NotificationOutbox)
        .where(
            NotificationOutbox.id == row.id,
            or_(NotificationOutbox.lease_until.is_(None), NotificationOutbox.lease_until <= now),
            NotificationOutbox.delivered_at.is_(None),
        )
        .values(
            lease_owner=owner, lease_until=now + timedelta(seconds=60), attempts=row.attempts + 1
        )
    )
    if changed.rowcount != 1:
        db.rollback()
        return None
    item = {
        "id": row.id,
        "type": "new_alert",
        "created_at": row.created_at.isoformat() + "Z",
        "data": row.payload,
    }
    db.commit()
    return item


def deliver_once(db, client, url, token="", now=None):
    now = now or utcnow()
    owner = str(uuid4())
    item = claim(db, owner, now)
    if not item:
        return False
    error = ""
    try:
        response = client.post(
            url,
            json=item,
            headers={
                "Idempotency-Key": item["id"],
                **({"Authorization": "Bearer " + token} if token else {}),
            },
        )
        if not 200 <= response.status_code < 300:
            error = "destination_rejected"
    except httpx.HTTPError:
        error = "connection_failed"
    row = db.scalar(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.id == item["id"],
            NotificationOutbox.lease_owner == owner,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row:
        if not error:
            row.delivered_at = utcnow()
        else:
            row.next_attempt_at = utcnow() + timedelta(
                seconds=min(3600, 2 ** min(row.attempts, 11))
            )
        row.last_error = error
        row.lease_owner = None
        row.lease_until = None
        db.commit()
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database", default="")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    if not args.apply:
        with SessionLocal() as db:
            rows = db.scalars(
                select(NotificationOutbox.id)
                .where(NotificationOutbox.delivered_at.is_(None))
                .limit(1000)
            ).all()
            print(json.dumps({"apply": False, "pending_in_sample": len(rows)}))
        return
    if args.confirm_database != engine.url.database:
        parser.error("Delivery requires the exact selected --confirm-database")
    if engine.url.username != "sentinelx_notifier":
        parser.error("Delivery requires the isolated outbox-only notifier database identity")
    url = validate_destination(
        os.environ.get("ALERT_WEBHOOK_URL", ""),
        os.environ.get("ALERT_WEBHOOK_ALLOWED_HOSTS", "").split(","),
    )
    proxy = urlsplit(os.environ.get("EGRESS_PROXY_URL", ""))
    if (
        proxy.scheme != "http"
        or proxy.hostname != "egress-proxy"
        or proxy.port != 8081
        or proxy.username != "sentinelx"
        or not proxy.password
        or len(proxy.password) < 24
        or proxy.path
        or proxy.query
        or proxy.fragment
    ):
        parser.error("Delivery requires the approved controlled-egress proxy")
    with httpx.Client(
        proxy=proxy.geturl(), timeout=10, follow_redirects=False, trust_env=False
    ) as client:
        while True:
            with SessionLocal() as db:
                processed = deliver_once(db, client, url, os.environ.get("ALERT_WEBHOOK_TOKEN", ""))
            if args.once:
                break
            if not processed:
                time.sleep(2)


if __name__ == "__main__":
    main()
