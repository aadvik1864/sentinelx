import os
import secrets
import subprocess
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from app.core.database import engine
from app.database_roles import MIGRATOR, NOTIFIER, RUNTIME, provision


@pytest.mark.parametrize(
    "first,second", [("short", "x" * 32), ("x" * 32, "short"), ("x" * 32, "x" * 32)]
)
def test_role_provisioning_rejects_shared_or_weak_credentials_before_any_query(first, second):
    class Connection:
        def execute(self, *args, **kwargs):
            raise AssertionError("No database operations are allowed for invalid inputs")

    with pytest.raises(ValueError):
        provision(Connection(), "fixture", first, second)


def test_populated_postgres_upgrade_and_runtime_notifier_grants():
    if engine.dialect.name != "postgresql" or engine.url.database != "sentinelx_test":
        pytest.skip("Requires the explicitly disposable CI PostgreSQL cluster")
    url = engine.url
    options = {"host": url.host, "port": url.port, "user": url.username, "password": url.password}
    database = "sentinelx_roles_" + secrets.token_hex(6)
    other = database + "_other"
    passwords = {role: secrets.token_urlsafe(32) for role in (MIGRATOR, RUNTIME, NOTIFIER)}
    with psycopg.connect(dbname=url.database, autocommit=True, **options) as administrator:
        if administrator.execute(
            "SELECT 1 FROM pg_roles WHERE rolname IN (%s,%s,%s)", (MIGRATOR, RUNTIME, NOTIFIER)
        ).fetchone():
            pytest.skip("Never alter previously existing production role identities")
        administrator.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            directory = Path(__file__).resolve().parents[1]
            environment = {
                **os.environ,
                "DATABASE_URL": url.set(database=database).render_as_string(hide_password=False),
                "ENVIRONMENT": "test",
            }
            command = [os.sys.executable, "-m", "alembic", "upgrade"]
            subprocess.run(
                command + ["0005_receipt_tombstones"],
                cwd=directory,
                env=environment,
                check=True,
                capture_output=True,
            )
            with psycopg.connect(dbname=database, **options) as connection:
                connection.execute(
                    "INSERT INTO users (id,name,email,password_hash,role,auth_version,must_change_password,disabled,mfa_secret,mfa_last_step,mfa_recovery_hashes,created_at,updated_at) VALUES (1,'Preserved','preserved@example.com','test-only-existing-hash','ADMIN',4,false,false,'test-only-encrypted-seed',42,'[\"test-only-recovery-digest\"]','2026-01-01','2026-01-01')"
                )
                connection.execute(
                    "INSERT INTO log_sources (id,name,kind,hostname,log_path,enabled,token_hash,created_at,last_error,total_events) VALUES (2,'Preserved source','linux','fixture','/fixture',true,'test-only-preserved-token-hash','2026-01-01','',0)"
                )
                connection.execute("CREATE TABLE public.unrelated_fixture (id serial PRIMARY KEY)")
                before = connection.execute(
                    "SELECT password_hash,role,auth_version,mfa_secret,mfa_last_step,mfa_recovery_hashes FROM users"
                ).fetchone()
                provision(
                    connection,
                    database,
                    passwords[MIGRATOR],
                    passwords[RUNTIME],
                    passwords[NOTIFIER],
                )
            environment["DATABASE_URL"] = url.set(
                database=database, username=MIGRATOR, password=passwords[MIGRATOR]
            ).render_as_string(hide_password=False)
            subprocess.run(
                command + ["head"], cwd=directory, env=environment, check=True, capture_output=True
            )
            # Grant as the schema owner, not the bootstrap administrator.
            from app.database_roles import grant_runtime

            with psycopg.connect(
                dbname=database,
                host=url.host,
                port=url.port,
                user=MIGRATOR,
                password=passwords[MIGRATOR],
            ) as connection:
                grant_runtime(connection)
                assert (
                    connection.execute(
                        "SELECT password_hash,role,auth_version,mfa_secret,mfa_last_step,mfa_recovery_hashes FROM users"
                    ).fetchone()
                    == before
                )
                assert connection.execute(
                    "SELECT token_hash,token_expires_at FROM log_sources"
                ).fetchone() == ("test-only-preserved-token-hash", None)
            with psycopg.connect(
                dbname=database,
                host=url.host,
                port=url.port,
                user=RUNTIME,
                password=passwords[RUNTIME],
            ) as connection:
                connection.execute(
                    "INSERT INTO audit_logs(action,resource,resource_id,metadata,timestamp) VALUES('FIXTURE','fixture','0','{}',CURRENT_TIMESTAMP)"
                )
                connection.execute(
                    "INSERT INTO events(timestamp,source,event_type,severity,hostname,message,metadata,created_at) VALUES(CURRENT_TIMESTAMP,'linux','fixture','low','fixture','fixture','{}',CURRENT_TIMESTAMP)"
                )
                for statement in (
                    "DELETE FROM events WHERE false",
                    "UPDATE source_receipts SET payload_hash=payload_hash WHERE false",
                    "CREATE TABLE public.forbidden_fixture(id integer)",
                    "UPDATE audit_logs SET action=action WHERE false",
                    "SELECT nextval('public.unrelated_fixture_id_seq')",
                ):
                    with (
                        pytest.raises(psycopg.errors.InsufficientPrivilege),
                        connection.transaction(),
                    ):
                        connection.execute(statement)
            with psycopg.connect(
                dbname=database,
                host=url.host,
                port=url.port,
                user=NOTIFIER,
                password=passwords[NOTIFIER],
            ) as connection:
                connection.execute(
                    "SELECT id FROM notification_outbox WHERE false FOR UPDATE SKIP LOCKED"
                )
                connection.execute("UPDATE notification_outbox SET attempts=attempts WHERE false")
                for statement in (
                    "SELECT * FROM users",
                    "UPDATE notification_outbox SET payload=payload WHERE false",
                    "DELETE FROM notification_outbox WHERE false",
                ):
                    with (
                        pytest.raises(psycopg.errors.InsufficientPrivilege),
                        connection.transaction(),
                    ):
                        connection.execute(statement)
            administrator.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(other)))
            administrator.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(other), sql.Identifier(RUNTIME)
                )
            )
            with psycopg.connect(dbname=database, **options) as connection:
                with pytest.raises(ValueError, match="dedicated PostgreSQL cluster"):
                    provision(
                        connection,
                        database,
                        passwords[MIGRATOR],
                        passwords[RUNTIME],
                        passwords[NOTIFIER],
                    )
        finally:
            for name in (other, database):
                administrator.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name))
                )
            for role in (MIGRATOR, RUNTIME, NOTIFIER):
                if administrator.execute(
                    "SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)
                ).fetchone():
                    administrator.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
