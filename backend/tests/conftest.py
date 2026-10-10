import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

temporary_root = Path(tempfile.gettempdir())
temporary_root.mkdir(parents=True, exist_ok=True)
test_directory = tempfile.TemporaryDirectory(prefix="sentinelx-tests-", dir=temporary_root)
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = (
    os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{test_directory.name}/tests.db"
)
os.environ["JWT_SECRET"] = "test-only-secret-with-at-least-32-characters"
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = "admin@sentinelx.dev"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "Test-password-123!"
os.environ["REDIS_URL"] = ""
os.environ["SEED_DEMO"] = "false"
os.environ["DEMO_MODE"] = "false"
os.environ["LIVE_MONITORING"] = "false"
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = "auto"
os.environ["ABUSEIPDB_API_KEY"] = ""
os.environ["COOKIE_SECURE"] = "false"
os.environ["API_DOCS_ENABLED"] = "false"
os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password, limiter  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402

PASSWORD = "Test-password-123!"


@pytest.fixture
def client():
    # TEST_DATABASE_URL must point to a dedicated, disposable test database.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    limiter.entries.clear()
    with TestClient(app, headers={"Origin": "http://localhost:5173"}) as test_client:
        with SessionLocal() as db:
            for name, role in [("analyst", "ANALYST"), ("viewer", "VIEWER")]:
                db.add(
                    User(
                        name=name,
                        email=f"{name}@sentinelx.dev",
                        role=role,
                        password_hash=hash_password(PASSWORD),
                    )
                )
            db.commit()
        yield test_client


@pytest.fixture
def tokens(client):
    result = {}
    for name in ["admin", "analyst", "viewer"]:
        response = client.post(
            "/api/v1/auth/login", json={"email": f"{name}@sentinelx.dev", "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        result[name] = {"Authorization": f"Bearer {response.json()['access_token']}"}
    return result


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def admin_user(db):
    return db.scalar(select(User).where(User.role == "ADMIN"))
