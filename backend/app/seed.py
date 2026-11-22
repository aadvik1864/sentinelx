import json
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import AuditLog, DetectionRule, User
from app.schemas import RuleInput

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
                must_change_password=settings.environment == "production",
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


if __name__ == "__main__":
    with SessionLocal() as db:
        bootstrap(db)
    print("Bootstrap complete. No activity records were inserted.")
