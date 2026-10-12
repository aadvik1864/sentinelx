"""Operator-only maintenance. Dry-run by default; never scheduled implicitly."""

import argparse
import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, exists, func, select, update

from app.core.database import SessionLocal, engine
from app.core.security import audit
from app.models import (
    Alert,
    AuditLog,
    Event,
    IncidentEvent,
    RefreshSession,
    SourceReceipt,
    User,
    WebAuthnChallenge,
    WebAuthnCredential,
    utcnow,
)
from app.services.serialization import serialize


def retention_candidates(days: int):
    if days < 7:
        raise ValueError(
            "Retention must be at least 7 days (longer than the maximum detection window)"
        )
    cutoff = utcnow() - timedelta(days=days)
    return (
        select(Event.id)
        .where(
            Event.timestamp < cutoff,
            Event.created_at < cutoff,
            ~exists().where(Alert.event_id == Event.id),
            ~exists().where(IncidentEvent.event_id == Event.id),
            ~exists().where(
                SourceReceipt.event_id == Event.id, SourceReceipt.incident_id.is_not(None)
            ),
        )
        .order_by(Event.id)
    )


def maintain(db, days: int, *, apply: bool = False, batch_size: int = 1000):
    if not 1 <= batch_size <= 10000:
        raise ValueError("Batch size must be 1–10000")
    candidates = retention_candidates(days).limit(batch_size)
    ids = list(db.scalars(candidates))
    expired = RefreshSession.expires_at < utcnow()
    report = {
        "apply": apply,
        "retention_days": days,
        "eligible_events_in_batch": len(ids),
        "expired_sessions": db.scalar(
            select(func.count()).select_from(RefreshSession).where(expired)
        ),
    }
    if apply:
        if db.bind.dialect.name != "postgresql":
            raise ValueError("Retention writes require PostgreSQL; SQLite supports dry-runs only")
        db.execute(delete(Event).where(Event.id.in_(ids)))
        db.execute(delete(RefreshSession).where(expired))
        audit(db, None, "RETENTION_APPLIED", "system", "maintenance", details=report)
        db.commit()
    return report


def export_audit(db, output: Path, after_id: int, previous_hash: str):
    """A verifiable export, not a substitute for a separately controlled immutable sink."""
    digest = previous_hash
    last_id = after_id
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as file:
        rows = db.scalars(
            select(AuditLog).where(AuditLog.id > after_id).order_by(AuditLog.id)
        ).yield_per(1000)
        for row in rows:
            payload = json.dumps(serialize(row), sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256((digest + "\n" + payload).encode()).hexdigest()
            file.write(json.dumps({"entry": json.loads(payload), "sha256": digest}) + "\n")
            last_id = row.id
        file.flush()
        os.fsync(file.fileno())
    return {"last_id": last_id, "sha256": digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    retention = commands.add_parser("retention")
    retention.add_argument("--days", type=int, required=True)
    retention.add_argument("--batch-size", type=int, default=1000)
    reset = commands.add_parser("reset-mfa")
    reset.add_argument("--user-id", type=int, required=True)
    reset.add_argument(
        "--include-passkeys",
        action="store_true",
        help="Also revoke enrolled passkeys after independent identity verification",
    )
    for command in (retention, reset):
        command.add_argument("--apply", action="store_true")
        command.add_argument("--confirm-database", default="")
    exporter = commands.add_parser("export-audit")
    exporter.add_argument("--output", type=Path, required=True)
    exporter.add_argument("--after-id", type=int, default=0)
    exporter.add_argument("--previous-hash", default="0" * 64)
    args = parser.parse_args()
    if getattr(args, "apply", False) and args.confirm_database != engine.url.database:
        parser.error("--apply requires --confirm-database matching the selected database exactly")
    with SessionLocal() as db:
        if args.command == "retention":
            report = maintain(db, args.days, apply=args.apply, batch_size=args.batch_size)
        elif args.command == "reset-mfa":
            user = db.scalar(select(User).where(User.id == args.user_id).with_for_update())
            if not user:
                parser.error("User not found")
            report = {"user_id": user.id, "apply": args.apply}
            if args.apply:
                if args.include_passkeys:
                    db.execute(
                        delete(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
                    )
                db.execute(delete(WebAuthnChallenge).where(WebAuthnChallenge.user_id == user.id))
                user.mfa_secret = None
                user.mfa_pending_secret = None
                user.mfa_pending_expires_at = None
                user.mfa_last_step = -1
                user.mfa_recovery_hashes = []
                user.auth_version += 1
                db.execute(
                    update(RefreshSession)
                    .where(RefreshSession.user_id == user.id)
                    .values(revoked=True)
                )
                audit(
                    db,
                    None,
                    "OPERATOR_MFA_RESET",
                    "user",
                    user.id,
                    details={"include_passkeys": args.include_passkeys},
                )
                db.commit()
        else:
            if (
                args.after_id < 0
                or len(args.previous_hash) != 64
                or any(char not in "0123456789abcdef" for char in args.previous_hash)
            ):
                parser.error(
                    "Supply a nonnegative audit cursor and a 64-character lowercase SHA-256 anchor"
                )
            report = export_audit(db, args.output, args.after_id, args.previous_hash)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
