import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_runner_clock", Path(__file__).resolve().parents[1] / "check_runner_clock.py"
)
clock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clock)


def test_steady_clock_summary():
    assert clock.clock_summary([0, -0.000001, 0.000002]) == {
        "clock_samples": 3,
        "minimum_wall_step_seconds": -0.000001,
        "maximum_wall_step_seconds": 0.000002,
        "clock_stable": True,
    }


@pytest.mark.parametrize("steps", [[], [-1.156], [0.1], [0.05], [-0.05]])
def test_unknown_or_jumping_clocks_are_not_approved(steps):
    assert not clock.clock_summary(steps)["clock_stable"]
