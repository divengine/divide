"""The proof of concept of #15 (prototypes/function-simulation): Mock Simulation of one Runner
Function with dependency doubles, and its PHP line trace over Xdebug (DBGp, non-interactive).

The line-trace tests need Xdebug (php.ini or DIVIDE_XDEBUG=path/xdebug.so)."""

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


@pytest.mark.parametrize("change, problem", [
    ({"version": 2}, "not divide.function-simulation version 1"),
    ({"unknown": "real"}, "unknown: only"),
    ({"context": {"_flow_state": {}}}, "belong to Runner"),
    ({"doubles": {"importer": {"tax": {"returns": 1, "throws": "x"}}}}, "exactly one of"),
    ({"doubles": {"importer": {"tax": {"sequence": []}}}}, "non-empty list"),
    ({"doubles": {"importer": {"tax": {"returns": 1, "context": {"_x": 1}}}}}, "without '_' keys"),
    ({"doubles": {"services": {"mailer": {}}}}, "an object of methods"),
    ({"doubles": {"classes": {}}}, "importer and services only"),
    ({"limits": {"lines": 10 ** 9}}, "limits.lines"),
    ({"function": {"name": "x", "sha256": "abc"}}, "sha256 hex digest"),
])
def test_a_wrong_scenario_is_refused_before_anything_runs(project, change, problem):
    data = scenario(**change) if "function" not in change else {**scenario(), **change}
    assert any(problem in p for p in fs.check_scenario(data))
    marker = project / "ran"
    file = write(project, "marker", f"file_put_contents({str(marker)!r}, 'x');\nreturn fn (array &$c) => 1;\n")
    with pytest.raises(fs.ScenarioError):
        sim(project, file, data)
    assert not marker.exists()


# ------------------------------------------------------------------ doubles
def test_doubles_answer_and_are_recorded(project):
    result = sim(project, project / "functions" / "checkout.php", scenario())
    assert result.status == "returned"
    assert result.result["return"] == "notified"
    assert result.result["after"]["total"] == 121.0 and result.result["after"]["tax_rate"] == 0.21
    assert "mailer" not in result.result["after"]  # a service double is not data
    assert [c["double"] for c in result.result["calls"]] == ["billing:tax", "mailer->send"]
    assert result.result["calls"][1]["args"] == ["buyer@example.com", "Total: 121"]
    assert result.result["logs"] == [{"level": "INFO", "message": "large order"}]
    assert result.result["stdout"] == "sent: yes\n"


def test_a_missing_import_double_fails_loudly_and_never_loads_the_real_function(project):
    real = project / "functions" / "billing"
    real.mkdir()
    marker = project / "real-tax-loaded"
    (real / "tax.php").write_text(f"<?php\nfile_put_contents({str(marker)!r}, 'x');\nreturn fn (array &$c) => 1.0;\n")
    data = scenario(doubles={"services": {"mailer": {"send": {"returns": True}}}})
    result = sim(project, project / "functions" / "checkout.php", data)
    assert result.status == "exception"
    assert result.result["exception"]["missing_double"] is True
    assert "billing:tax" in result.result["exception"]["message"]
    assert not marker.exists()


def test_a_missing_service_method_fails_loudly(project):
    data = scenario(doubles={"importer": {"billing:tax": {"returns": 1.0}}, "services": {"mailer": {"queue": {"returns": 1}}}})
    result = sim(project, project / "functions" / "checkout.php", data)
    assert result.status == "exception" and result.result["exception"]["missing_double"] is True
    assert "mailer->send" in result.result["exception"]["message"]


def test_a_sequence_answers_in_order_and_fails_past_its_end(project):
    file = write(project, "twice", 'return function (array &$c): array {\n'
                 '    $f = $c["_importer"]("rate");\n    return [$f($c), $f($c)];\n};\n')
    ok = sim(project, file, scenario("twice", doubles={"importer": {"rate": {"sequence": [{"returns": 1}, {"returns": 2}]}}}))
    assert ok.result["return"] == [1, 2]
    short = sim(project, file, scenario("twice", doubles={"importer": {"rate": {"sequence": [{"returns": 1}]}}}))
    assert short.status == "exception" and "no outcome for call 2" in short.result["exception"]["message"]


def test_a_throwing_double_is_the_functions_exception(project):
    data = scenario(doubles={"importer": {"billing:tax": {"throws": "tax service down"}},
                             "services": {"mailer": {"send": {"returns": True}}}})
    result = sim(project, project / "functions" / "checkout.php", data)
    assert result.status == "exception"
    assert result.result["exception"]["message"] == "tax service down"
    assert result.result["exception"]["missing_double"] is False


def test_a_class_is_not_autoloaded_unless_the_scenario_opts_in(project):
    (project / "vendor").mkdir()
    marker = project / "autoload-ran"
    (project / "vendor" / "autoload.php").write_text(
        f"<?php\nfile_put_contents({str(marker)!r}, 'x');\n"
        "spl_autoload_register(function ($c) { if ($c === 'Acme\\\\Mailer') { eval('namespace Acme; class Mailer { function send() { return 1; } }'); } });\n")
    file = write(project, "uses_class", "return fn (array &$c) => (new \\Acme\\Mailer())->send();\n")
    refused = sim(project, file, scenario("uses_class"))
    assert refused.status == "exception" and refused.result["exception"]["missing_double"] is True
    assert "Acme\\Mailer" in refused.result["exception"]["message"]
    assert not marker.exists()
    allowed = sim(project, file, scenario("uses_class", autoload=True))
    assert allowed.status == "returned" and allowed.result["return"] == 1 and marker.exists()


def test_a_changed_function_is_stale(project):
    file = project / "functions" / "checkout.php"
    data = scenario()
    data["function"]["sha256"] = "0" * 64
    result = sim(project, file, data)
    assert result.status == "stale" and result.result["sha256"] == fs.sha256(file)


# ------------------------------------------------------------------ not a sandbox
def test_a_direct_side_effect_is_not_intercepted_without_the_tripwire(project, tmp_path):
    target = tmp_path / "outside.txt"
    data = scenario("direct_write", context={"path": str(target)}, doubles={})
    result = sim(project, project / "functions" / "direct_write.php", data)
    assert result.status == "returned" and result.result["return"] is True
    assert target.read_text() == "real write"  # the evidence: doubles do not stop PHP's own functions


def test_the_tripwire_stops_some_direct_side_effects(project, tmp_path):
    target = tmp_path / "outside.txt"
    data = scenario("direct_write", context={"path": str(target)}, doubles={})
    result = sim(project, project / "functions" / "direct_write.php", data, harden=True)
    assert result.status == "exception", result.stderr
    assert "file_put_contents" in result.result["exception"]["message"]
    assert not target.exists()


def test_the_tripwire_is_a_deny_list_not_a_sandbox(project, tmp_path):
    target = project / "inside.txt"  # inside open_basedir, by a function not on the list
    file = write(project, "fopen_write", 'return function (array &$c): bool {\n'
                 '    $h = fopen($c["path"], "w");\n    return stream_copy_to_stream(fopen("php://memory", "r"), $h) !== false;\n};\n')
    result = sim(project, file, scenario("fopen_write", context={"path": str(target)}, doubles={}), harden=True)
    assert result.status == "returned", result.stderr
    assert target.exists()  # created: fopen is not denied


def test_a_runaway_function_is_stopped_at_its_time_limit(project):
    file = write(project, "spin", "return function (array &$c): void { while (true) { } };\n")
    result = sim(project, file, scenario("spin", doubles={}, limits={"seconds": 2}))
    assert result.status == "timeout"


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
