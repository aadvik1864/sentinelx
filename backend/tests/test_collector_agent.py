import importlib.util
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

# Works from both the source checkout and the backend image (/app/collectors).
root = Path(__file__).resolve().parents[1]
path = next(
    path
    for path in [root / "collectors" / "agent.py", root.parent / "collectors" / "agent.py"]
    if path.exists()
)
spec = importlib.util.spec_from_file_location("collector_agent", path)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


def test_file_tail_restart_partial_records_and_rotation(tmp_path):
    state = agent.State(tmp_path / "state.sqlite3")
    path = tmp_path / "auth.log"
    path.write_text("historical\n")
    tailer = agent.FileTailer(state, 1, path)
    assert tailer.read_one() is None
    with path.open("a") as file:
        file.write("first\npartial")
    first = tailer.read_one()
    assert first[0] == "first"
    state.save(1, first[2])
    assert tailer.read_one() is None
    tailer.close()
    tailer = agent.FileTailer(state, 1, path)
    with path.open("a") as file:
        file.write(" complete\n")
    second = tailer.read_one()
    assert second[0] == "partial complete"
    state.save(1, second[2])
    path.rename(tmp_path / "auth.log.1")
    path.write_text("new file\n")
    assert tailer.read_one() is None
    third = tailer.read_one()
    assert third[0] == "new file"
    assert third[1] not in {first[1], second[1]}
    assert not tailer.gap
    tailer.close()


def test_rotation_while_stopped_and_missing_inode_gap(tmp_path):
    state = agent.State(tmp_path / "state.sqlite3")
    path = tmp_path / "auth.log"
    path.write_text("before\nremaining\n")
    tailer = agent.FileTailer(state, 1, path, start="beginning")
    first = tailer.read_one()
    state.save(1, first[2])
    tailer.close()
    rotated = tmp_path / "auth.log.1"
    path.rename(rotated)
    path.write_text("new\n")
    tailer = agent.FileTailer(state, 1, path)
    assert tailer.read_one()[0] == "remaining"
    tailer.close()
    rotated.unlink()
    tailer = agent.FileTailer(state, 1, path)
    assert tailer.read_one()[0] == "new"
    assert tailer.gap
    tailer.close()


def test_copytruncate_is_reported(tmp_path):
    state = agent.State(tmp_path / "state.sqlite3")
    path = tmp_path / "auth.log"
    path.write_text("a long old record\n")
    tailer = agent.FileTailer(state, 1, path)
    path.write_text("new\n")
    assert tailer.read_one()[0] == "new"
    assert tailer.gap
    tailer.close()


def test_pending_record_survives_restart(tmp_path):
    path = tmp_path / "state.sqlite3"
    state = agent.State(path)
    state.save(1, {"offset": 0})
    state.stage(1, {"record_key": "stable-record-key", "line": "redacted"}, {"offset": 17})
    state.db.close()
    state = agent.State(path)
    assert state.cursor(1) == {"offset": 0}
    pending = state.pending(1)
    assert pending["cursor"] == {"offset": 17}
    state.save(1, pending["cursor"])
    assert state.pending(1) is None
    assert os.stat(path).st_mode & 0o077 == 0


def test_occurrence_time_iso_and_year_rollover():
    assert (
        agent.occurrence_time("2026-10-08T12:00:00+05:30 host sshd: activity", "UTC")
        == "2026-10-08T06:30:00+00:00"
    )
    now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    assert (
        agent.occurrence_time("Dec 31 23:59:00 host sshd: activity", "UTC", now)
        == "2025-12-31T23:59:00+00:00"
    )
    with pytest.raises(ValueError):
        agent.occurrence_time("no occurrence timestamp", "UTC")


def test_redaction_and_loop_prevention_do_not_filter_external_apps():
    line = json.dumps(
        {
            "path": "/login?password=hidden",
            "password": "private",
            "nested": {"Authorization": "Bearer private"},
            "message": "token=private Bearer private",
        }
    )
    result = agent.prepare_line("application", line)
    assert "private" not in result
    assert "hidden" not in result
    for path in ["/api/v1/incidents", "/api/v1/events", "/health/ready"]:
        line = json.dumps({"path": path, "method": "GET"})
        assert agent.prepare_line("nginx", line, self_monitoring=True) is None
        assert agent.prepare_line("nginx", line) is not None


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://example.com/path",
        "https://example.com?token=private",
    ],
)
def test_unsafe_origins_are_rejected(url):
    with pytest.raises(ValueError):
        agent.validate_url(url)


@pytest.mark.parametrize(
    "url",
    ["http://localhost:8080", "http://127.0.0.1:8080", "http://[::1]:8080", "https://example.com"],
)
def test_safe_origins_are_accepted(url):
    assert agent.validate_url(url) == url


class ImmediateStop:
    def is_set(self):
        return False

    def wait(self, delay):
        return False


def test_retries_keep_same_payload_until_acknowledgment(tmp_path):
    state = agent.State(tmp_path / "state.sqlite3")
    state.save(1, {"offset": 0})
    payload = {"record_key": "stable-record-key", "line": "redacted", "timestamp": None}
    state.stage(1, payload, {"offset": 10})
    calls = []

    class Transport:
        def post(self, source, suffix, body):
            calls.append(body)
            assert state.cursor(1) == {"offset": 0}
            if len(calls) == 1:
                raise httpx.ConnectError("unavailable")
            return httpx.Response(429 if len(calls) == 2 else 201, headers={"Retry-After": "1"})

        def heartbeat(self, *args):
            pass

    worker = agent.Worker({"id": 1}, state, Transport(), ImmediateStop())
    assert worker.deliver_pending()
    assert calls == [payload, payload, payload]
    assert state.cursor(1) == {"offset": 10}
    assert state.pending(1) is None


def test_rejected_record_is_quarantined_not_retried_forever(tmp_path):
    state = agent.State(tmp_path / "state.sqlite3")
    state.stage(1, {"record_key": "stable-record-key", "line": "redacted"}, {"offset": 10})

    class Transport:
        def post(self, *args):
            return httpx.Response(422)

        def heartbeat(self, *args):
            pass

    worker = agent.Worker({"id": 1}, state, Transport(), threading.Event())
    assert worker.deliver_pending()
    assert state.rejected(1) == 1
    assert worker.error == "record_rejected"
    assert state.cursor(1) == {"offset": 10}


def test_invalid_file_record_has_visible_error_without_raw_secrets(tmp_path):
    state = agent.State(tmp_path / "state.sqlite3")
    errors = []

    class Transport:
        def heartbeat(self, source, error):
            errors.append(error)

    worker = agent.Worker(
        {"id": 1, "kind": "application", "mode": "file"}, state, Transport(), threading.Event()
    )
    assert worker.accept("not JSON password=private", "stable-record-key", {"offset": 10})
    assert errors == ["record_rejected"]
    assert "private" not in state.db.execute("SELECT payload FROM quarantine").fetchone()[0]


def test_quiet_docker_stream_saves_start_cursor_and_flags_replacement(tmp_path, monkeypatch):
    state = agent.State(tmp_path / "state.sqlite3")
    calls = []
    container = ["first-container"]

    class Process:
        def __init__(self, command, **kwargs):
            import io

            calls.append(command)
            self.stdout = io.StringIO("")

        def poll(self):
            return 0

        def wait(self, **kwargs):
            return 0

    class Transport:
        def heartbeat(self, *args):
            pass

    from types import SimpleNamespace

    monkeypatch.setattr(
        agent.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=container[0])
    )
    monkeypatch.setattr(agent.subprocess, "Popen", Process)
    worker = agent.Worker(
        {"id": 1, "kind": "nginx", "mode": "docker", "service": "nginx"},
        state,
        Transport(),
        threading.Event(),
    )
    with pytest.raises(OSError, match="stream stopped"):
        worker.run_docker()
    cursor = state.cursor(1)
    assert cursor["timestamp"]
    with pytest.raises(OSError):
        worker.run_docker()
    assert calls[0][-2] == calls[1][-2] == cursor["timestamp"]
    container[0] = "replacement-container"
    with pytest.raises(OSError):
        worker.run_docker()
    assert state.notice(1) == "log_gap"
