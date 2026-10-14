import json
import re
from datetime import UTC, datetime

from app.schemas import EventInput, RawLog

SSH_FAILED = re.compile(r"Failed \w+ for (?:invalid user )?(?P<user>\S+) from (?P<ip>\S+)")
SSH_ACCEPTED = re.compile(r"Accepted \w+ for (?P<user>\S+) from (?P<ip>\S+)")
INVALID = re.compile(r"Invalid user (?P<user>\S+) from (?P<ip>\S+)")
WEB = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+) [^"]*" (?P<status>\d{3}) \S+'
)
SYSLOG_TIME = re.compile(r"^(?P<time>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})")


def normalize(raw: RawLog) -> EventInput:
    timestamp = raw.timestamp or datetime.now(UTC)
    base = dict(
        timestamp=timestamp, source=raw.source, hostname=raw.hostname, message=raw.line, metadata={}
    )
    if raw.source == "linux":
        if raw.timestamp is None and (match := SYSLOG_TIME.match(raw.line)):
            # Classic syslog has no year/zone; collectors must supply a timestamp outside a UTC lab.
            timestamp = datetime.strptime(
                f"{datetime.now(UTC).year} {match['time']}", "%Y %b %d %H:%M:%S"
            ).replace(tzinfo=UTC)
            if timestamp > datetime.now(UTC) and (timestamp - datetime.now(UTC)).days > 1:
                timestamp = timestamp.replace(year=timestamp.year - 1)
            base["timestamp"] = timestamp
        for pattern, kind, severity in [
            (SSH_FAILED, "authentication_failure", "medium"),
            (SSH_ACCEPTED, "authentication_success", "low"),
            (INVALID, "invalid_user", "medium"),
        ]:
            if match := pattern.search(raw.line):
                base["metadata"] = {"invalid_user": "invalid user" in raw.line.lower()}
                return EventInput(
                    **base,
                    event_type=kind,
                    severity=severity,
                    source_ip=match["ip"],
                    username=match["user"],
                )
        if "sudo:" in raw.line or "su:" in raw.line:
            match = re.search(r"(?:sudo|su):\s+(\S+)\s*:", raw.line)
            return EventInput(
                **base,
                event_type="privilege_escalation",
                severity="high",
                username=match[1] if match else None,
            )
        return EventInput(**base, event_type="system_event", severity="low")
    if raw.source in {"nginx", "apache"}:
        if raw.line.lstrip().startswith("{"):
            data = json.loads(raw.line)
            if not isinstance(data, dict):
                raise ValueError("Web access log must be a JSON object")
            status = data.get("http_status")
            if type(status) is not int or not 100 <= status <= 599:
                raise ValueError("Web log requires an integer http_status")
            method = str(data.get("method", "GET"))[:20]
            path = str(data.get("path", "/")).split("?", 1)[0][:2048]
            base.update(
                timestamp=raw.timestamp or data.get("timestamp", timestamp),
                message=f"{method} {path}: HTTP {status}",
                metadata={"http_status": status, "path": path, "method": method},
            )
            return EventInput(
                **base,
                source_ip=data.get("ip"),
                event_type="http_request",
                severity="medium" if status >= 400 else "low",
            )
        match = WEB.match(raw.line)
        if not match:
            raise ValueError("Expected an Nginx/Apache combined or common access log")
        status = int(match["status"])
        base["timestamp"] = raw.timestamp or datetime.strptime(
            match["time"], "%d/%b/%Y:%H:%M:%S %z"
        )
        path = match["path"].split("?", 1)[0][:2048]
        base["metadata"] = {"http_status": status, "path": path, "method": match["method"]}
        base["message"] = f"{match['method']} {path}: HTTP {status}"
        return EventInput(
            **base,
            source_ip=match["ip"],
            event_type="http_request",
            severity="medium" if status >= 400 else "low",
        )
    data = json.loads(raw.line)
    if not isinstance(data, dict):
        raise ValueError("Application log must be a JSON object")
    message = str(data.get("message", "Application event"))
    kind = data.get("event_type") or (
        "authentication_failure" if "failed login" in message.lower() else "application_event"
    )
    base.update(
        timestamp=raw.timestamp or data.get("timestamp", timestamp),
        message=message,
        metadata={
            key: value
            for key, value in data.items()
            if key not in {"timestamp", "message", "ip", "username", "event_type"}
        },
    )
    return EventInput(
        **base,
        event_type=kind,
        severity="medium" if data.get("level") == "ERROR" else "low",
        source_ip=data.get("ip"),
        username=data.get("username"),
    )
