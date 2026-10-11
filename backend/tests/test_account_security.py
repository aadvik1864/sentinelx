import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pyotp
import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.core.security import limiter
from app.models import AuditLog, RefreshSession, User, utcnow
from app.services.mfa import decrypt
from tests.conftest import PASSWORD
from tests.test_security import production_settings


def login(client, otp="", password=PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        json={"email": "admin@sentinelx.dev", "password": password, "otp": otp},
    )


def enroll(client, token):
    setup = client.post("/api/v1/auth/mfa/setup", headers=token, json={"password": PASSWORD})
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    enabled = client.post(
        "/api/v1/auth/mfa/enable", headers=token, json={"code": pyotp.TOTP(secret).now()}
    )
    assert enabled.status_code == 200
    return secret, enabled.json()["recovery_codes"]


def test_production_requires_mfa_key():
    with pytest.raises(ValueError, match="MFA_ENCRYPTION_KEY"):
        production_settings(mfa_encryption_key="")
    with pytest.raises(ValueError, match="Fernet"):
        production_settings(mfa_encryption_key="not-a-key")
    assert production_settings().require_mfa


def test_starter_password_gates_reads_writes_sockets_and_cannot_be_reused(client, tokens):
    created = client.post(
        "/api/v1/users",
        headers=tokens["admin"],
        json={"name": "New teammate", "email": "new@example.com", "password": PASSWORD},
    ).json()
    session = client.post(
        "/api/v1/auth/login", json={"email": created["email"], "password": PASSWORD}
    ).json()
    token = {"Authorization": "Bearer " + session["access_token"]}
    assert session["user"]["must_change_password"]
    assert client.get("/api/v1/auth/me", headers=token).status_code == 200
    for path in ("/dashboard", "/alerts", "/incidents", "/users"):
        assert client.get("/api/v1" + path, headers=token).status_code == 403
    with client.websocket_connect("/ws/alerts", headers={"Origin": "http://localhost:5173"}) as ws:
        ws.send_json({"token": session["access_token"]})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    same = client.post(
        "/api/v1/auth/change-password",
        headers=token,
        json={"current_password": PASSWORD, "new_password": PASSWORD},
    )
    assert same.status_code == 400
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=token,
        json={"current_password": PASSWORD, "new_password": "Own-password-456!"},
    )
    assert changed.status_code == 204
    assert client.get("/api/v1/auth/me", headers=token).status_code == 401
    session = client.post(
        "/api/v1/auth/login", json={"email": created["email"], "password": "Own-password-456!"}
    ).json()
    assert not session["user"]["must_change_password"]
    assert (
        client.get(
            "/api/v1/dashboard", headers={"Authorization": "Bearer " + session["access_token"]}
        ).status_code
        == 200
    )


def test_production_mfa_setup_gate_covers_existing_accounts(client, tokens, monkeypatch):
    monkeypatch.setattr(get_settings(), "environment", "production")
    assert client.get("/api/v1/dashboard", headers=tokens["admin"]).status_code == 403
    assert client.get("/api/v1/auth/me", headers=tokens["admin"]).json()["mfa_required"]
    secret, codes = enroll(client, tokens["admin"])
    assert secret and codes
    session = login(client, codes[0]).json()
    assert (
        client.get(
            "/api/v1/dashboard", headers={"Authorization": "Bearer " + session["access_token"]}
        ).status_code
        == 200
    )


def test_mfa_secrets_are_encrypted_hidden_and_sessions_revoked(client, tokens, db):
    secret, codes = enroll(client, tokens["admin"])
    user = db.scalar(select(User).where(User.role == "ADMIN"))
    assert user.mfa_secret != secret and decrypt(user.mfa_secret) == secret
    assert all(code not in user.mfa_recovery_hashes for code in codes)
    assert client.get("/api/v1/auth/me", headers=tokens["admin"]).status_code == 401
    assert all(
        session.revoked
        for session in db.scalars(select(RefreshSession).where(RefreshSession.user_id == user.id))
    )
    assert secret not in repr([entry.details for entry in db.scalars(select(AuditLog))])
    new = login(client, codes[0]).json()
    headers = {"Authorization": "Bearer " + new["access_token"]}
    people = client.get("/api/v1/users", headers=headers)
    assert "mfa_secret" not in people.text and "mfa_recovery_hashes" not in people.text
    assert new["user"]["mfa_enabled"]


def test_mfa_login_requires_second_factor_and_rejects_replay(client, tokens, monkeypatch):
    fixed = (int(time.time()) // 30) * 30
    monkeypatch.setattr(time, "time", lambda: fixed)
    secret, codes = enroll(client, tokens["admin"])
    assert login(client).status_code == 401
    assert login(client, "000000").status_code == 401
    assert login(client, pyotp.TOTP(secret).at(fixed)).status_code == 401
    monkeypatch.setattr(time, "time", lambda: fixed + 30)
    otp = pyotp.TOTP(secret).at(fixed + 30)
    assert login(client, otp).status_code == 200
    assert login(client, otp).status_code == 401
    assert login(client, codes[0]).status_code == 200
    assert login(client, codes[0]).status_code == 401
    limiter.entries.clear()
    assert login(client, codes[1], password="wrong").status_code == 401
    limiter.entries.clear()
    assert login(client, codes[1]).status_code == 200


def test_mfa_setup_requires_password_and_pending_setup_expires(client, tokens, db):
    assert (
        client.post(
            "/api/v1/auth/mfa/setup", headers=tokens["admin"], json={"password": "wrong"}
        ).status_code
        == 400
    )
    setup = client.post(
        "/api/v1/auth/mfa/setup", headers=tokens["admin"], json={"password": PASSWORD}
    ).json()
    user = db.scalar(select(User).where(User.role == "ADMIN"))
    user.mfa_pending_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert (
        client.post(
            "/api/v1/auth/mfa/enable",
            headers=tokens["admin"],
            json={"code": pyotp.TOTP(setup["secret"]).now()},
        ).status_code
        == 409
    )


def test_account_disable_revokes_access_refresh_and_login(client, tokens, db):
    viewer = db.scalar(select(User).where(User.role == "VIEWER"))
    response = client.patch(
        f"/api/v1/users/{viewer.id}/access", headers=tokens["admin"], json={"disabled": True}
    )
    assert response.status_code == 200 and response.json()["disabled"]
    assert client.get("/api/v1/dashboard", headers=tokens["viewer"]).status_code == 401
    assert (
        client.post("/api/v1/auth/refresh").status_code == 401
    )  # tokens fixture's last cookie belongs to viewer
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": viewer.email, "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.patch(
            f"/api/v1/users/{viewer.id}/access", headers=tokens["analyst"], json={"disabled": False}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/users/{viewer.id}/access", headers=tokens["admin"], json={"disabled": False}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/dashboard", headers=tokens["viewer"]).status_code == 401


def test_mfa_recovery_consumption_is_atomic_on_postgres(client, tokens, db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Concurrent MFA row locks require PostgreSQL")
    _, codes = enroll(client, tokens["admin"])
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: login(client, codes[0]), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 401]


def test_concurrent_mfa_enable_cannot_replace_first_enrollment(client, tokens, db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Concurrent enrollment requires PostgreSQL row locks")
    setup = client.post(
        "/api/v1/auth/mfa/setup", headers=tokens["admin"], json={"password": PASSWORD}
    ).json()
    code = pyotp.TOTP(setup["secret"]).now()
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: client.post(
                    "/api/v1/auth/mfa/enable", headers=tokens["admin"], json={"code": code}
                ),
                range(2),
            )
        )
    statuses = sorted(response.status_code for response in responses)
    assert statuses[0] == 200 and statuses[1] in {401, 409}
    assert db.query(AuditLog).filter(AuditLog.action == "MFA_ENABLED").count() == 1


def test_refresh_and_enrollment_have_consistent_lock_order(client, tokens, db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Concurrent refresh/enrollment requires PostgreSQL")
    session = login(client).json()
    headers = {"Authorization": "Bearer " + session["access_token"]}
    cookie = client.cookies.get("sentinelx_refresh")
    setup = client.post(
        "/api/v1/auth/mfa/setup", headers=headers, json={"password": PASSWORD}
    ).json()
    code = pyotp.TOTP(setup["secret"]).now()

    def enable():
        return client.post("/api/v1/auth/mfa/enable", headers=headers, json={"code": code})

    def refresh():
        return client.post(
            "/api/v1/auth/refresh", headers={"Cookie": "sentinelx_refresh=" + cookie}
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        enabled = executor.submit(enable)
        refreshed = executor.submit(refresh)
        assert enabled.result().status_code == 200
        assert refreshed.result().status_code in {200, 401}


@pytest.mark.parametrize("operation", ["access", "role"])
def test_cross_administrator_edits_cannot_remove_every_active_admin(client, tokens, db, operation):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Cross-worker administration locks require PostgreSQL")
    administrator = db.scalar(select(User).where(User.role == "ADMIN"))
    teammate = db.scalar(select(User).where(User.role == "ANALYST"))
    teammate.role = "ADMIN"
    db.commit()

    def change(actor, target):
        suffix = "/access" if operation == "access" else ""
        payload = {"disabled": True} if operation == "access" else {"role": "VIEWER"}
        return client.patch(f"/api/v1/users/{target}{suffix}", headers=tokens[actor], json=payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(change, "admin", teammate.id)
        second = executor.submit(change, "analyst", administrator.id)
        statuses = sorted([first.result().status_code, second.result().status_code])
    assert statuses[0] == 200 and statuses[1] in {401, 403}
    db.expire_all()
    assert db.query(User).filter(User.role == "ADMIN", User.disabled.is_(False)).count() == 1


def test_administrator_cannot_disable_self(client, tokens):
    user = client.get("/api/v1/auth/me", headers=tokens["admin"]).json()
    assert (
        client.patch(
            f"/api/v1/users/{user['id']}/access", headers=tokens["admin"], json={"disabled": True}
        ).status_code
        == 409
    )
