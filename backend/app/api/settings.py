from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.api.common import page, require_row
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import admin_only, audit, current_user, rate_limit, write_security
from app.models import AuditLog, RefreshSession, User
from app.schemas import Register, UserAccess, UserPatch
from app.services.serialization import serialize
from app.services.users import provision_viewer

router = APIRouter(tags=["System"])


def lock_administrator(db, user):
    # Serialize cross-account changes across workers, then recheck the actor.
    # Two administrators must not concurrently disable/demote one another into lockout.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(7369746578)"))
    db.refresh(user, with_for_update=True)
    if user.disabled or user.role != "ADMIN":
        raise HTTPException(403, "Administrator access is no longer active")


@router.get("/system")
def system(user: User = Depends(current_user)):
    settings = get_settings()
    return {
        "version": "0.1.0",
        "environment": settings.environment,
        "demo_mode": settings.demo_mode,
        "live_monitoring": settings.live_monitoring,
        "ai_provider": "llm" if settings.ai_provider == "openai" else settings.ai_provider,
        "ai_model": (
            settings.ollama_model
            if settings.ai_provider == "ollama"
            else settings.llm_model
            if settings.ai_provider == "openai"
            else None
        ),
        "threat_intel_provider": "AbuseIPDB" if settings.abuseipdb_api_key else "unconfigured",
    }


@router.get("/users/assignees")
def assignees(user: User = Depends(write_security), db: Session = Depends(get_db)):
    return {
        "items": [
            {"id": row.id, "name": row.name}
            for row in db.scalars(
                select(User).where(User.role.in_(["ADMIN", "ANALYST"]), User.disabled.is_(False))
            )
        ]
    }


@router.get("/users")
def list_users(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    return {"items": [serialize(row) for row in db.scalars(select(User).order_by(User.id))]}


@router.post("/users", status_code=201)
def create_user(
    data: Register,
    request: Request,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    rate_limit(request, "create-user", 10)
    return provision_viewer(db, data, user, request)


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    data: UserPatch,
    request: Request,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    lock_administrator(db, user)
    row = require_row(db, User, user_id)
    db.refresh(row, with_for_update=True)
    if row.id == user.id:
        raise HTTPException(409, "Administrators cannot change their own role")
    previous = row.role
    row.role = data.role
    row.auth_version += 1
    audit(
        db,
        user,
        "UPDATE_USER_ROLE",
        "user",
        user_id,
        request,
        {"before": previous, "after": data.role},
    )
    db.commit()
    return serialize(row)


@router.patch("/users/{user_id}/access")
def update_access(
    user_id: int,
    data: UserAccess,
    request: Request,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    lock_administrator(db, user)
    row = require_row(db, User, user_id)
    db.refresh(row, with_for_update=True)
    if row.id == user.id:
        raise HTTPException(409, "Administrators cannot disable their own account")
    row.disabled = data.disabled
    row.auth_version += 1
    db.execute(update(RefreshSession).where(RefreshSession.user_id == row.id).values(revoked=True))
    audit(db, user, "UPDATE_USER_ACCESS", "user", row.id, request, {"disabled": row.disabled})
    db.commit()
    return serialize(row)


@router.get("/audit-logs")
def audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    return page(
        db,
        select(AuditLog).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()),
        AuditLog,
        limit,
        offset,
    )
