import importlib.util
import stat
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "browser_release_check",
    Path(__file__).resolve().parents[1] / "browser_release_check.py",
)
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)


@pytest.mark.parametrize("returncode", [0, 1])
def test_browser_assertion_output_remains_private_even_on_failure(
    tmp_path, capsys, returncode
):
    command = [
        sys.executable,
        "-c",
        f"import sys; print('test-only-recovery-code'); print('test-only-private-dom',file=sys.stderr); sys.exit({returncode})",
    ]
    if returncode:
        with pytest.raises(SystemExit, match="diagnostics are private"):
            browser.private_browser_check(
                command, frontend=tmp_path, environment={}, directory=tmp_path
            )
    else:
        browser.private_browser_check(
            command, frontend=tmp_path, environment={}, directory=tmp_path
        )
    public = capsys.readouterr()
    assert "test-only-recovery-code" not in public.out + public.err
    assert "test-only-private-dom" not in public.out + public.err
    logs = list(tmp_path.glob("browser-check-*.log"))
    assert len(logs) == 1 and stat.S_IMODE(logs[0].stat().st_mode) == 0o600
    assert (
        "test-only-recovery-code" in logs[0].read_text()
        and "test-only-private-dom" in logs[0].read_text()
    )
