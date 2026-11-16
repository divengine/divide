"""The processes divide starts die with it.

Language servers (phpactor indexes the whole project), PHP scripts under
Xdebug, ``php -S``, renders: none of them may outlive divide, whichever way it
ends (Alt+X, an error, Ctrl+C, a test that leaves, a kill). Two guards:

- every process is started with ``options()``: on Linux the kernel sends it
  SIGTERM when divide dies (``PR_SET_PDEATHSIG``), even if divide is killed;
- every process is ``track()``-ed, and ``kill_all()`` (when the app closes,
  and at exit) kills the ones still running.
"""

from __future__ import annotations

import atexit
import signal
import sys

_PR_SET_PDEATHSIG = 1
_running: list = []  # asyncio.subprocess.Process (or anything with .returncode and .kill())


def _die_with_parent() -> None:  # runs in the child, before exec
    import ctypes

    ctypes.CDLL(None, use_errno=True).prctl(_PR_SET_PDEATHSIG, signal.SIGTERM)


def options() -> dict:
    """Keyword arguments for ``asyncio.create_subprocess_exec``."""
    return {"preexec_fn": _die_with_parent} if sys.platform.startswith("linux") else {}


def track(process):
    """Remember ``process`` to kill it when divide ends; returns it."""
    _running[:] = [p for p in _running if p.returncode is None]
    if process is not None:
        _running.append(process)
    return process


def running() -> list:
    return [p for p in _running if p.returncode is None]


def kill_all() -> None:
    """Kill every process divide started that still runs."""
    for process in running():
        try:
            process.kill()
        except (ProcessLookupError, OSError):
            pass
    _running.clear()


atexit.register(kill_all)
