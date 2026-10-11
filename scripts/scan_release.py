"""Scan the exact five release images, including OS packages; fail on HIGH/CRITICAL."""

import argparse
import json
import re
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((args.artifact_dir / "report.json").read_text())
    images = report.get("images", {})
    if set(images) != {"backend", "frontend", "nginx", "postgres", "redis"}:
        parser.error(
            "Expected the exact five image IDs from a completed disposable release check"
        )
    summary = {}
    for service, image in images.items():
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
            parser.error("Invalid image ID")
        output = args.artifact_dir / f"{service}-vulnerabilities.json"
        subprocess.run(
            [
                "trivy",
                "image",
                "--quiet",
                "--disable-telemetry",
                "--scanners",
                "vuln",
                "--format",
                "json",
                "--output",
                str(output),
                image,
            ],
            check=True,
        )
        data = json.loads(output.read_text())
        findings = [
            v
            for target in data.get("Results", [])
            for v in target.get("Vulnerabilities", [])
            if v["Severity"] in {"HIGH", "CRITICAL"}
        ]
        summary[service] = {"image": image, "high_critical": len(findings)}
    (args.artifact_dir / "container-scan-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))
    if any(row["high_critical"] for row in summary.values()):
        raise SystemExit(
            "Container vulnerability gate failed; review findings before release"
        )


if __name__ == "__main__":
    main()
