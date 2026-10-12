"""One-shot migration/bootstrap job. Its credentials are not supplied to the API container."""

import psycopg
from alembic import command
from alembic.config import Config

from app.core.database import SessionLocal, engine
from app.database_roles import grant_runtime
from app.seed import bootstrap


def main():
    command.upgrade(Config("alembic.ini"), "head")
    with SessionLocal() as db:
        bootstrap(db)
    url = engine.url
    with psycopg.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=engine.url.password,
    ) as connection:
        grant_runtime(connection)
    print("Selected-database migration/bootstrap finished; runtime privileges granted.")


if __name__ == "__main__":
    main()
