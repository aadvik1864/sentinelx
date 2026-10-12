"""A populated pre-release schema must migrate without replacing existing records."""

import os
import sqlite3
import subprocess
from pathlib import Path


def test_populated_upgrade_preserves_accounts_and_receipts(tmp_path):
    directory = Path(__file__).resolve().parents[1]
    path = tmp_path / "migration.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path}", "ENVIRONMENT": "test"}
    command = [os.sys.executable, "-m", "alembic", "upgrade"]
    subprocess.run(
        command + ["0003_log_sources"], cwd=directory, env=env, check=True, capture_output=True
    )
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO users (id,name,email,password_hash,role,auth_version,created_at,updated_at) VALUES (1,'Preserved','preserved@example.com','test-only-existing-hash','ADMIN',4,'2026-01-01','2026-01-01')"
        )
        db.execute(
            "INSERT INTO events (id,timestamp,source,event_type,severity,hostname,message,metadata,created_at) VALUES (31,'2026-01-01','linux','fixture','low','fixture','preserved evidence','{}','2026-01-01')"
        )
        db.execute(
            "INSERT INTO log_sources (id,name,kind,hostname,log_path,enabled,token_hash,created_at,last_error,total_events) VALUES (2,'Preserved source','linux','fixture','/fixture',1,'test-only-preserved-token-hash','2026-01-01','',1)"
        )
        db.execute(
            "INSERT INTO source_receipts (source_id,record_key,payload_hash,event_id) VALUES (2,'preserved-record','test-only-payload-hash',31)"
        )
    subprocess.run(command + ["head"], cwd=directory, env=env, check=True, capture_output=True)
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT name,email,password_hash,role,auth_version FROM users"
        ).fetchone() == (
            "Preserved",
            "preserved@example.com",
            "test-only-existing-hash",
            "ADMIN",
            4,
        )
        assert db.execute(
            "SELECT disabled,must_change_password,mfa_secret FROM users"
        ).fetchone() == (0, 0, None)
        assert db.execute("SELECT id,message FROM events").fetchone() == (31, "preserved evidence")
        assert db.execute("SELECT token_hash,total_events FROM log_sources").fetchone() == (
            "test-only-preserved-token-hash",
            1,
        )
        assert db.execute(
            "SELECT token_expires_at,previous_token_hash,previous_token_expires_at FROM log_sources"
        ).fetchone() == (None, None, None)
        assert db.execute("SELECT mfa_webauthn_handle FROM users").fetchone() == (None,)
        assert db.execute("SELECT count(*) FROM notification_outbox").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM webauthn_credentials").fetchone() == (0,)
        assert db.execute("SELECT event_id,record_key FROM source_receipts").fetchone() == (
            31,
            "preserved-record",
        )
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0008_receipt_metrics",
        )
