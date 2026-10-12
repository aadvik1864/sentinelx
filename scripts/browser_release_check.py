"""Run fixture-only production browser checks with an isolated trusted test CA."""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


def private_browser_check(command, *, frontend, environment, directory):
    # Assertion diagnostics can include visible recovery codes/DOM content. Never stream them to CI.
    with tempfile.NamedTemporaryFile(
        prefix="browser-check-", suffix=".log", dir=directory, delete=False
    ) as log:
        result = subprocess.run(
            command, cwd=frontend, env=environment, stdout=log, stderr=subprocess.STDOUT
        )
    if result.returncode:
        raise SystemExit(
            "Production browser check failed; diagnostics are private fixture artifacts"
        )
    print("Trusted-CA production browser/passkey check passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((args.artifact_dir / "report.json").read_text())
    if report["status"] != "passed" or not report["project"].startswith(
        "sentinelx-release-"
    ):
        parser.error(
            "Requires a passed disposable release fixture left running with --keep"
        )
    credentials = dict(
        line.split("=", 1)
        for line in (args.artifact_dir / "browser.env").read_text().splitlines()
    )
    if credentials.get("SENTINELX_E2E_URL") != "https://localhost:18443":
        parser.error("Only the disposable fixture origin is allowed")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # GitHub handles these workflow commands as secret masks, not public log content.
        for name in ("SENTINELX_E2E_PASSWORD", "SENTINELX_E2E_OTP"):
            print(f"::add-mask::{credentials[name]}", flush=True)
    home = Path(tempfile.mkdtemp(prefix="browser-home-", dir=args.artifact_dir))
    nss = home / ".pki" / "nssdb"
    nss.mkdir(parents=True)
    ca = args.artifact_dir / "tls" / "ca.pem"
    subprocess.run(
        ["certutil", "-N", "-d", f"sql:{nss}", "--empty-password"], check=True
    )
    subprocess.run(
        [
            "certutil",
            "-A",
            "-d",
            f"sql:{nss}",
            "-n",
            "SentinelX disposable CA",
            "-t",
            "C,,",
            "-i",
            str(ca),
        ],
        check=True,
    )
    environment = {
        **os.environ,
        **credentials,
        "SENTINELX_RELEASE_E2E": "true",
        "HOME": str(home),
        "NODE_EXTRA_CA_CERTS": str(ca),
        "PLAYWRIGHT_BROWSERS_PATH": os.environ.get(
            "PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".cache" / "ms-playwright")
        ),
    }
    frontend = Path(__file__).resolve().parents[1] / "frontend"
    private_browser_check(
        [
            str(frontend / "node_modules/.bin/playwright"),
            "test",
            "e2e/production-auth.spec.ts",
        ],
        frontend=frontend,
        environment=environment,
        directory=args.artifact_dir,
    )


if __name__ == "__main__":
    main()
