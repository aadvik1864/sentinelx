from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    DUMMY_HASH,
    admin_only,
    audit,
    current_user,
    hash_password,
    issue_session,
    limiter,
    rate_limit,
    token_digest,
    verify_password,
)
from app.models import RefreshSession, User, utcnow
from app.schemas import ChangePassword, Login, Register
from app.services.serialization import serialize
from app.services.telemetry import emit_activity
from app.services.users import provision_viewer

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


def set_refresh(response: Response, token: str):
    response.set_cookie(
        "sentinelx_refresh",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/api/v1/auth",
        max_age=settings.refresh_token_days * 86400,
    )
    response.headers["Cache-Control"] = "no-store"


@router.post("/register", status_code=201)
def register(
    data: Register,
    request: Request,
    administrator: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    # Compatibility route for administrator provisioning, never anonymous sign-up.
    rate_limit(request, "register", 5)
    return provision_viewer(db, data, administrator, request)


@router.post("/login")
def login(data: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(request, "login", 10)
    email = str(data.email).lower()
    limiter.check("login-account:" + email, 10, 300)
    user = db.scalar(select(User).where(User.email == email))
    valid = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        audit(db, None, "LOGIN_FAILED", "auth", "login", request)
        db.commit()
        emit_activity(
            request,
            "authentication_failure",
            "Sign-in rejected",
            username=email[:100],
            level="WARNING",
        )
        raise HTTPException(401, "Incorrect email or password")
    access, refresh = issue_session(db, user)
    audit(db, user, "LOGIN", "user", user.id, request)
    db.commit()
    set_refresh(response, refresh)
    emit_activity(request, "authentication_success", "User signed in", username=email[:100])
    return {"access_token": access, "token_type": "bearer", "user": serialize(user)}


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(request, "refresh", 60)
    token = request.cookies.get("sentinelx_refresh", "")
    session = db.scalar(
        select(RefreshSession)
        .where(RefreshSession.token_hash == token_digest(token))
        .with_for_update()
    )
    if not session or session.expires_at <= utcnow():
        raise HTTPException(401, "Session expired. Please sign in again.")
    if session.revoked or session.consumed:
        db.execute(
            update(RefreshSession)
            .where(RefreshSession.family == session.family)
            .values(revoked=True)
        )
        db.commit()
        emit_activity(
            request, "refresh_replay", "Refresh credential replay rejected", level="WARNING"
        )
        raise HTTPException(401, "Refresh token reuse detected. Please sign in again.")
    user = db.get(User, session.user_id)
    consumed = db.execute(
        update(RefreshSession)
        .where(
            RefreshSession.id == session.id,
            RefreshSession.consumed.is_(False),
            RefreshSession.revoked.is_(False),
        )
        .values(consumed=True)
    )
    if consumed.rowcount != 1:
        db.execute(
            update(RefreshSession)
            .where(RefreshSession.family == session.family)
            .values(revoked=True)
        )
        db.commit()
        raise HTTPException(401, "Refresh token reuse detected. Please sign in again.")
    access, new_refresh = issue_session(db, user, session.family)
    db.commit()
    set_refresh(response, new_refresh)
    return {"access_token": access, "token_type": "bearer", "user": serialize(user)}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("sentinelx_refresh", "")
    session = db.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == token_digest(token))
    )
    if session:
        db.execute(
            update(RefreshSession)
            .where(RefreshSession.family == session.family)
            .values(revoked=True)
        )
        audit(db, db.get(User, session.user_id), "LOGOUT", "user", session.user_id, request)
        db.commit()
        emit_activity(request, "session_logout", "User signed out")
    response.delete_cookie(
        "sentinelx_refresh",
        path="/api/v1/auth",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


@router.get("/me")
def me(user: User = Depends(current_user)):
    return serialize(user)


@router.post("/change-password", status_code=204)
def change_password(
    data: ChangePassword,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rate_limit(request, "password", 5)
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(data.new_password)
    user.auth_version += 1
    db.execute(update(RefreshSession).where(RefreshSession.user_id == user.id).values(revoked=True))
    audit(db, user, "CHANGE_PASSWORD", "user", user.id, request)
    db.commit()
    emit_activity(
        request, "password_changed", "User changed their password", username=user.email[:100]
    )
