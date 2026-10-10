"""Read authorized files/container logs. Send source-scoped, replay-safe records to SentinelX."""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import signal
import sqlite3
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

EXCLUDED = (
    "/health",
    "/ws/",
    "/api/v1/sources",
    "/api/v1/events",
    "/api/v1/dashboard",
    "/api/v1/system",
    "/api/v1/auth/refresh",
)
SECRET_KEY = re.compile(
    r"password|passwd|secret|token|authorization|cookie|api.?key|credential", re.I
)
SECRET_VALUE = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
BEARER_VALUE = re.compile(r"(?i)\bBearer\s+[a-zA-Z0-9._~+/=-]+")
SYSLOG_TIME = re.compile(r"^([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})")
ISO_TIME = re.compile(r"^(\d{4}-\d{2}-\d{2}T\S+)")


def validate_url(value):
    parsed = urlparse(value)
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError(
            "Use a SentinelX origin without credentials, paths, or query strings"
        )
    loopback = parsed.hostname == "localhost"
    try:
        loopback = loopback or ipaddress.ip_address(parsed.hostname).is_loopback
    except (TypeError, ValueError):
        pass
    if not parsed.hostname or (
        parsed.scheme != "https" and not (parsed.scheme == "http" and loopback)
    ):
        raise ValueError(
            "Use verified HTTPS, or HTTP on loopback through a local/SSH-tunneled endpoint"
        )
    return value.rstrip("/")


def local_timezone(name="local"):
    if name != "local":
        return ZoneInfo(name)
    with Path("/etc/localtime").open("rb") as file:
        return ZoneInfo.from_file(file)


def occurrence_time(line, timezone="local", now=None):
    now = now or datetime.now(UTC)
    zone = local_timezone(timezone)
    if match := ISO_TIME.match(line):
        timestamp = datetime.fromisoformat(match[1].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=zone)
        return timestamp.astimezone(UTC).isoformat()
    if match := SYSLOG_TIME.match(line):
        year = now.astimezone(zone).year
        timestamp = datetime.strptime(
            f"{year} {match[1]}", "%Y %b %d %H:%M:%S"
        ).replace(tzinfo=zone)
        if timestamp > now + timedelta(days=1):
            timestamp = timestamp.replace(year=year - 1)
        return timestamp.astimezone(UTC).isoformat()
    raise ValueError("Linux record has no supported occurrence timestamp")


def scrub(value):
    if isinstance(value, dict):
        return {
            key: "[redacted]" if SECRET_KEY.search(key) else scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        value = SECRET_VALUE.sub(lambda match: f"{match[1]}=[redacted]", value)
        return BEARER_VALUE.sub("Bearer [redacted]", value)
    return value


def prepare_line(kind, line, self_monitoring=False):
    """Exclude self-collection traffic and redact credential-like fields before transmission."""
    if line.lstrip().startswith("{"):
        data = json.loads(line)
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        path = str(data.get("path", "")).split("?", 1)[0]
        if self_monitoring and path.startswith(EXCLUDED):
            return None
        if (
            self_monitoring
            and str(data.get("method", "")).upper() in {"GET", "HEAD", "OPTIONS"}
            and path.startswith("/api/")
        ):
            return None
        if "path" in data:
            data["path"] = path
        return json.dumps(scrub(data), ensure_ascii=True)
    if kind == "application":
        # Uvicorn/entrypoint output is not the configured JSON security log stream.
        return None
    if kind in {"nginx", "apache"}:
        match = re.search(r'"\S+ (\S+) HTTP/', line)
        if not match:
            return None
        path = match[1].split("?", 1)[0]
        if self_monitoring and path.startswith(EXCLUDED):
            return None
        if (
            self_monitoring
            and re.search(r'"(?:GET|HEAD|OPTIONS) ', line)
            and path.startswith("/api/")
        ):
            return None
        line = line[: match.start(1)] + path + line[match.end(1) :]
    return scrub(line)


class State:
    def __init__(self, path):
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        os.chmod(path, 0o600)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS checkpoints (source TEXT PRIMARY KEY, cursor TEXT NOT NULL, pending TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS quarantine (source TEXT, record_key TEXT, payload TEXT, reason TEXT, PRIMARY KEY(source, record_key))"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS notices (source TEXT PRIMARY KEY, error TEXT NOT NULL)"
        )
        self.db.commit()

    def cursor(self, source):
        with self.lock:
            row = self.db.execute(
                "SELECT cursor FROM checkpoints WHERE source=?", (str(source),)
            ).fetchone()
            return json.loads(row[0]) if row else {}

    def save(self, source, cursor):
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO checkpoints VALUES (?, ?, NULL) ON CONFLICT(source) DO UPDATE SET cursor=excluded.cursor, pending=NULL",
                (str(source), json.dumps(cursor)),
            )

    def stage(self, source, payload, cursor):
        with self.lock, self.db:
            existing = self.cursor(source)
            pending = json.dumps({"payload": payload, "cursor": cursor})
            self.db.execute(
                "INSERT INTO checkpoints VALUES (?, ?, ?) ON CONFLICT(source) DO UPDATE SET pending=excluded.pending",
                (str(source), json.dumps(existing), pending),
            )

    def pending(self, source):
        with self.lock:
            row = self.db.execute(
                "SELECT pending FROM checkpoints WHERE source=?", (str(source),)
            ).fetchone()
            return json.loads(row[0]) if row and row[0] else None

    def reject(self, source, pending, reason):
        with self.lock, self.db:
            payload = pending["payload"]
            self.db.execute(
                "INSERT OR IGNORE INTO quarantine VALUES (?, ?, ?, ?)",
                (str(source), payload["record_key"], json.dumps(payload), reason),
            )
            self.db.execute(
                "UPDATE checkpoints SET cursor=?, pending=NULL WHERE source=?",
                (json.dumps(pending["cursor"]), str(source)),
            )

    def rejected(self, source):
        with self.lock:
            return self.db.execute(
                "SELECT COUNT(*) FROM quarantine WHERE source=?", (str(source),)
            ).fetchone()[0]

    def notice(self, source, error=None):
        with self.lock, self.db:
            if error is not None:
                self.db.execute(
                    "INSERT INTO notices VALUES (?, ?) ON CONFLICT(source) DO UPDATE SET error=excluded.error",
                    (str(source), error),
                )
            row = self.db.execute(
                "SELECT error FROM notices WHERE source=?", (str(source),)
            ).fetchone()
            return row[0] if row else ""


class FileTailer:
    def __init__(self, state, source, path, start="tail"):
        self.state, self.source = state, source
        self.path = Path(path).expanduser()
        self.file = None
        self.gap = False
        stat = self.path.stat()
        if not state.cursor(source):
            state.save(
                source,
                {
                    "identity": self.identity(stat),
                    "offset": stat.st_size if start == "tail" else 0,
                    "generation": 0,
                },
            )

    @staticmethod
    def identity(stat):
        return f"{stat.st_dev}:{stat.st_ino}"

    def open_checkpoint(self, cursor):
        candidate = self.path
        if self.identity(candidate.stat()) != cursor["identity"]:
            candidate = next(
                (
                    path
                    for path in self.path.parent.glob(self.path.name + "*")
                    if path.is_file()
                    and self.identity(path.stat()) == cursor["identity"]
                ),
                None,
            )
            if candidate is None:
                self.gap = True
                candidate = self.path
                cursor = {
                    "identity": self.identity(candidate.stat()),
                    "offset": 0,
                    "generation": cursor["generation"] + 1,
                }
                self.state.save(self.source, cursor)
        self.file = candidate.open("rb")

    def read_one(self):
        cursor = self.state.cursor(self.source)
        if not self.file:
            self.open_checkpoint(cursor)
            cursor = self.state.cursor(self.source)
        stat = os.fstat(self.file.fileno())
        if stat.st_size < cursor["offset"]:
            self.gap = True
            cursor = {**cursor, "offset": 0, "generation": cursor["generation"] + 1}
            self.state.save(self.source, cursor)
        self.file.seek(cursor["offset"])
        position = self.file.tell()
        raw = self.file.readline(65537)
        if not raw:
            current = self.path.stat()
            if self.identity(current) != self.identity(stat):
                self.file.close()
                self.file = None
                self.state.save(
                    self.source,
                    {
                        "identity": self.identity(current),
                        "offset": 0,
                        "generation": cursor["generation"] + 1,
                    },
                )
            return None
        if not raw.endswith(b"\n") and len(raw) <= 65536:
            self.file.seek(position)
            return None
        if len(raw) > 65536:
            while raw and not raw.endswith(b"\n"):
                raw = self.file.readline(65537)
            line = "[oversized log record]"
        else:
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        key = hashlib.sha256(
            f"{cursor['identity']}:{cursor['generation']}:{position}:".encode() + raw
        ).hexdigest()
        return (
            line,
            key,
            {**cursor, "offset": self.file.tell()},
            len(raw) > 65536 or line == "[oversized log record]",
        )

    def close(self):
        if self.file:
            self.file.close()


class Transport:
    def __init__(self, url, stop):
        self.url = validate_url(url)
        self.stop = stop
        self.client = httpx.Client(
            base_url=self.url, timeout=15, follow_redirects=False, trust_env=False
        )
        self.lock = threading.Lock()
        self.next_request = 0.0

    def post(self, source, suffix, body):
        import time

        with self.lock:
            wait = max(0, self.next_request - time.monotonic())
            self.stop.wait(wait)
            self.next_request = time.monotonic() + 0.125
        return self.client.post(
            f"/api/v1/sources/{source['id']}/{suffix}",
            json=body,
            headers={"Authorization": f"Bearer {source['key']}"},
        )

    def heartbeat(self, source, error=""):
        try:
            self.post(
                source,
                "heartbeat",
                {"state": "error" if error else "listening", "error": error},
            )
        except httpx.HTTPError:
            pass


class Worker:
    def __init__(self, source, state, transport, stop):
        self.source, self.state, self.transport, self.stop = (
            source,
            state,
            transport,
            stop,
        )
        self.error = ""
        self.process = None
        self.last_heartbeat = 0.0

    def beat(self, force=False):
        import time

        if force or time.monotonic() - self.last_heartbeat > 15:
            error = self.error or (
                "record_rejected" if self.state.rejected(self.source["id"]) else ""
            )
            error = error or self.state.notice(self.source["id"])
            self.transport.heartbeat(self.source, error)
            self.last_heartbeat = time.monotonic()

    def deliver_pending(self):
        pending = self.state.pending(self.source["id"])
        if not pending:
            return True
        delay = 1
        while not self.stop.is_set():
            try:
                response = self.transport.post(
                    self.source, "events", pending["payload"]
                )
                if response.status_code in (200, 201):
                    self.state.save(self.source["id"], pending["cursor"])
                    self.error = ""
                    return True
                if response.status_code in (409, 413, 422):
                    self.state.reject(
                        self.source["id"], pending, f"HTTP {response.status_code}"
                    )
                    self.error = "record_rejected"
                    self.beat(force=True)
                    return True
                self.error = "connection_failed"
                delay = min(
                    60, max(delay, int(response.headers.get("Retry-After", delay)))
                )
                if response.status_code in (401, 403):
                    print(
                        f"Source {self.source['id']}: credential rejected or source paused; update its configuration.",
                        flush=True,
                    )
                    delay = 30
            except (httpx.HTTPError, ValueError):
                self.error = "connection_failed"
            self.beat()
            self.stop.wait(delay)
            delay = min(delay * 2, 30)
        return False

    def accept(self, line, record_key, cursor, oversized=False):
        try:
            if oversized:
                raise ValueError("Oversized log record")
            if (
                self.source["kind"] == "application"
                and self.source.get("mode", "file") == "file"
                and not line.lstrip().startswith("{")
            ):
                raise ValueError("Application file must contain JSON records")
            cleaned = prepare_line(
                self.source["kind"], line, self.source.get("self_monitoring", False)
            )
            if cleaned is None or not cleaned.strip():
                self.state.save(self.source["id"], cursor)
                return True
            timestamp = (
                occurrence_time(line, self.source.get("timezone", "local"))
                if self.source["kind"] == "linux"
                else None
            )
            if self.source["kind"] == "application" and not json.loads(cleaned).get(
                "timestamp"
            ):
                raise ValueError("Application JSON needs an occurrence timestamp")
            payload = {
                "record_key": record_key,
                "line": cleaned,
                "timestamp": timestamp,
            }
            if len(cleaned) > 20000:
                raise ValueError("Oversized log record")
        except (ValueError, TypeError, KeyError):
            payload = {
                "record_key": record_key,
                "line": "[invalid or oversized record; raw content omitted]",
                "timestamp": None,
            }
            self.state.stage(self.source["id"], payload, cursor)
            self.state.reject(
                self.source["id"],
                self.state.pending(self.source["id"]),
                "Unsupported format or timestamp",
            )
            self.error = "record_rejected"
            self.beat(force=True)
            return True
        self.state.stage(self.source["id"], payload, cursor)
        return self.deliver_pending()

    def run_file(self):
        tailer = None
        try:
            tailer = FileTailer(
                self.state,
                self.source["id"],
                self.source["path"],
                self.source.get("start", "tail"),
            )
            self.error = ""
            self.beat(force=True)
            while not self.stop.is_set():
                record = tailer.read_one()
                if tailer.gap:
                    self.state.notice(self.source["id"], "log_gap")
                if record:
                    line, key, cursor, oversized = record
                    if not self.accept(line, key, cursor, oversized):
                        break
                else:
                    self.beat()
                    self.stop.wait(0.5)
        finally:
            if tailer:
                tailer.close()

    def run_docker(self):
        selector = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"label=com.docker.compose.project={self.source.get('project', 'sentinelx')}",
                "--filter",
                f"label=com.docker.compose.service={self.source['service']}",
                "--format",
                "{{.ID}}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        containers = selector.stdout.split()
        if len(containers) != 1:
            raise OSError("Configured container is unavailable or ambiguous")
        container = containers[0]
        cursor = self.state.cursor(self.source["id"])
        since = cursor.get("timestamp") or datetime.now(UTC).isoformat()
        if cursor.get("container") and cursor["container"] != container:
            self.state.notice(self.source["id"], "log_gap")
        if not cursor:
            self.state.save(
                self.source["id"], {"container": container, "timestamp": since}
            )
        self.process = subprocess.Popen(
            ["docker", "logs", "--follow", "--timestamps", "--since", since, container],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.error = ""
        self.beat(force=True)
        try:
            for record in self.process.stdout:
                if self.stop.is_set():
                    break
                stamp, separator, line = record.partition(" ")
                if not separator or not ISO_TIME.match(stamp):
                    continue
                line = line.rstrip("\r\n")
                key = hashlib.sha256(f"{container}:{stamp}:{line}".encode()).hexdigest()
                next_cursor = {"container": container, "timestamp": stamp}
                if not self.accept(line, key, next_cursor, len(line) > 20000):
                    break
                self.beat()
        finally:
            process = self.process
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            process.stdout.close()
            self.process = None
        if not self.stop.is_set():
            raise OSError("Container log stream stopped")

    def run(self):
        self.deliver_pending()
        while not self.stop.is_set():
            try:
                if self.source.get("mode", "file") == "docker":
                    self.run_docker()
                else:
                    self.run_file()
            except (OSError, subprocess.SubprocessError):
                self.error = (
                    "docker_unavailable"
                    if self.source.get("mode") == "docker"
                    else "file_unavailable"
                )
                self.beat(force=True)
                self.stop.wait(5)
            except (ValueError, KeyError):
                self.error = "configuration_error"
                self.beat(force=True)
                self.stop.wait(30)

    def health_loop(self):
        while not self.stop.wait(15):
            self.beat(force=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    if args.config.stat().st_mode & 0o077:
        raise SystemExit(
            "Collector configuration contains keys. Run chmod 600 on that file first."
        )
    config = json.loads(args.config.read_text())
    stop = threading.Event()
    transport = Transport(config["url"], stop)
    state = State(config.get("state_file", str(args.config.with_suffix(".sqlite3"))))
    workers = [Worker(source, state, transport, stop) for source in config["sources"]]

    def halt(*_args):
        stop.set()
        for worker in workers:
            if worker.process and worker.process.poll() is None:
                worker.process.terminate()

    signal.signal(signal.SIGTERM, halt)
    signal.signal(signal.SIGINT, halt)
    threads = []
    for worker in workers:
        for target in (worker.run, worker.health_loop):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            threads.append(thread)
    print(
        f"SentinelX collector started with {len(workers)} authorized sources. Existing file history is not replayed on first start.",
        flush=True,
    )
    while not stop.wait(1):
        if any(not thread.is_alive() for thread in threads):
            halt()
            raise SystemExit(
                "A source worker stopped unexpectedly. Check the service log and configuration."
            )
    for thread in threads:
        thread.join(timeout=20)
    transport.client.close()


if __name__ == "__main__":
    main()
