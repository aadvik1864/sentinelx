import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "setup_monitoring", Path(__file__).resolve().parents[1] / "setup_monitoring.py"
)
monitoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitoring)


@pytest.fixture
def definition():
    return {
        "name": "Linux host: example.test",
        "kind": "linux",
        "hostname": "example.test",
        "log_path": "/var/log/auth.log",
    }


def test_existing_source_is_reused_after_display_name_change(definition):
    source = {**definition, "id": 7, "name": "Earlier collector label"}
    assert monitoring.find_existing_source([source], definition) is source


def test_existing_source_name_still_matches(definition):
    source = {**definition, "id": 7}
    assert monitoring.find_existing_source([source], definition) is source


@pytest.mark.parametrize(
    "field,value",
    [
        ("hostname", "other.example.test"),
        ("kind", "nginx"),
        ("log_path", "/var/log/other.log"),
    ],
)
def test_different_source_identity_is_not_reused(definition, field, value):
    source = {**definition, "id": 7, "name": "Another source", field: value}
    assert monitoring.find_existing_source([source], definition) is None


def test_ambiguous_existing_sources_fail_closed(definition):
    sources = [
        {**definition, "id": 7, "name": "Earlier label"},
        {**definition, "id": 8, "name": "Another label"},
    ]
    with pytest.raises(SystemExit, match="Several existing sources match"):
        monitoring.find_existing_source(sources, definition)


def test_new_source_has_no_existing_match(definition):
    assert monitoring.find_existing_source([], definition) is None
