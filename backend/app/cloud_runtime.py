"""Start the Render API using only its restricted runtime database identity."""

import os
import sys

from sqlalchemy import URL


def main():
    os.environ["DATABASE_URL"] = URL.create(
        "postgresql+psycopg",
        username="sentinelx_runtime",
        password=os.environ["POSTGRES_RUNTIME_PASSWORD"],
        host=os.environ["DATABASE_HOST"],
        port=int(os.environ.get("DATABASE_PORT", "5432")),
        database=os.environ["DATABASE_NAME"],
        query={"sslmode": "require"},
    ).render_as_string(hide_password=False)
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            os.environ.get("PORT", "10000"),
            "--proxy-headers",
            "--forwarded-allow-ips",
            "*",
        ],
    )


if __name__ == "__main__":
    main()
