import time
from datetime import timedelta

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    DUMMY_HASH,
    admin_only,
    audit,
    authenticated_user,
    hash_password,
    issue_session,
    limiter,
    rate_limit,
    token_digest,
    verify_password,
)
from app.models import RefreshSession, User, utcnow
from app.schemas import ChangePassword, Login, MFAEnable, MFASetup, Register
from app.services import mfa
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


def user_view(user):
    return {**serialize(user), "mfa_required": settings.require_mfa}


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
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    valid = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
    mfa_valid = bool(
        user
        and not user.disabled
        and (user.mfa_secret or user.passkeys)
        and valid
        and mfa.verify(user, data.otp)
    )
    if (
        not user
        or user.disabled
        or not valid
        or ((user.mfa_secret or user.passkeys) and not mfa_valid)
    ):
        audit(db, None, "LOGIN_FAILED", "auth", "login", request)
        db.commit()
        emit_activity(
            request,
            "authentication_failure",
            "Sign-in rejected",
            username=email[:100],
            level="WARNING",
        )
        raise HTTPException(
            401,
            "Incorrect sign-in details. Check your email, password, and authenticator or recovery code.",
        )
    access, refresh = issue_session(db, user, mfa_verified=mfa_valid)
    audit(db, user, "LOGIN", "user", user.id, request)
    db.commit()
    set_refresh(response, refresh)
    emit_activity(request, "authentication_success", "User signed in", username=email[:100])
    return {"access_token": access, "token_type": "bearer", "user": user_view(user)}


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(request, "refresh", 60)
    token = request.cookies.get("sentinelx_refresh", "")
    session = db.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == token_digest(token))
    )
    if not session or session.expires_at <= utcnow():
        raise HTTPException(401, "Session expired. Please sign in again.")
    # Every identity mutation locks user -> session, avoiding refresh/MFA lock inversion.
    user = db.scalar(
        select(User)
        .where(User.id == session.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    db.refresh(session, with_for_update=True)
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
    if (
        not user
        or user.disabled
        or ((user.mfa_secret or user.passkeys) and not session.mfa_verified)
    ):
        raise HTTPException(401, "Please sign in with your authenticator.")
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
    access, new_refresh = issue_session(db, user, session.family, mfa_verified=session.mfa_verified)
    db.commit()
    set_refresh(response, new_refresh)
    return {"access_token": access, "token_type": "bearer", "user": user_view(user)}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("sentinelx_refresh", "")
    session = db.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == token_digest(token))
    )
    if session:
        user = db.scalar(select(User).where(User.id == session.user_id).with_for_update())
        db.execute(
            update(RefreshSession)
            .where(RefreshSession.family == session.family)
            .values(revoked=True)
        )
        audit(db, user, "LOGOUT", "user", session.user_id, request)
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
def me(user: User = Depends(authenticated_user)):
    return user_view(user)


@router.post("/change-password", status_code=204)
def change_password(
    data: ChangePassword,
    request: Request,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
):
    rate_limit(request, "password", 5)
    db.refresh(user, with_for_update=True)
    if user.disabled:
        raise HTTPException(401, "Session expired. Please sign in again.")
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if verify_password(data.new_password, user.password_hash):
        raise HTTPException(400, "Choose a password different from your current password")
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    user.auth_version += 1
    db.execute(update(RefreshSession).where(RefreshSession.user_id == user.id).values(revoked=True))
    audit(db, user, "CHANGE_PASSWORD", "user", user.id, request)
    db.commit()
    emit_activity(
        request, "password_changed", "User changed their password", username=user.email[:100]
    )


@router.post("/mfa/setup")
def setup_mfa(
    data: MFASetup,
    request: Request,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
):
    rate_limit(request, "mfa-setup", 5)
    db.refresh(user, with_for_update=True)
    if user.disabled:
        raise HTTPException(401, "Session expired. Please sign in again.")
    if user.must_change_password:
        raise HTTPException(403, "Replace your starter password before adding an authenticator")
    if user.mfa_secret:
        raise HTTPException(409, "An authenticator is already enabled")
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    secret = pyotp.random_base32()
    user.mfa_pending_secret = mfa.encrypt(secret)
    user.mfa_pending_expires_at = utcnow() + timedelta(minutes=10)
    audit(db, user, "MFA_ENROLLMENT_STARTED", "user", user.id, request)
    db.commit()
    return {
        "secret": secret,
        "uri": pyotp.TOTP(secret).provisioning_uri(user.email, issuer_name="SentinelX"),
    }


@router.post("/mfa/enable")
def enable_mfa(
    data: MFAEnable,
    request: Request,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
):
    rate_limit(request, "mfa-enable", 5)
    db.refresh(user, with_for_update=True)
    if user.disabled:
        raise HTTPException(401, "Session expired. Please sign in again.")
    if (
        user.must_change_password
        or user.mfa_secret
        or not user.mfa_pending_secret
        or not user.mfa_pending_expires_at
        or user.mfa_pending_expires_at <= utcnow()
    ):
        raise HTTPException(409, "Start authenticator setup again")
    totp = pyotp.TOTP(mfa.decrypt(user.mfa_pending_secret))
    step = int(time.time()) // totp.interval
    # Enrollment accepts only the current step; subsequent login has a ±30s tolerance.
    if not totp.verify(data.code, for_time=step * totp.interval):
        raise HTTPException(400, "Incorrect authenticator code")
    user.mfa_secret = user.mfa_pending_secret
    user.mfa_pending_secret = None
    user.mfa_pending_expires_at = None
    user.mfa_last_step = step
    codes = mfa.recovery_codes(user)
    user.auth_version += 1
    db.execute(update(RefreshSession).where(RefreshSession.user_id == user.id).values(revoked=True))
    audit(db, user, "MFA_ENABLED", "user", user.id, request)
    db.commit()
    return {"recovery_codes": codes}
