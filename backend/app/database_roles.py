"""Explicit selected-database provisioning; never imported by the runtime application."""

import argparse
import os

import psycopg
from psycopg import sql

MIGRATOR = "sentinelx_migrator"
RUNTIME = "sentinelx_runtime"
NOTIFIER = "sentinelx_notifier"
TABLES = {
    "users",
    "refresh_sessions",
    "events",
    "log_sources",
    "source_receipts",
    "detection_rules",
    "incidents",
    "alerts",
    "incident_events",
    "incident_notes",
    "assets",
    "iocs",
    "incident_iocs",
    "audit_logs",
    "alembic_version",
    "notification_outbox",
    "webauthn_credentials",
    "webauthn_challenges",
}
APPEND_ONLY = {
    "events",
    "source_receipts",
    "incident_events",
    "incident_notes",
    "incident_iocs",
    "audit_logs",
    "notification_outbox",
}
MUTABLE_NO_DELETE = {
    "users",
    "refresh_sessions",
    "log_sources",
    "incidents",
    "alerts",
    "assets",
    "iocs",
}


def grant_runtime(connection):
    tables = connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    ).fetchall()
    for (name,) in tables:
        if name not in TABLES:
            continue
        privileges = (
            "SELECT"
            if name == "alembic_version"
            else (
                "SELECT, INSERT"
                if name in APPEND_ONLY
                else (
                    "SELECT, INSERT, UPDATE"
                    if name in MUTABLE_NO_DELETE
                    else "SELECT, INSERT, UPDATE, DELETE"
                )
            )
        )
        connection.execute(
            sql.SQL("REVOKE ALL ON TABLE public.{} FROM PUBLIC, {}, {}").format(
                sql.Identifier(name), sql.Identifier(RUNTIME), sql.Identifier(NOTIFIER)
            )
        )
        connection.execute(
            sql.SQL("GRANT {} ON TABLE public.{} TO {}").format(
                sql.SQL(privileges), sql.Identifier(name), sql.Identifier(RUNTIME)
            )
        )
    sequences = connection.execute(
        "SELECT s.relname, t.relname FROM pg_class s "
        "JOIN pg_namespace n ON n.oid=s.relnamespace "
        "JOIN pg_depend d ON d.objid=s.oid AND d.classid='pg_class'::regclass "
        "AND d.refclassid='pg_class'::regclass AND d.deptype IN ('a','i') "
        "JOIN pg_class t ON t.oid=d.refobjid WHERE s.relkind='S' AND n.nspname='public'"
    ).fetchall()
    for name, table in sequences:
        if table in TABLES:
            connection.execute(
                sql.SQL("REVOKE ALL ON SEQUENCE public.{} FROM PUBLIC, {}, {}").format(
                    sql.Identifier(name), sql.Identifier(RUNTIME), sql.Identifier(NOTIFIER)
                )
            )
            connection.execute(
                sql.SQL("GRANT USAGE, SELECT ON SEQUENCE public.{} TO {}").format(
                    sql.Identifier(name), sql.Identifier(RUNTIME)
                )
            )
    if any(name == "notification_outbox" for (name,) in tables):
        connection.execute(
            sql.SQL(
                "GRANT SELECT, UPDATE (attempts,next_attempt_at,delivered_at,lease_owner,lease_until,last_error) "
                "ON TABLE public.notification_outbox TO {}"
            ).format(sql.Identifier(NOTIFIER))
        )


def provision(connection, database, migrator_password, runtime_password, notifier_password=""):
    if (
        min(len(migrator_password), len(runtime_password)) < 24
        or migrator_password == runtime_password
    ):
        raise ValueError("Supply distinct migration/runtime passwords of at least 24 characters")
    if notifier_password and (
        len(notifier_password) < 24 or notifier_password in {migrator_password, runtime_password}
    ):
        raise ValueError("Supply an independent notifier credential of at least 24 characters")
    if connection.execute("SELECT current_database()").fetchone()[0] != database:
        raise ValueError("Connection does not match the explicitly selected database")
    # Fixed role names are cluster-wide. Never silently rotate another database's credentials.
    shared = connection.execute(
        "SELECT 1 FROM pg_shdepend d JOIN pg_roles r ON d.refobjid=r.oid "
        "WHERE d.refclassid='pg_authid'::regclass AND r.rolname IN (%s,%s,%s) "
        "AND ((d.dbid != 0 AND d.dbid != (SELECT oid FROM pg_database WHERE datname=current_database())) "
        "OR (d.dbid=0 AND d.classid='pg_database'::regclass "
        "AND d.objid != (SELECT oid FROM pg_database WHERE datname=current_database()))) LIMIT 1",
        (MIGRATOR, RUNTIME, NOTIFIER),
    ).fetchone()
    if shared:
        raise ValueError(
            "Use a dedicated PostgreSQL cluster; production roles already serve another database"
        )
    for role, password in ((MIGRATOR, migrator_password), (RUNTIME, runtime_password)):
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
        connection.execute(
            sql.SQL(
                "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
                "NOREPLICATION NOBYPASSRLS PASSWORD {}"
            ).format(sql.Identifier(role), sql.Literal(password))
        )
        if connection.execute(
            "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=%s",
            (role,),
        ).fetchone():
            raise ValueError("Provisioned roles must not have inherited role memberships")
    if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (NOTIFIER,)).fetchone():
        connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(NOTIFIER)))
    connection.execute(
        sql.SQL(
            "ALTER ROLE {} {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
        ).format(sql.Identifier(NOTIFIER), sql.SQL("LOGIN" if notifier_password else "NOLOGIN"))
    )
    if notifier_password:
        connection.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(NOTIFIER), sql.Literal(notifier_password)
            )
        )
    if connection.execute(
        "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=%s",
        (NOTIFIER,),
    ).fetchone():
        raise ValueError("Notifier role must not have inherited memberships")
    connection.execute(
        sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database))
    )
    connection.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
            sql.Identifier(database), sql.Identifier(MIGRATOR), sql.Identifier(RUNTIME)
        )
    )
    connection.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    connection.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(database), sql.Identifier(NOTIFIER)
        )
    )
    connection.execute(
        sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(NOTIFIER))
    )
    connection.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(MIGRATOR)))
    connection.execute(
        sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(RUNTIME))
    )
    # Transfer only recognized application objects in the explicitly selected database.
    for (name,) in connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'"):
        if name in TABLES:
            connection.execute(
                sql.SQL("ALTER TABLE public.{} OWNER TO {}").format(
                    sql.Identifier(name), sql.Identifier(MIGRATOR)
                )
            )
    grant_runtime(connection)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database", required=True)
    args = parser.parse_args()
    database = os.environ["POSTGRES_DATABASE"]
    if args.confirm_database != database or not args.apply:
        parser.error("Role provisioning requires --apply and the exact selected database")
    try:
        with psycopg.connect(
            host="postgres",
            dbname=database,
            user="sentinelx",
            password=os.environ["POSTGRES_PASSWORD"],
        ) as connection:
            provision(
                connection,
                database,
                os.environ["POSTGRES_MIGRATION_PASSWORD"],
                os.environ["POSTGRES_RUNTIME_PASSWORD"],
                os.environ.get("POSTGRES_NOTIFICATION_PASSWORD", ""),
            )
    except Exception:
        # Connection errors can contain credentials; retain them only in an approved private debugger.
        raise SystemExit(
            "Selected-database role provisioning failed; review private diagnostics"
        ) from None
    print("Selected-database migration/runtime roles provisioned; no application records replaced.")


if __name__ == "__main__":
    main()
