from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings, get_settings
from app.core.security import limiter
from app.models import AuditLog, User
from tests.test_pipeline import event, send


def test_administrator_provisioning_never_grants_admin_on_creation(client, tokens):
    payload = {
        "name": "New viewer",
        "email": "new@example.com",
        "password": "A-strong-password-123",
        "role": "ADMIN",
    }
    assert (
        client.post("/api/v1/auth/register", headers=tokens["admin"], json=payload).status_code
        == 422
    )
    payload.pop("role")
    created = client.post("/api/v1/auth/register", headers=tokens["admin"], json=payload)
    assert created.status_code == 201
    assert created.json()["role"] == "VIEWER"
    assert "password_hash" not in created.json()
    assert (
        client.post("/api/v1/auth/register", headers=tokens["admin"], json=payload).status_code
        == 409
    )


@pytest.mark.parametrize("path", ["/auth/register", "/users"])
def test_only_administrators_can_admit_people(client, tokens, db, path):
    payload = {
        "name": "Uninvited person",
        "email": "uninvited@example.com",
        "password": "Test-password-123!",
    }
    before = db.query(User).count()
    assert client.post("/api/v1" + path, json=payload).status_code == 401
    for role in ("viewer", "analyst"):
        assert client.post("/api/v1" + path, headers=tokens[role], json=payload).status_code == 403
    assert db.query(User).count() == before
    assert db.query(User).filter(User.email == payload["email"]).first() is None


def test_admin_created_person_is_audited_without_password_and_can_sign_in(client, tokens, db):
    payload = {
        "name": "  Trusted person  ",
        "email": "TRUSTED@example.com",
        "password": "Starter-password-123!",
    }
    created = client.post("/api/v1/users", headers=tokens["admin"], json=payload)
    assert created.status_code == 201
    assert created.json()["role"] == "VIEWER"
    assert created.json()["name"] == "Trusted person"
    assert created.json()["email"] == "trusted@example.com"
    assert "password_hash" not in created.json()
    assert payload["password"] not in created.text
    assert created.json()["must_change_password"]
    row = db.get(User, created.json()["id"])
    assert row.password_hash.startswith("$argon2id$")
    entry = db.query(AuditLog).filter(AuditLog.action == "CREATE_USER").one()
    assert entry.user_id != row.id and entry.resource_id == str(row.id)
    assert entry.details == {"role": "VIEWER"}
    login = client.post(
        "/api/v1/auth/login", json={"email": row.email, "password": payload["password"]}
    )
    assert login.status_code == 200 and login.json()["user"]["role"] == "VIEWER"
    assert client.post("/api/v1/users", headers=tokens["admin"], json=payload).status_code == 409


def test_new_user_input_validation_and_no_role_mass_assignment(client, tokens):
    payload = {
        "name": "New person",
        "email": "new-person@example.com",
        "password": "Starter-password-123!",
    }
    for change in ({"role": "ADMIN"}, {"password": "short"}, {"name": "   "}):
        assert (
            client.post(
                "/api/v1/users", headers=tokens["admin"], json={**payload, **change}
            ).status_code
            == 422
        )


def test_api_documentation_is_disabled_by_default(client):
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404


def test_untrusted_host_is_rejected(client):
    assert client.get("/api/v1/dashboard", headers={"Host": "untrusted.example"}).status_code == 400
    assert client.get("/health/live", headers={"Host": "untrusted.example"}).status_code == 400


def test_public_host_and_docs_configuration_fail_closed():
    with pytest.raises(ValueError, match="without wildcards"):
        Settings(_env_file=None, allowed_hosts="*")
    with pytest.raises(ValueError, match="documentation"):
        Settings(_env_file=None, environment="production", api_docs_enabled=True)


def production_settings(**changes):
    return Settings(
        _env_file=None,
        **{
            "environment": "production",
            "jwt_secret": "test-only-secret-with-at-least-32-characters",
            "cookie_secure": True,
            # Deterministic test-only Fernet key, never used for deployment.
            "mfa_encryption_key": "dGVzdC1vbmx5LW1mYS1lbmNyeXB0aW9uLWtleS0xMjM=",  # gitleaks:allow
            "database_url": "postgresql+psycopg://localhost/disposable_test",
            "redis_url": "redis://localhost:6379/0",
            "allowed_hosts": "sentinelx.example,localhost,127.0.0.1",
            "allowed_origins": "https://sentinelx.example:8443",
            "api_docs_enabled": False,
            "demo_mode": False,
            "seed_demo": False,
            **changes,
        },
    )


def test_production_accepts_exact_https_origin_and_hostname():
    settings = production_settings()
    assert settings.origins == ["https://sentinelx.example:8443"]
    assert settings.cookie_secure and not settings.api_docs_enabled


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "http://sentinelx.example",
        "https://untrusted.example",
        "https://sentinelx.example/path",
        "https://sentinelx.example/",
        "https://user:password@sentinelx.example",
        "https://sentinelx.example?query=1",
        "https://sentinelx.example#fragment",
        "https://sentinelx.example:99999",
    ],
)
def test_production_rejects_invalid_or_untrusted_origins(origin):
    with pytest.raises(ValueError):
        production_settings(allowed_origins=origin)


def test_password_hash_is_argon2id(client, db):
    user = db.query(User).filter(User.role == "ADMIN").one()
    assert user.password_hash.startswith("$argon2id$")
    assert "Test-password" not in user.password_hash


@pytest.mark.parametrize("path", ["/events", "/rules", "/assets", "/users", "/audit-logs"])
def test_viewer_cannot_access_restricted_data(client, tokens, path):
    assert client.get("/api/v1" + path, headers=tokens["viewer"]).status_code == 403


@pytest.mark.parametrize("path", ["/dashboard", "/alerts", "/incidents", "/auth/me"])
def test_viewer_can_read_soc_pages(client, tokens, path):
    assert client.get("/api/v1" + path, headers=tokens["viewer"]).status_code == 200


def test_viewer_cannot_ingest_or_modify_and_analyst_cannot_admin(client, tokens):
    assert client.post("/api/v1/events", headers=tokens["viewer"], json=event()).status_code == 403
    assert (
        client.post(
            "/api/v1/ai/analyze-incident", headers=tokens["viewer"], json={"incident_id": 1}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/rules",
            headers=tokens["analyst"],
            json={"name": "Forbidden", "event_type": "test"},
        ).status_code
        == 403
    )


def test_missing_invalid_and_expired_jwt(client, tokens):
    assert client.get("/api/v1/dashboard").status_code == 401
    assert (
        client.get("/api/v1/dashboard", headers={"Authorization": "Bearer invalid"}).status_code
        == 401
    )
    raw = tokens["admin"]["Authorization"].split()[1]
    payload = jwt.decode(raw, options={"verify_signature": False})
    payload["iat"] = datetime.now(UTC) - timedelta(hours=1)
    payload["exp"] = datetime.now(UTC) - timedelta(minutes=1)
    expired = jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")
    assert (
        client.get("/api/v1/dashboard", headers={"Authorization": f"Bearer {expired}"}).status_code
        == 401
    )


def test_refresh_rotation_and_replay_revokes_family(client):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@sentinelx.dev", "password": "Test-password-123!"},
    )
    old_cookie = client.cookies.get("sentinelx_refresh")
    assert (
        "HttpOnly" in login.headers["set-cookie"]
        and "SameSite=strict" in login.headers["set-cookie"]
    )
    rotated = client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    assert client.cookies.get("sentinelx_refresh") != old_cookie
    old_access = login.json()["access_token"]
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_access}"}).status_code
        == 200
    )
    replay = client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"sentinelx_refresh={old_cookie}"}
    )
    assert replay.status_code == 401
    new_access = rotated.json()["access_token"]
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"}).status_code
        == 401
    )


def test_logout_revokes_access_immediately(client):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@sentinelx.dev", "password": "Test-password-123!"},
    ).json()
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"}
        ).status_code
        == 401
    )


def test_password_change_revokes_all_sessions(client, tokens):
    response = client.post(
        "/api/v1/auth/change-password",
        headers=tokens["admin"],
        json={"current_password": "Test-password-123!", "new_password": "New-password-456!"},
    )
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me", headers=tokens["admin"]).status_code == 401


def test_csrf_origin_and_body_limit(client, tokens):
    assert (
        client.post("/api/v1/auth/refresh", headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert (
        client.post("/api/v1/events", headers=tokens["admin"], content="x" * 300000).status_code
        == 413
    )


def test_rate_limit(client):
    limiter.check("unit", 2)
    limiter.check("unit", 2)
    with pytest.raises(Exception) as error:
        limiter.check("unit", 2)
    assert error.value.status_code == 429


def test_input_and_ai_validation(client, tokens):
    assert (
        client.post(
            "/api/v1/events", headers=tokens["admin"], json=event(source_ip="not an ip")
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/events", headers=tokens["admin"], json=event(timestamp="2026-01-01T00:00:00")
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/events",
            headers=tokens["admin"],
            json=event(metadata={"destination_port": "22"}),
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/ai/analyze-incident", headers=tokens["admin"], json={"incident_id": 0}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/ai/analyze-incident", headers=tokens["admin"], json={"incident_id": 999}
        ).status_code
        == 404
    )


def test_xss_is_stored_as_data_not_html(client, tokens):
    result = send(client, tokens, event(message='<script>alert("xss")</script>'))
    response = client.get(f"/api/v1/events/{result['event']['id']}", headers=tokens["analyst"])
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["message"] == '<script>alert("xss")</script>'


def test_simulator_disabled_and_production_configuration(client, tokens):
    assert client.post("/api/v1/demo/simulate", headers=tokens["admin"]).status_code == 404
    with pytest.raises(ValueError):
        Settings(_env_file=None, environment="production", jwt_secret="short")


def test_admin_cannot_demote_self(client, tokens):
    me = client.get("/api/v1/auth/me", headers=tokens["admin"]).json()
    assert (
        client.patch(
            f"/api/v1/users/{me['id']}", headers=tokens["admin"], json={"role": "VIEWER"}
        ).status_code
        == 409
    )
