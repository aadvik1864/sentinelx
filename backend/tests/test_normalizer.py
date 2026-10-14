import json
from datetime import UTC, datetime

import pytest

from app.schemas import RawLog
from app.services.ingestion.normalizer import normalize


@pytest.mark.parametrize(
    "line,kind",
    [
        (
            "sshd: Failed password for invalid user root from 203.0.113.42 port 22 ssh2",
            "authentication_failure",
        ),
        (
            "sshd: Accepted publickey for admin from 2001:db8::1 port 22 ssh2",
            "authentication_success",
        ),
        ("sshd: Invalid user root from 203.0.113.42", "invalid_user"),
        ("sudo: admin : TTY=pts/0 ; USER=root ; COMMAND=/usr/bin/id", "privilege_escalation"),
    ],
)
def test_linux_normalization(line, kind):
    result = normalize(
        RawLog(source="linux", hostname="lab", line=line, timestamp=datetime.now(UTC))
    )
    assert result.event_type == kind


def test_web_and_json_normalization():
    date = datetime.now(UTC).strftime("%d/%b/%Y:%H:%M:%S %z")
    line = f'203.0.113.42 - - [{date}] "GET /admin HTTP/1.1" 403 128 "-" "lab"'
    web = normalize(RawLog(source="nginx", hostname="web-lab", line=line))
    assert web.metadata["http_status"] == 403
    assert web.message == "GET /admin: HTTP 403"
    application = normalize(
        RawLog(
            source="application",
            hostname="auth",
            line=json.dumps(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "level": "ERROR",
                    "message": "Failed login",
                    "ip": "203.0.113.42",
                }
            ),
        )
    )
    assert application.event_type == "authentication_failure"


def test_json_web_message_uses_plain_punctuation():
    web = normalize(
        RawLog(
            source="nginx",
            hostname="web-lab",
            line=json.dumps(
                {"method": "POST", "path": "/login?private=omitted", "http_status": 401}
            ),
        )
    )
    assert web.message == "POST /login: HTTP 401"
    assert web.metadata["path"] == "/login"


def test_invalid_application_log():
    with pytest.raises(ValueError):
        normalize(RawLog(source="application", hostname="lab", line="[]"))
