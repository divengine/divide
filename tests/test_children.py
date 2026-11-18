"""The processes divide starts die with it (language servers, PHP, php -S)."""

import asyncio
import os
import subprocess
import sys
import time

import pytest

from divide.run import children


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # a zombie is dead too: it only waits for its parent to read it
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as stat:
            return stat.read().split(")")[-1].split()[0] != "Z"
    except (ProcessLookupError, FileNotFoundError):  # it ended between the two looks
        return False


async def test_kill_all_kills_what_still_runs():
    proc = children.track(await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(30)", **children.options()))
    assert proc in children.running()
    children.kill_all()
    await asyncio.wait_for(proc.wait(), 5)
    assert children.running() == []


async def test_killing_a_process_that_just_ended_is_no_error():
    """A worker cancelled as its php ends (the dialector's verdict as you type)."""
    proc = await asyncio.create_subprocess_exec(sys.executable, "-c", "pass", stdout=asyncio.subprocess.PIPE)
    await proc.communicate()
    children.kill(proc)  # (proc.kill() itself may raise ProcessLookupError here, or not: it depends on the Python)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PR_SET_PDEATHSIG is Linux's")
def test_a_child_dies_when_divide_is_killed(tmp_path):
    """divide killed outright (no atexit, no unmount): the kernel ends its children."""
    pidfile = tmp_path / "pid"
    parent = subprocess.Popen([sys.executable, "-c", f"""
import asyncio
from divide.run import children
async def main():
    proc = await asyncio.create_subprocess_exec("sleep", "30", **children.options())
    open({str(pidfile)!r} + ".part", "w").write(str(proc.pid))
    import os
    os.replace({str(pidfile)!r} + ".part", {str(pidfile)!r})  # whole, never half written
    await asyncio.sleep(30)
asyncio.run(main())
"""])
    try:
        deadline = time.monotonic() + 10
        while not (pidfile.exists() and pidfile.read_text(encoding="utf-8")) and time.monotonic() < deadline:
            time.sleep(0.05)
        pid = int(pidfile.read_text(encoding="utf-8"))
        assert alive(pid)
        parent.kill()
        parent.wait(5)
        deadline = time.monotonic() + 5
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not alive(pid)
    finally:
        parent.kill()
