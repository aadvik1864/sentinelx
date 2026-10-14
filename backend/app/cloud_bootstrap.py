"""Initialize a new dedicated managed database, outside the API service."""

import argparse
import os

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.database_roles import MIGRATOR, NOTIFIER, RUNTIME, grant_runtime


def provision_new_database(connection, database, migration_password, runtime_password):
    """Create restricted roles without requiring a provider's superuser identity."""
    if (
        min(len(migration_password), len(runtime_password)) < 24
        or migration_password == runtime_password
    ):
        raise ValueError("Supply distinct migration/runtime passwords of at least 24 characters")
    if connection.execute("SELECT current_database()").fetchone()[0] != database:
        raise ValueError("Connection must match the explicitly confirmed database")
    if connection.execute("SELECT 1 FROM pg_tables WHERE schemaname='public' LIMIT 1").fetchone():
        raise ValueError("Cloud initialization requires a new empty database")
    if connection.execute(
        "SELECT 1 FROM pg_roles WHERE rolname IN (%s,%s,%s)", (MIGRATOR, RUNTIME, NOTIFIER)
    ).fetchone():
        raise ValueError(
            "Cloud initialization requires a dedicated cluster without existing SentinelX roles"
        )
    # New roles default to NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION,
    # and NOBYPASSRLS. Managed owners cannot ALTER superuser-only attributes.
    for role, password in ((MIGRATOR, migration_password), (RUNTIME, runtime_password)):
        connection.execute(
            sql.SQL("CREATE ROLE {} LOGIN NOINHERIT PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
    connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(sql.Identifier(NOTIFIER)))
    owner = connection.execute("SELECT current_user").fetchone()[0]
    # PostgreSQL 16+ grants a creator ADMIN access, but not SET access by default.
    # The database owner must be able to transfer this database's schema to the migrator.
    connection.execute(
        sql.SQL("GRANT {} TO {} WITH SET TRUE, INHERIT FALSE").format(
            sql.Identifier(MIGRATOR), sql.Identifier(owner)
        )
    )
    connection.execute(
        sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database))
    )
    connection.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}, {}").format(
            sql.Identifier(database),
            sql.Identifier(MIGRATOR),
            sql.Identifier(RUNTIME),
            sql.Identifier(NOTIFIER),
        )
    )
    connection.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    connection.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(MIGRATOR)))
    connection.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(MIGRATOR)))
    connection.execute(
        sql.SQL("GRANT USAGE ON SCHEMA public TO {}, {}").format(
            sql.Identifier(RUNTIME), sql.Identifier(NOTIFIER)
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-host", required=True)
    parser.add_argument("--confirm-database", required=True)
    args = parser.parse_args()
    admin = make_url(os.environ["CLOUD_ADMIN_DATABASE_URL"])
    if admin.host != args.confirm_host or admin.database != args.confirm_database:
        parser.error("Confirm the exact new managed database host and database name")
    if not os.environ.get("BOOTSTRAP_ADMIN_PASSWORD"):
        parser.error("A privately generated starter password is required")
    admin_dsn = admin.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn) as connection:
        provision_new_database(
            connection,
            admin.database,
            os.environ["POSTGRES_MIGRATION_PASSWORD"],
            os.environ["POSTGRES_RUNTIME_PASSWORD"],
        )
    migration = admin.set(
        drivername="postgresql+psycopg",
        username=MIGRATOR,
        password=os.environ["POSTGRES_MIGRATION_PASSWORD"],
    )
    os.environ["DATABASE_URL"] = migration.render_as_string(hide_password=False)
    from alembic import command
    from alembic.config import Config

    from app.core.database import SessionLocal
    from app.seed import bootstrap

    command.upgrade(Config("alembic.ini"), "head")
    with SessionLocal() as session:
        bootstrap(session)
    with psycopg.connect(
        migration.set(drivername="postgresql").render_as_string(hide_password=False)
    ) as connection:
        grant_runtime(connection)
    print(
        "New cloud database migrated and administrator created; restricted runtime grants applied."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(
            "Cloud initialization failed; inspect private diagnostics before retrying."
        ) from None
