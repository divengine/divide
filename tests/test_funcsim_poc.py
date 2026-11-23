"""The line trace of the proof of concept of #15 (prototypes/function-simulation): a Function's PHP
lines over Xdebug (DBGp, non-interactive), until #22 promotes it. The engine's cases (doubles,
scenarios, limits, the tripwire) moved with the engine to tests/test_funcsim.py (#21).

These tests need Xdebug (php.ini or DIVIDE_XDEBUG=path/xdebug.so)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "prototypes" / "function-simulation"
_spec = importlib.util.spec_from_file_location("funcsim_poc", PROTO / "funcsim.py")
fs = importlib.util.module_from_spec(_spec)
sys.modules["funcsim_poc"] = fs
_spec.loader.exec_module(fs)  # type: ignore[union-attr]

pytestmark = pytest.mark.skipif(not shutil.which("php"), reason="needs php")
XDEBUG = os.environ.get("DIVIDE_XDEBUG")


def _xdebug() -> bool:
    if not shutil.which("php"):
        return False
    if XDEBUG and Path(XDEBUG).is_file():
        return True
    return "xdebug" in subprocess.run(["php", "-m"], capture_output=True, text=True).stdout.lower().split()


needs_xdebug = pytest.mark.skipif(not _xdebug(), reason="needs Xdebug (php.ini or DIVIDE_XDEBUG=path/xdebug.so)")
INI = ["-d", f"zend_extension={XDEBUG}"] if XDEBUG and Path(XDEBUG).is_file() else []


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(PROTO / "example", root)
    return root.resolve()


def scenario(name: str = "checkout", **extra) -> dict:
    data = json.loads((PROTO / "example" / "checkout.scenario.json").read_text(encoding="utf-8"))
    data["function"] = {"module": None, "name": name}
    data.update(extra)
    return data


def write(project: Path, name: str, body: str) -> Path:
    path = project / "functions" / f"{name}.php"
    path.write_text("<?php\n\ndeclare(strict_types=1);\n\n" + body, encoding="utf-8")
    return path


def sim(project: Path, file: Path, data: dict, **kwargs) -> fs.Simulation:
    kwargs.setdefault("ini", INI)
    return asyncio.run(fs.simulate(project, file, data, **kwargs))


# ------------------------------------------------------------------ the scenario
def test_the_example_scenario_is_valid():
    assert fs.check_scenario(scenario()) == []


# ------------------------------------------------------------------ the line trace
@needs_xdebug
def test_the_line_trace_records_the_functions_lines_and_locals(project):
    result = sim(project, project / "functions" / "checkout.php", scenario(), trace=True)
    assert result.status == "returned" and result.result["return"] == "notified"
    lines = [e["line"] for e in result.events]
    assert lines[:6] == [7, 8, 9, 10, 9, 10]  # the loop, twice
    assert 15 in lines and 16 in lines  # the branch taken
    first = result.events[0]["locals"]["set"]
    assert first["context.email"] == "buyer@example.com" and "context._importer" not in first
    assert result.events[1]["locals"]["set"] == {"total": 0.0}
    by_line = {e["line"]: e for e in result.events}
    assert by_line[14]["locals"]["set"]["total"] == 121.0  # after the tax double answered on line 13
    assert by_line[14]["locals"]["set"]["context.tax_rate"] == 0.21
    assert all(e["depth"] == 0 for e in result.events)  # the doubles' own code is not traced
    doc = result.document(project, project / "functions" / "checkout.php", scenario())
    assert doc["protocol"] == "divide.function-trace" and doc["version"] == 1
    assert doc["function"]["file"] == "functions/checkout.php"


@needs_xdebug
def test_observing_locals_does_not_change_the_function(project):
    plain = sim(project, project / "functions" / "checkout.php", scenario())
    traced = sim(project, project / "functions" / "checkout.php", scenario(), trace=True)
    assert traced.result["return"] == plain.result["return"]
    assert traced.result["after"] == plain.result["after"]
    assert traced.result["calls"] == plain.result["calls"]


@needs_xdebug
def test_a_branch_not_taken_has_no_line(project):
    data = scenario(context={"items": [{"price": 1, "qty": 1}], "email": "a@b"})
    result = sim(project, project / "functions" / "checkout.php", data, trace=True)
    lines = [e["line"] for e in result.events]
    assert 14 in lines and 15 not in lines and 16 not in lines


@needs_xdebug
def test_the_line_trace_is_bounded(project):
    file = project / "functions" / "busy.php"
    result = sim(project, file, scenario("busy", context={"n": 1000}, doubles={}, limits={"lines": 50}), trace=True)
    assert result.status == "line_limit" and result.truncated and len(result.events) == 50


@needs_xdebug
def test_the_line_trace_of_an_exception_ends_on_its_line(project):
    data = scenario(doubles={"importer": {"billing:tax": {"returns": 1.0}}, "services": {"mailer": {"queue": {"returns": 1}}}})
    result = sim(project, project / "functions" / "checkout.php", data, trace=True)
    assert result.status == "exception" and result.result["exception"]["missing_double"] is True
    assert result.events[-1]["line"] == 18  # the mailer call
