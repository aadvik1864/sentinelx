"""Password + verified WebAuthn; bounded, origin-bound, single-use challenges."""

import json
import secrets
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field, field_validator
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)

from app.api.auth import set_refresh, user_view
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    DUMMY_HASH,
    audit,
    authenticated_user,
    issue_session,
    limiter,
    rate_limit,
    verify_password,
)
from app.models import RefreshSession, User, WebAuthnChallenge, WebAuthnCredential, utcnow
from app.schemas import Login, MFASetup, StrictModel
from app.services.mfa import recovery_codes
from app.services.telemetry import emit_activity

router = APIRouter(prefix="/auth/passkeys", tags=["Account security"])
settings = get_settings()


class Finish(StrictModel):
    challenge_id: UUID
    credential: dict
    name: str = Field(default="Passkey", min_length=1, max_length=100)

    @field_validator("credential")
    @classmethod
    def bounded(cls, value):
        if len(json.dumps(value)) > 20000:
            raise ValueError("Credential response too large")
        return value


def origin(request):
    value = request.headers.get("origin", "")
    if value not in settings.origins:
        raise HTTPException(403, "Invalid passkey origin")
    if urlsplit(value).hostname != settings.webauthn_rp_id:
        raise HTTPException(403, "Passkeys require the configured relying-party hostname")
    return value


def begin(db, user, kind, request):
    db.execute(
        delete(WebAuthnChallenge).where(
            WebAuthnChallenge.user_id == user.id,
            WebAuthnChallenge.kind == kind,
        )
    )
    challenge = WebAuthnChallenge(
        id=str(uuid4()),
        user_id=user.id,
        kind=kind,
        challenge=secrets.token_urlsafe(32),
        auth_version=user.auth_version,
        origin=origin(request),
        expires_at=utcnow() + timedelta(minutes=5),
    )
    db.add(challenge)
    return challenge


def browser_response(credential, user=None):
    response = credential.get("response", {})
    if not isinstance(response, dict) or not isinstance(credential.get("id"), str):
        raise ValueError("Malformed browser response")
    client_data = response.get("clientDataJSON")
    if not isinstance(client_data, str):
        raise ValueError("Missing client data")
    client = json.loads(base64url_to_bytes(client_data))
    if (
        not isinstance(client, dict)
        or client.get("crossOrigin", False) is not False
        or "topOrigin" in client
    ):
        raise ValueError("Cross-origin/embedded passkey responses are not supported")
    handle = response.get("userHandle")
    if handle is not None and not isinstance(handle, str):
        raise ValueError("Malformed account handle")
    if (
        user
        and handle is not None
        and base64url_to_bytes(handle) != base64url_to_bytes(user.mfa_webauthn_handle or "")
    ):
        raise ValueError("Account handle mismatch")


def consume(db, data, kind, request, expected_user=None):
    row = db.get(WebAuthnChallenge, str(data.challenge_id))
    if not row or (expected_user and row.user_id != expected_user.id):
        raise HTTPException(401, "Passkey challenge expired or already used")
    user = db.scalar(
        select(User)
        .where(User.id == row.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    row = db.scalar(
        select(WebAuthnChallenge)
        .where(WebAuthnChallenge.id == row.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        not user
        or user.disabled
        or not row
        or row.kind != kind
        or row.expires_at <= utcnow()
        or row.auth_version != user.auth_version
        or row.origin != origin(request)
    ):
        raise HTTPException(401, "Passkey challenge expired or account access changed")
    removed = db.execute(delete(WebAuthnChallenge).where(WebAuthnChallenge.id == row.id))
    if removed.rowcount != 1:
        raise HTTPException(401, "Passkey challenge already used")
    return user, row


@router.get("")
def list_passkeys(user: User = Depends(authenticated_user)):
    return {
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "created_at": row.created_at,
                "last_used_at": row.last_used_at,
            }
            for row in user.passkeys
        ]
    }


@router.post("/register/options")
def registration_options(
    data: MFASetup,
    request: Request,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
):
    rate_limit(request, "passkey-register", 5)
    db.refresh(user, with_for_update=True)
    if user.disabled or user.must_change_password:
        raise HTTPException(403, "Replace the starter password before enrolling a passkey")
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if len(user.passkeys) >= 10:
        raise HTTPException(409, "Remove an unused passkey before adding another")
    if not user.mfa_webauthn_handle:
        user.mfa_webauthn_handle = secrets.token_urlsafe(32)
    challenge = begin(db, user, "register", request)
    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name="SentinelX",
        user_name=user.email,
        user_id=base64url_to_bytes(user.mfa_webauthn_handle),
        challenge=base64url_to_bytes(challenge.challenge),
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.REQUIRED
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(row.credential_id))
            for row in user.passkeys
        ],
    )
    db.commit()
    return {"challenge_id": challenge.id, "options": json.loads(options_to_json(options))}


@router.post("/register/verify")
def registration_verify(
    data: Finish,
    request: Request,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
):
    rate_limit(request, "passkey-register-verify", 10)
    user, challenge = consume(db, data, "register", request, user)
    if user.must_change_password or len(user.passkeys) >= 10:
        raise HTTPException(403, "Account cannot enroll another passkey")
    try:
        browser_response(data.credential)
        result = verify_registration_response(
            credential=data.credential,
            expected_challenge=base64url_to_bytes(challenge.challenge),
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=challenge.origin,
            require_user_verification=True,
        )
        credential_id = bytes_to_base64url(result.credential_id)
        if len(credential_id) > 2048 or db.scalar(
            select(WebAuthnCredential.id).where(WebAuthnCredential.credential_id == credential_id)
        ):
            raise ValueError("Credential already registered")
    except (WebAuthnException, ValueError, TypeError, KeyError):
        db.commit()  # Invalid responses also consume the challenge.
        raise HTTPException(400, "Passkey verification failed; start again") from None
    codes = recovery_codes(user) if not (user.mfa_secret or user.passkeys) else []
    db.add(
        WebAuthnCredential(
            user_id=user.id,
            credential_id=credential_id,
            public_key=bytes_to_base64url(result.credential_public_key),
            sign_count=result.sign_count,
            name=data.name,
        )
    )
    user.auth_version += 1
    db.execute(update(RefreshSession).where(RefreshSession.user_id == user.id).values(revoked=True))
    audit(db, user, "PASSKEY_ADDED", "user", user.id, request)
    db.commit()
    emit_activity(
        request, "account_security_changed", "User enrolled a passkey", username=user.email[:100]
    )
    return {"recovery_codes": codes}


@router.post("/login/options")
def login_options(data: Login, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "passkey-login", 10)
    limiter.check("login-account:" + str(data.email).lower(), 10, 300)
    user = db.scalar(select(User).where(User.email == str(data.email).lower()).with_for_update())
    valid = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or user.disabled or not valid or not user.passkeys:
        audit(db, None, "LOGIN_FAILED", "auth", "passkey", request)
        db.commit()
        emit_activity(
            request,
            "authentication_failure",
            "Passkey sign-in rejected",
            username=str(data.email).lower()[:100],
            level="WARNING",
        )
        raise HTTPException(401, "Incorrect sign-in details or no enrolled passkey")
    challenge = begin(db, user, "login", request)
    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        challenge=base64url_to_bytes(challenge.challenge),
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(row.credential_id))
            for row in user.passkeys
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    db.commit()
    return {"challenge_id": challenge.id, "options": json.loads(options_to_json(options))}


@router.post("/login/verify")
def login_verify(data: Finish, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(request, "passkey-login-verify", 10)
    user, challenge = consume(db, data, "login", request)
    try:
        browser_response(data.credential, user)
        credential = db.scalar(
            select(WebAuthnCredential)
            .where(
                WebAuthnCredential.user_id == user.id,
                WebAuthnCredential.credential_id == data.credential.get("id", ""),
            )
            .with_for_update()
        )
        if not credential:
            raise ValueError("Unknown account credential")
        result = verify_authentication_response(
            credential=data.credential,
            expected_challenge=base64url_to_bytes(challenge.challenge),
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=challenge.origin,
            credential_public_key=base64url_to_bytes(credential.public_key),
            credential_current_sign_count=credential.sign_count,
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, TypeError, KeyError):
        audit(db, None, "LOGIN_FAILED", "auth", "passkey", request)
        db.commit()
        emit_activity(
            request,
            "authentication_failure",
            "Passkey verification rejected",
            username=user.email[:100],
            level="WARNING",
        )
        raise HTTPException(401, "Passkey verification failed; start again") from None
    credential.sign_count, credential.last_used_at = result.new_sign_count, utcnow()
    access, refresh = issue_session(db, user, mfa_verified=True)
    audit(db, user, "LOGIN_PASSKEY", "user", user.id, request)
    db.commit()
    set_refresh(response, refresh)
    emit_activity(
        request,
        "authentication_success",
        "User signed in with a passkey",
        username=user.email[:100],
    )
    return {"access_token": access, "token_type": "bearer", "user": user_view(user)}


@router.post("/{credential_id}/remove", status_code=204)
def remove_passkey(
    credential_id: int,
    data: MFASetup,
    request: Request,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
):
    rate_limit(request, "passkey-remove", 5)
    db.refresh(user, with_for_update=True)
    if user.disabled or not verify_password(data.password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    credential = db.scalar(
        select(WebAuthnCredential).where(
            WebAuthnCredential.id == credential_id, WebAuthnCredential.user_id == user.id
        )
    )
    if not credential:
        raise HTTPException(404, "Passkey not found")
    if not user.mfa_secret and len(user.passkeys) <= 1:
        raise HTTPException(
            409, "Add another passkey or a TOTP authenticator before removing the last factor"
        )
    db.delete(credential)
    user.auth_version += 1
    db.execute(update(RefreshSession).where(RefreshSession.user_id == user.id).values(revoked=True))
    audit(db, user, "PASSKEY_REMOVED", "user", user.id, request)
    db.commit()
    emit_activity(
        request, "account_security_changed", "User removed a passkey", username=user.email[:100]
    )
