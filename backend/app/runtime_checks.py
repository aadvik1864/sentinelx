"""Read-only role checks and harmless denied-operation probes on a disposable fixture only."""

import json
import os
import sys

import psycopg
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def probe():
    from app.core.database import engine

    if engine.url.database != "sentinelx_release_test":
        raise ValueError(
            "Denied-operation probes are restricted to the disposable release database"
        )
    if any(
        name in os.environ
        for name in (
            "POSTGRES_PASSWORD",
            "POSTGRES_MIGRATION_PASSWORD",
            "BOOTSTRAP_ADMIN_PASSWORD",
            "POSTGRES_NOTIFICATION_PASSWORD",
        )
    ):
        raise ValueError("Privileged bootstrap/migration secrets reached the runtime container")
    denied = []
    for statement in (
        "CREATE TABLE public.fixture_privilege_probe (id integer)",
        "ALTER TABLE public.events ADD COLUMN fixture_privilege_probe integer",
        "CREATE ROLE fixture_privilege_probe",
        "DELETE FROM public.audit_logs WHERE false",
        "UPDATE public.audit_logs SET action=action WHERE false",
        "UPDATE public.alembic_version SET version_num=version_num WHERE false",
        "DELETE FROM public.events WHERE false",
        "UPDATE public.events SET message=message WHERE false",
        "DELETE FROM public.source_receipts WHERE false",
        "UPDATE public.source_receipts SET payload_hash=payload_hash WHERE false",
        "SELECT pg_read_file('PG_VERSION')",
    ):
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text(statement))
            except DBAPIError as error:
                if getattr(error.orig, "sqlstate", "") != "42501":
                    raise ValueError("Fixture probe did not produce a permission denial") from None
                denied.append(True)
            else:
                raise ValueError("Runtime privilege boundary failed")
            finally:
                transaction.rollback()
    return {"runtime_privilege_denials": len(denied), "privileged_secrets_absent": True}


def probe_notifier():
    if os.environ.get("POSTGRES_DATABASE") != "sentinelx_release_test":
        raise ValueError("Notifier probes require the explicitly selected disposable database")
    denied = 0
    with psycopg.connect(
        host="postgres",
        dbname="sentinelx_release_test",
        user="sentinelx_notifier",
        password=os.environ["POSTGRES_NOTIFICATION_PASSWORD"],
    ) as connection:
        for statement in (
            "SELECT * FROM public.users WHERE false",
            "SELECT * FROM public.events WHERE false",
            "SELECT * FROM public.audit_logs WHERE false",
            "UPDATE public.notification_outbox SET payload=payload WHERE false",
            "DELETE FROM public.notification_outbox WHERE false",
            "CREATE TABLE public.fixture_notifier_probe (id integer)",
        ):
            try:
                with connection.transaction():
                    connection.execute(statement)
                    raise ValueError("Notifier privilege boundary failed")
            except psycopg.errors.InsufficientPrivilege:
                denied += 1
        connection.execute(
            "SELECT id FROM public.notification_outbox WHERE false FOR UPDATE SKIP LOCKED"
        )
        connection.execute("UPDATE public.notification_outbox SET attempts=attempts WHERE false")
    return {"notifier_privilege_denials": denied, "notifier_delivery_grants_verified": True}


if __name__ == "__main__":
    print(json.dumps(probe_notifier() if sys.argv[1:] == ["--notifier"] else probe()))
