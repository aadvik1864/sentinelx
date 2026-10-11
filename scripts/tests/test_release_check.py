import hashlib
import importlib.util
import io
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release_check", Path(__file__).resolve().parents[1] / "release_check.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_small_sample_percentile_uses_nearest_rank():
    assert release.p95([1]) == 1
    assert release.p95(list(range(1, 25))) == 23
    assert release.p95(list(range(1, 1201))) == 1140
    with pytest.raises(ValueError):
        release.p95([])


@pytest.mark.parametrize("events", [0, -1, 864001, True, "864000; DROP TABLE users"])
def test_history_seed_rejects_unbounded_or_non_integer_sizes(events):
    with pytest.raises(ValueError):
        release.history_seed_sql(events, 1)


@pytest.mark.parametrize("source", [0, -1, True, "1; DROP TABLE users"])
def test_history_seed_rejects_non_fixture_source_ids(source):
    with pytest.raises(ValueError):
        release.history_seed_sql(864000, source)


def test_one_day_history_has_receipts_and_does_not_mutate_accounts():
    sql = release.history_seed_sql(864000, 7)
    assert "generate_series(1, 864000)" in sql
    assert "INTERVAL '0.1 seconds'" in sql
    assert "INSERT INTO source_receipts" in sql
    assert "WHERE id = 7" in sql
    assert "ANALYZE events" in sql
    assert "users" not in sql and "DELETE" not in sql and "DROP" not in sql


def test_fingerprints_stream_every_table_without_exposing_content(monkeypatch, capsys):
    content = b'{"fixture":"test-only-private-content"}\n' * 100000
    requests = []

    class Stream(io.BytesIO):
        def read(self, size=-1):
            assert size == 1024 * 1024
            return super().read(size)

    class Process:
        def __init__(self, command, **kwargs):
            requests.append((command, kwargs))
            self.stdout = Stream(content)

        def wait(self):
            return 0

    monkeypatch.setattr(release.subprocess, "Popen", Process)
    actual = release.database_fingerprints(
        ["docker", "compose"], {}, "sentinelx_release_test"
    )
    assert len(actual) == 14
    assert set(actual.values()) == {hashlib.sha256(content).hexdigest()}
    assert len(requests) == 14
    assert all("COPY (SELECT row_to_json" in command[-1] for command, _ in requests)
    assert "private-content" not in capsys.readouterr().out


def test_fingerprints_refuse_non_fixture_database():
    with pytest.raises(ValueError, match="disposable"):
        release.database_fingerprints([], {}, "sentinelx_live")


def test_fingerprints_reject_a_failed_copy(monkeypatch):
    class Process:
        stdout = io.BytesIO(b"unverified fixture output")

        def __init__(self, *args, **kwargs):
            pass

        def wait(self):
            return 1

    monkeypatch.setattr(release.subprocess, "Popen", Process)
    with pytest.raises(RuntimeError, match="fingerprint query failed"):
        release.database_fingerprints([], {}, "sentinelx_release_test")
