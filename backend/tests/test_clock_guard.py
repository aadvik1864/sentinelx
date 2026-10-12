import pytest

from app.core.clock import ClockGuard


def test_unstable_clock_rejects_api_and_readiness_but_not_liveness(client, monkeypatch):
    from app.main import app, clock_guard

    monkeypatch.setattr(app.state, "clock_guard_enabled", True)
    monkeypatch.setattr(clock_guard, "healthy", lambda: False)
    assert client.get("/health/live").status_code == 200
    response = client.get("/health/ready")
    assert response.status_code == 503 and response.json()["status"] == "clock_unstable"
    response = client.post("/api/v1/auth/login", json={})
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("delta", [-1.156, 1.180234, -0.051, 0.051])
def test_clock_steps_latch_failure_without_changing_host_time(delta):
    guard = ClockGuard()
    guard.observe(10, 1000)
    guard.observe(11, 1001 + delta)
    assert not guard.stable
    guard.observe(12, 1002 + delta)
    assert not guard.stable


def test_smooth_clock_progress_is_not_rejected():
    guard = ClockGuard()
    for index in range(100):
        guard.observe(index, 1000 + index * 1.00001)
    assert guard.stable and guard.samples == 100
