import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Asset, AuditLog, DetectionRule, Event, User
from app.schemas import EventInput, RuleInput
from app.services.detection.engine import ingest

RULES_DIR = Path(__file__).resolve().parents[2] / "detection-rules"
if not RULES_DIR.exists():
    RULES_DIR = Path(__file__).resolve().parents[3] / "detection-rules"


def bootstrap(db):
    settings = get_settings()
    if settings.bootstrap_admin_password and not db.scalar(
        select(User.id).where(User.email == settings.bootstrap_admin_email.lower())
    ):
        if len(settings.bootstrap_admin_password) < 12:
            raise ValueError("BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters")
        db.add(
            User(
                name="SOC administrator",
                email=settings.bootstrap_admin_email.lower(),
                password_hash=hash_password(settings.bootstrap_admin_password),
                role="ADMIN",
            )
        )
    # A persistent marker prevents an intentionally deleted rule from reappearing on restart.
    if not db.scalar(select(AuditLog.id).where(AuditLog.action == "BOOTSTRAP_RULES")):
        for file in sorted(RULES_DIR.glob("**/*.json")):
            for value in json.loads(file.read_text()):
                data = RuleInput.model_validate(value)
                if not db.scalar(select(DetectionRule.id).where(DetectionRule.name == data.name)):
                    db.add(DetectionRule(**data.model_dump()))
        db.add(
            AuditLog(action="BOOTSTRAP_RULES", resource="system", resource_id="default-rules-v1")
        )
    db.commit()


def attack_sequence(hostname="linux-lab-01", source_ip="203.0.113.42"):
    now = datetime.now(UTC) - timedelta(seconds=50)
    events = []
    for index in range(12):
        events.append(
            EventInput(
                timestamp=now + timedelta(seconds=index * 2),
                source="linux",
                event_type="authentication_failure",
                severity="medium",
                source_ip=source_ip,
                username="admin",
                hostname=hostname,
                message=f"Failed password for admin from {source_ip} port 52412 ssh2",
                metadata={"simulated": True},
            )
        )
    events.extend(
        [
            EventInput(
                timestamp=now + timedelta(seconds=30),
                source="linux",
                event_type="authentication_success",
                severity="low",
                source_ip=source_ip,
                username="admin",
                hostname=hostname,
                message=f"Accepted password for admin from {source_ip}",
                metadata={"simulated": True},
            ),
            EventInput(
                timestamp=now + timedelta(seconds=35),
                source="linux",
                event_type="privilege_escalation",
                severity="high",
                source_ip=source_ip,
                username="admin",
                hostname=hostname,
                message="sudo: admin : USER=root ; COMMAND=/usr/bin/id",
                metadata={"simulated": True},
            ),
        ]
    )
    return events


def seed_demo(db):
    if db.scalar(select(func.count()).select_from(Event)):
        return
    rng = random.Random(42)
    assets = [
        ("linux-lab-01", "10.10.0.11", "server"),
        ("web-lab-01", "10.10.0.20", "server"),
        ("auth-service", "10.10.0.30", "application"),
        ("analyst-workstation", "10.10.0.40", "endpoint"),
    ]
    for host, ip, kind in assets:
        if not db.scalar(select(Asset.id).where(Asset.hostname == host)):
            db.add(Asset(hostname=host, ip_address=ip, type=kind, environment="lab"))
    db.commit()
    now = datetime.now(UTC)
    # Baseline events are persisted, not synthetic dashboard metrics.
    for hour in range(24):
        for _index in range(rng.randint(8, 25)):
            db.add(
                Event(
                    timestamp=(
                        now - timedelta(hours=23 - hour, minutes=rng.randint(1, 59))
                    ).replace(tzinfo=None),
                    source="nginx",
                    event_type="http_request",
                    severity="low",
                    source_ip=f"10.10.0.{rng.randint(41, 48)}",
                    hostname="web-lab-01",
                    message="GET /health 200",
                    details={"http_status": 200, "simulated": True},
                )
            )
    db.commit()
    for port in [22, 23, 25, 53, 80, 443, 445, 3389]:
        ingest(
            db,
            EventInput(
                timestamp=now - timedelta(minutes=9),
                source="network",
                event_type="network_connection",
                source_ip="198.51.100.18",
                hostname="web-lab-01",
                message=f"Connection attempt to port {port}",
                metadata={"destination_port": port, "simulated": True},
            ),
        )
    for event in attack_sequence():
        ingest(db, event)


if __name__ == "__main__":
    with SessionLocal() as db:
        bootstrap(db)
        if get_settings().seed_demo:
            seed_demo(db)
    print("Bootstrap complete. Demo data is inserted only when SEED_DEMO=true and no events exist.")
