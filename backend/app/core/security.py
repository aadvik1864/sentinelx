import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import redis
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import AuditLog, RefreshSession, User, utcnow

settings = get_settings()
hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_session(
    db: Session, user: User, family: str | None = None, *, mfa_verified: bool = False
):
    refresh = secrets.token_urlsafe(48)
    session = RefreshSession(
        id=str(uuid4()),
        user_id=user.id,
        family=family or str(uuid4()),
        token_hash=token_digest(refresh),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
        mfa_verified=mfa_verified,
    )
    db.add(session)
    db.flush()
    now = datetime.now(UTC)
    access = jwt.encode(
        {
            "sub": str(user.id),
            "sid": session.id,
            "ver": user.auth_version,
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
            "iss": "sentinelx",
            "aud": "sentinelx-api",
            "jti": str(uuid4()),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return access, refresh


def authenticate_token(token: str, db: Session, *, allow_setup: bool = False) -> User:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience="sentinelx-api",
            issuer="sentinelx",
            options={"require": ["exp", "iat", "sub", "sid", "ver", "jti"]},
        )
        user = db.get(User, int(payload["sub"]))
        session = db.get(RefreshSession, payload["sid"])
        if (
            not user
            or user.disabled
            or not session
            or session.user_id != user.id
            or session.revoked
            or session.expires_at <= utcnow()
            or payload["ver"] != user.auth_version
        ):
            raise ValueError("Invalid session")
        if not allow_setup and (
            user.must_change_password
            or (settings.require_mfa and not user.mfa_secret)
            or (user.mfa_secret and not session.mfa_verified)
        ):
            raise HTTPException(
                403, "Complete account security setup before accessing the workspace"
            )
        return user
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(401, "Session expired. Please sign in again.") from None


def authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(401, "Authentication required")
    return authenticate_token(credentials.credentials, db, allow_setup=True)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(401, "Authentication required")
    return authenticate_token(credentials.credentials, db)


def roles(*allowed: str):
    def dependency(user: User = Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(403, "Your role does not permit this action")
        return user

    return dependency


read_security = roles("ADMIN", "ANALYST")
write_security = roles("ADMIN", "ANALYST")
admin_only = roles("ADMIN")


def audit(
    db: Session,
    user: User | None,
    action: str,
    resource: str,
    resource_id,
    request: Request | None = None,
    details: dict | None = None,
):
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            resource=resource,
            resource_id=str(resource_id),
            ip_address=request.client.host if request and request.client else None,
            details=details or {},
        )
    )


class RateLimiter:
    def __init__(self):
        self.redis = (
            redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
            if settings.redis_url
            else None
        )
        self.entries = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str, limit: int = 30, seconds: int = 60):
        key = "sentinelx:limit:" + token_digest(key)
        if self.redis:
            try:
                script = "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n"
                count = self.redis.eval(script, 1, key, seconds)
                if count > limit:
                    raise HTTPException(
                        429,
                        "Too many requests. Try again shortly.",
                        headers={"Retry-After": str(seconds)},
                    )
                return
            except redis.RedisError:
                if settings.environment == "production":
                    raise HTTPException(503, "Rate limiter unavailable") from None
        with self.lock:
            now = time.monotonic()
            # Opportunistic cleanup bounds the development-only fallback's memory.
            if len(self.entries) > 10000:
                self.entries = defaultdict(
                    deque, {k: v for k, v in self.entries.items() if v and now - v[-1] < seconds}
                )
            values = self.entries[key]
            while values and values[0] <= now - seconds:
                values.popleft()
            if len(values) >= limit:
                raise HTTPException(
                    429,
                    "Too many requests. Try again shortly.",
                    headers={"Retry-After": str(seconds)},
                )
            values.append(now)


limiter = RateLimiter()


def rate_limit(request: Request, scope: str, limit: int = 30):
    limiter.check(f"{scope}:{request.client.host if request.client else 'unknown'}", limit)
