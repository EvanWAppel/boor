"""SETUP-04: the one-command local runner (``scripts/dev.sh``).

The real commands (uvicorn + ``pnpm dev``) are swapped for ``sleep`` stand-ins via
``BOOR_DEV_SERVICE_CMD`` / ``BOOR_DEV_WEB_CMD`` so the process supervision — both
start, one Ctrl-C stops both, one dying stops the other — is tested without
Docker, Node or ports. ``--print`` exercises the real default commands.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "dev.sh"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait_for(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _start(tmp_path: Path, service_cmd: str, web_cmd: str) -> subprocess.Popen[bytes]:
    env = {
        **os.environ,
        "BOOR_DEV_SERVICE_CMD": service_cmd,
        "BOOR_DEV_WEB_CMD": web_cmd,
    }
    return subprocess.Popen(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # keep the script's signals away from pytest
    )


def _pids(tmp_path: Path) -> tuple[int, int] | None:
    files = [tmp_path / "service.pid", tmp_path / "web.pid"]
    if not all(f.exists() and f.read_text().strip() for f in files):
        return None
    service_pid, web_pid = (int(f.read_text()) for f in files)
    return service_pid, web_pid


def _stand_in(tmp_path: Path, name: str, seconds: int = 300) -> str:
    # `exec` so the recorded PID is the long-running process itself.
    return f"echo $$ > {tmp_path / name}.pid; exec sleep {seconds}"


def test_script_exists_and_is_executable() -> None:
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def test_print_shows_default_commands() -> None:
    out = subprocess.run(
        ["bash", str(SCRIPT), "--print"], capture_output=True, text=True, check=True
    ).stdout
    assert "uvicorn boor_service.api:app --reload" in out
    assert "--port 8000" in out
    assert "pnpm dev" in out
    assert "3000" in out


def test_print_passes_service_env_file_by_path_only(tmp_path: Path) -> None:
    env_file = tmp_path / "service.env"
    env_file.write_text("SENTINEL_VALUE_MUST_NOT_BE_PRINTED=1\n")
    out = subprocess.run(
        ["bash", str(SCRIPT), "--print"],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "BOOR_SERVICE_ENV_FILE": str(env_file)},
    ).stdout
    assert f"--env-file {env_file}" in out
    assert "SENTINEL_VALUE_MUST_NOT_BE_PRINTED" not in out


def test_interrupt_stops_both(tmp_path: Path) -> None:
    proc = _start(tmp_path, _stand_in(tmp_path, "service"), _stand_in(tmp_path, "web"))
    try:
        assert _wait_for(lambda: _pids(tmp_path) is not None), "both processes should start"
        pids = _pids(tmp_path)
        assert pids is not None
        assert all(_pid_alive(p) for p in pids)

        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=15)

        assert _wait_for(lambda: not any(_pid_alive(p) for p in pids)), "Ctrl-C stops both"
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)


def test_one_exiting_stops_the_other(tmp_path: Path) -> None:
    proc = _start(
        tmp_path,
        f"echo $$ > {tmp_path / 'service.pid'}; sleep 1; exit 3",
        _stand_in(tmp_path, "web"),
    )
    try:
        assert _wait_for(lambda: _pids(tmp_path) is not None)
        pids = _pids(tmp_path)
        assert pids is not None
        returncode = proc.wait(timeout=15)
        assert returncode != 0, "a crashed child should fail the runner"
        assert _wait_for(lambda: not _pid_alive(pids[1])), "the survivor is stopped"
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)


@pytest.mark.skipif(
    subprocess.run(["which", "shellcheck"], capture_output=True).returncode != 0,
    reason="shellcheck not installed",
)
def test_shellcheck_clean() -> None:
    subprocess.run(["shellcheck", str(SCRIPT)], check=True)
