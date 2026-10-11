"""Stream PostgreSQL backups through age; restore only into a new disposable database.

Requires Docker Compose and age on the operator workstation. No plaintext dump is
written and no existing database is overwritten or deleted.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


def database_name(value):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", value):
        raise argparse.ArgumentTypeError("Use a simple PostgreSQL database identifier")
    return value


def pipe(producer, consumer, *, output=None):
    first = subprocess.Popen(producer, stdout=subprocess.PIPE)
    try:
        second = subprocess.Popen(consumer, stdin=first.stdout, stdout=output)
    except BaseException:
        first.stdout.close()
        first.terminate()
        first.wait()
        raise
    first.stdout.close()
    result = second.wait()
    source_result = first.wait()
    if result or source_result:
        raise RuntimeError("Backup/restore pipeline failed; the output is not verified")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--compose-file", action="append", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--database", type=database_name, required=True)
    backup.add_argument(
        "--recipient", required=True, help="Public age recipient, never an identity key"
    )
    backup.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("restore-drill")
    restore.add_argument("--database", type=database_name, required=True)
    restore.add_argument("--identity-file", type=Path, required=True)
    restore.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    compose = [
        "docker",
        "compose",
        "--project-name",
        args.project,
        "--env-file",
        str(args.env_file),
    ]
    for file in args.compose_file:
        compose += ["-f", file]
    postgres = compose + ["exec", "-T", "postgres"]
    if args.command == "backup":
        if args.output.suffix != ".age":
            parser.error("Encrypted backup output must end in .age")
        # Exclusive creation refuses existing files and symlinks; failed files are retained for review.
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            pipe(
                postgres
                + [
                    "pg_dump",
                    "-U",
                    "sentinelx",
                    "-d",
                    args.database,
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                ],
                ["age", "--encrypt", "--recipient", args.recipient],
                output=file,
            )
            file.flush()
            os.fsync(file.fileno())
        digest = hashlib.sha256()
        with args.output.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        print(
            json.dumps(
                {
                    "status": "encrypted",
                    "sha256": digest.hexdigest(),
                    "bytes": args.output.stat().st_size,
                }
            )
        )
    else:
        if not re.fullmatch(r"sentinelx_restore_[a-z0-9_]+", args.database):
            parser.error(
                "Restore drills require a NEW database named sentinelx_restore_<label>"
            )
        if args.identity_file.stat().st_mode & 0o077:
            parser.error("The age identity file must have private permissions (0600)")
        # createdb fails if the database already exists. No --clean or drop command is ever used.
        subprocess.run(
            postgres + ["createdb", "-U", "sentinelx", args.database], check=True
        )
        pipe(
            [
                "age",
                "--decrypt",
                "--identity",
                str(args.identity_file),
                str(args.input),
            ],
            postgres
            + [
                "pg_restore",
                "-U",
                "sentinelx",
                "-d",
                args.database,
                "--no-owner",
                "--no-privileges",
                "--single-transaction",
                "--exit-on-error",
            ],
        )
        result = subprocess.run(
            postgres
            + [
                "psql",
                "-U",
                "sentinelx",
                "-d",
                args.database,
                "-At",
                "-c",
                "SELECT json_build_object('users',(SELECT count(*) FROM users),'events',(SELECT count(*) FROM events),'alerts',(SELECT count(*) FROM alerts),'incidents',(SELECT count(*) FROM incidents),'receipts',(SELECT count(*) FROM source_receipts),'audit',(SELECT count(*) FROM audit_logs),'revision',(SELECT version_num FROM alembic_version));",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        print(
            json.dumps(
                {"status": "restored-for-review", "counts": json.loads(result.stdout)}
            )
        )


if __name__ == "__main__":
    main()
