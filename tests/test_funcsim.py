"""Function Mock Simulation (divide.run.funcsim, #21): one Runner Function run with declared dependency
doubles in its own PHP process, on copies of examples/runner and examples/generator.

A Mock Simulation runs real PHP: these tests show what is replaced (imports, services, the logger,
Composer classes unless opted in) and what is not (direct writes; the tripwire is not a sandbox).

Needs php; the tests that compare with Runner's own importer need
``composer install --working-dir examples/runner`` (and examples/generator)."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from divide import config
from divide.run import children
from divide.run import flowfunctions as ff
from divide.run import flowmodel as fm
from divide.run import funcsim as fs
from divide.run import functest as ft

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "examples" / "runner"
GENERATOR = ROOT / "examples" / "generator"
pytestmark = pytest.mark.skipif(not shutil.which("php"), reason="needs php")


def _installed(example: Path) -> bool:
    return (example / "vendor" / "divengine" / "runner" / "src" / "runner.php").is_file()


needs_runner = pytest.mark.skipif(not (_installed(RUNNER) and _installed(GENERATOR)),
                                  reason="needs composer install in examples/runner and examples/generator")

CHECKOUT = """// A Function written for injection: its dependencies come from the context.
return function (array &$context): string {
    $total = 0.0;
    foreach ($context["items"] ?? [] as $item) {
        $total += $item["price"] * $item["qty"];
    }
    $tax = $context["_importer"]("tax", "billing");
    $total += $tax($context);
    if ($total > 100) {
        $context["_logger"]("INFO", "large order", ["total" => $total]);
        $context["review"] = true;
    }
    $sent = $context["mailer"]->send($context["email"], "Total: " . $total);
    $context["total"] = $total;
    echo "sent: ", $sent ? "yes" : "no", "\\n";
    return $sent ? "notified" : "pending";
};
"""


def _copy(example: Path, root: Path, *, vendor: bool) -> Path:
    shutil.copytree(example, root, ignore=shutil.ignore_patterns("vendor", "composer.lock", "build", ".div"))
    if vendor and (example / "vendor").is_dir():
        try:
            (root / "vendor").symlink_to(example / "vendor", target_is_directory=True)
        except OSError:  # Windows without the right to make links
            shutil.copytree(example / "vendor", root / "vendor")
    return root.resolve()


@pytest.fixture
def project(tmp_path) -> Path:
    """examples/runner (function root ``functions``, as its Flows run), trusted, with no Composer vendor."""
    root = _copy(RUNNER, tmp_path / "runner", vendor=False)
    (root / ".div").mkdir()
    (root / ".div" / "runner.json").write_text(json.dumps({"root": "functions", "modules": {}}), encoding="utf-8")
    write(root, "checkout", CHECKOUT)
    fs.trust(root)
    return root


def write(project: Path, name: str, body: str) -> Path:
    path = project / "functions" / f"{name}.php"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<?php\n\ndeclare(strict_types=1);\n\n" + body, encoding="utf-8")
    return path


def scenario(name: str = "checkout", module: str | None = None, **extra) -> dict:
    data = {
        "protocol": "divide.function-simulation", "version": 1,
        "description": "A large order: tax doubled, the mailer accepts",
        "function": {"module": module, "name": name},
        "context": {"items": [{"price": 60, "qty": 1}, {"price": 20, "qty": 2}], "email": "buyer@example.com"},
        "doubles": {"importer": {"billing:tax": {"returns": 21.0, "context": {"tax_rate": 0.21}}},
                    "services": {"mailer": {"send": {"sequence": [{"returns": True}]}}}},
        "unknown": "fail",
        "expect": {"returns": "notified", "context": {"review": True}},
        "limits": {"lines": 2000, "seconds": 20, "stdout": 65536},
    }
    data.update(extra)
    return data


def sim(project: Path, data: dict, functions: fm.Functions | None = None, **kwargs) -> fs.Simulation:
    return asyncio.run(fs.simulate(fs.request_for(project, data, functions), **kwargs))


def just(**context) -> dict:
    """A scenario with no doubles for a Function written by the test."""
    return scenario("t", context=context, doubles={}, expect={})


# ---------------------------------------------------------------- the scenario
def test_a_new_scenario_is_valid_and_pinned_to_the_file(project):
    file = project / "functions" / "checkout.php"
    data = fs.new_scenario(None, "checkout", file)
    assert fs.check_scenario(data) == [] and fs.check_scenario(scenario()) == []
    assert data["function"]["sha256"] == fs.sha256(file) and data["unknown"] == "fail" and data["autoload"] is False


@pytest.mark.parametrize("change, problem", [
    ({"version": 2}, "Not divide.function-simulation version 1"),
    ({"protocol": "runner.simulate"}, "Not divide.function-simulation"),
    ({"classes": {}}, "Unknown keys: classes"),
    ({"unknown": "real"}, "unknown: only"),
    ({"context": {"_flow_state": {}}}, "belong to Runner"),
    ({"context": []}, "context is a JSON object"),
    ({"function": {"name": ""}}, "function.name is missing"),
    ({"function": {"module": "bad mod", "name": "x"}}, "not a Runner reference"),
    ({"function": {"module": "billing", "name": "../x"}}, "not a Runner reference"),
    ({"function": {"name": "x", "sha256": "abc"}}, "sha256 hex digest"),
    ({"doubles": {"importer": {"tax": {"returns": 1, "throws": "x"}}}}, "exactly one of"),
    ({"doubles": {"importer": {"tax": {}}}}, "exactly one of returns, throws, sequence (none)"),
    ({"doubles": {"importer": {"tax": {"sequence": []}}}}, "non-empty list"),
    ({"doubles": {"importer": {"tax": {"sequence": [{"sequence": [{"returns": 1}]}]}}}}, "cannot hold a sequence"),
    ({"doubles": {"importer": {"tax": {"returns": 1, "context": {"_x": 1}}}}}, "without '_' keys"),
    ({"doubles": {"importer": {"tax": {"throws": 3}}}}, "throws is a message"),
    ({"doubles": {"importer": {"tax": {"returns": 1, "real": True}}}}, "unknown real"),
    ({"doubles": {"services": {"mailer": {}}}}, "an object of methods"),
    ({"doubles": {"services": {"_logger": {"x": {"returns": 1}}}}}, "'_' keys belong to Runner"),
    ({"doubles": {"services": {"email": {"x": {"returns": 1}}}}}, "also in the context"),
    ({"doubles": {"classes": {}}}, "importer and services only"),
    ({"limits": {"seconds": 0}}, "limits.seconds: 1..300"),
    ({"limits": {"lines": 100_001}}, "limits.lines: 1..100000"),
    ({"limits": {"stdout": True}}, "limits.stdout"),
    ({"limits": {"memory": 1}}, "limits has"),
    ({"autoload": "yes"}, "autoload is true or false"),
    ({"expect": {"returns": 1, "context_after": {}}}, "expect has returns and context only"),
    ({"expect": {"context": [1]}}, "expect.context is a JSON object"),
])
def test_a_wrong_scenario_is_refused(change, problem):
    data = scenario()
    data.update(change)
    problems = fs.check_scenario(data)
    assert any(problem in p for p in problems), problems


def test_a_wrong_scenario_starts_no_process(project, monkeypatch):
    marker = project / "ran.txt"
    write(project, "t", f"file_put_contents({json.dumps(str(marker))}, 'ran');\nreturn fn (array &$c) => 1;\n")
    started = []
    monkeypatch.setattr(fs, "run_script", lambda *a, **k: started.append(a))
    bad = just() | {"unknown": "real"}
    with pytest.raises(fs.ScenarioError) as refused:
        fs.request_for(project, bad)
    assert "unknown" in str(refused.value)
    good = fs.request_for(project, just())
    with pytest.raises(fs.ScenarioError):
        asyncio.run(fs.simulate(fs.SimRequest(good.project, bad, good.file)))
    assert not started and not marker.exists()


# ---------------------------------------------------------------- trust
def test_the_first_simulation_needs_the_projects_opt_in_kept_in_the_users_settings(project, monkeypatch):
    fs.distrust(project)
    started = []
    monkeypatch.setattr(fs, "run_script", lambda *a, **k: started.append(a))
    with pytest.raises(fs.NotTrusted):
        sim(project, scenario())
    assert not started
    fs.trust(project)
    assert fs.trusted(project) and str(project.resolve()) in config.load()[fs.TRUST_KEY]
    on_disk = [p.relative_to(project).as_posix() for p in (project / ".div").rglob("*")]
    assert on_disk == [".div/runner.json"], "the opt-in is never written into the project"
    fs.distrust(project)
    assert not fs.trusted(project)


def test_the_labels_never_claim_isolation():
    assert "real PHP runs" in fs.LABEL and "MOCK SIMULATION" in fs.LABEL
    assert "not a sandbox" in fs.TRIPWIRE_LABEL and "not a sandbox" in fs.TRUST_TEXT


# ---------------------------------------------------------------- doubles
def test_doubles_answer_are_recorded_and_the_expectations_hold(project):
    out = sim(project, scenario())
    assert out.status == "returned", (out.message, out.stderr, out.exception)
    assert out.returned == "notified" and out.return_type == "string"
    assert out.after["total"] == 121.0 and out.after["review"] is True and out.after["tax_rate"] == 0.21
    assert "_importer" not in out.after and "_logger" not in out.after and "mailer" not in out.after
    assert out.before == scenario()["context"]
    assert [(c["double"], c["outcome"]) for c in out.calls] == [("billing:tax", "returns"), ("mailer->send", "returns")]
    assert out.calls[1]["args"] == ["buyer@example.com", "Total: 121"]
    assert out.logs == [{"level": "INFO", "message": "large order", "data": {"total": 121.0}}]
    assert out.output == "sent: yes\n" and out.output_cut == 0 and out.leaked == ""
    assert fs.check(out) == [(True, 'returns "notified"'), (True, 'the context after has {"review": true}')]
    assert {c.path for c in out.changes} >= {"total", "review", "tax_rate"}
    result = out.result()
    assert result["status"] == "returned" and result["stdout"] == "sent: yes\n" and result["tripwire"] is False


def test_an_expectation_that_does_not_hold_is_reported(project):
    out = sim(project, scenario(expect={"returns": "pending", "context": {"total": 1}}))
    assert out.ok and fs.check(out) == [(False, 'returns "pending"'), (False, 'the context after has {"total": 1}')]


def test_a_missing_import_double_fails_loudly_and_never_requires_the_real_function(project):
    marker = project / "real-tax-ran.txt"
    write(project, "billing/tax", f"file_put_contents({json.dumps(str(marker))}, 'x');\n"
                                  "return fn (array &$c) => 999.0;\n")
    data = scenario()
    data["doubles"]["importer"] = {"tax": {"returns": 1.0}}  # billing:tax is asked for, not tax
    out = sim(project, data)
    assert out.status == "exception" and out.missing_double
    assert "billing:tax" in out.exception["message"]
    assert {"double": "import billing:tax", "outcome": "missing"} in out.calls
    assert not marker.exists(), "the real Function file was required"


def test_a_missing_service_method_fails_loudly(project):
    data = scenario()
    data["doubles"]["services"]["mailer"] = {"queue": {"returns": True}}
    out = sim(project, data)
    assert out.status == "exception" and out.missing_double and "mailer->send" in out.exception["message"]


def test_a_service_property_is_not_doubled(project):
    write(project, "t", "return fn (array &$c) => $c['repo']->name;\n")
    data = just() | {"doubles": {"services": {"repo": {"find": {"returns": 1}}}}}
    out = sim(project, data)
    assert out.status == "exception" and out.missing_double and "repo->name" in out.exception["message"]


def test_a_service_absent_from_the_doubles_is_not_invented(project):
    data = scenario()
    del data["doubles"]["services"]
    out = sim(project, data)
    assert out.status in ("exception", "fatal") and not out.ok  # $context["mailer"] is undefined: PHP's own error


def test_a_sequence_answers_in_order_and_fails_past_its_end(project):
    write(project, "t", """return function (array &$c): array {
    $next = $c["_importer"]("next");
    return [$next($c), $next($c), $next($c)];
};
""")
    seq = {"sequence": [{"returns": 1}, {"returns": 2, "context": {"seen": 2}}]}
    out = sim(project, just() | {"doubles": {"importer": {"next": seq}}})
    assert out.status == "exception" and out.missing_double and "call 3" in out.exception["message"]
    assert [c.get("call") for c in out.calls] == [1, 2, 3] and out.calls[-1]["outcome"] == "exhausted"
    assert out.after["seen"] == 2
    seq["sequence"].append({"returns": 3})
    out = sim(project, just() | {"doubles": {"importer": {"next": seq}}})
    assert out.ok and out.returned == [1, 2, 3]


def test_a_throwing_double_is_the_functions_exception(project):
    data = scenario()
    data["doubles"]["services"]["mailer"]["send"] = {"throws": "SMTP down"}
    out = sim(project, data)
    assert out.status == "exception" and not out.missing_double
    assert out.exception["class"] == "RuntimeException" and out.exception["message"] == "SMTP down"
    assert out.after["review"] is True  # what ran before the throw is kept


def test_the_logger_is_recorded(project):
    write(project, "t", "return function (array &$c): int { $c['_logger']('WARNING', 'low stock'); return 1; };\n")
    assert sim(project, just()).logs == [{"level": "WARNING", "message": "low stock"}]


# ---------------------------------------------------------------- what is not replaced
def test_the_projects_autoload_is_off_unless_the_scenario_opts_in(project):
    marker = project / "autoload-ran.txt"
    (project / "vendor").mkdir()
    (project / "vendor" / "autoload.php").write_text(
        "<?php\nfile_put_contents(" + json.dumps(str(marker)) + ", 'x');\n"
        "spl_autoload_register(function ($c) { if ($c === 'Acme\\\\Clock') { eval('namespace Acme; '\n"
        "  . 'final class Clock { public function now(): string { return \"real\"; } }'); } });\n", encoding="utf-8")
    write(project, "t", "return fn (array &$c): string => (new Acme\\Clock())->now();\n")
    out = sim(project, just())
    assert out.status == "exception" and out.missing_double and "Acme\\Clock" in out.exception["message"]
    assert not marker.exists(), "the project's autoload ran without the opt-in"
    out = sim(project, just() | {"autoload": True})
    assert out.ok and out.returned == "real" and marker.exists()


def test_a_changed_function_is_stale_and_not_called(project):
    marker = project / "called.txt"
    file = write(project, "t", f"return function (array &$c): int {{ file_put_contents({json.dumps(str(marker))}, 'x'); return 1; }};\n")
    data = fs.new_scenario(None, "t", file)
    file.write_text(file.read_text(encoding="utf-8") + "// edited\n", encoding="utf-8")
    out = sim(project, data)
    assert out.status == "stale" and out.sha256 == fs.sha256(file) and not marker.exists()


def test_a_function_that_does_not_exist_is_missing_without_a_process(project, monkeypatch):
    started = []
    monkeypatch.setattr(fs, "run_script", lambda *a, **k: started.append(a))
    out = sim(project, scenario("nowhere", "billing"))
    assert out.status == "missing" and "billing:nowhere" in out.message and not started


def test_a_file_that_returns_no_callable_is_missing(project):
    write(project, "t", "return 42;\n")
    out = sim(project, just())
    assert out.status == "missing" and "does not return a callable" in out.message


def test_the_files_top_level_code_runs_for_real(project):
    marker = project / "top-level.txt"
    write(project, "t", f"file_put_contents({json.dumps(str(marker))}, 'x');\nreturn fn (array &$c) => 1;\n")
    assert sim(project, just()).ok and marker.exists()


def test_a_direct_side_effect_is_not_intercepted_without_the_tripwire(project, tmp_path):
    target = tmp_path / "outside.txt"
    write(project, "t", "return fn (array &$c): bool => file_put_contents($c['path'], 'real write') !== false;\n")
    out = sim(project, just(path=str(target)))
    assert out.ok and out.returned is True and target.read_text(encoding="utf-8") == "real write"


def test_the_tripwire_stops_some_direct_side_effects(project, tmp_path):
    target = tmp_path / "outside.txt"
    write(project, "t", "return fn (array &$c): bool => file_put_contents($c['path'], 'real write') !== false;\n")
    out = sim(project, just(path=str(target)), tripwire=True)
    assert out.tripwire and out.status in ("fatal", "exception"), out.stderr
    assert not target.exists()


def test_the_tripwire_is_a_deny_list_not_a_sandbox(project):
    target = project / "inside.txt"
    write(project, "t", """return function (array &$c): bool {
    $out = fopen($c['path'], 'w');
    $in = fopen('php://memory', 'r+');
    fprintf($in, 'still written');
    rewind($in);
    stream_copy_to_stream($in, $out);
    return fclose($out);
};
""")
    out = sim(project, just(path=str(target)), tripwire=True)
    assert out.ok, out.stderr
    assert target.read_text(encoding="utf-8") == "still written"


# ---------------------------------------------------------------- bounds
def test_the_functions_output_is_bounded_and_cannot_break_the_result(project):
    write(project, "t", """return function (array &$c): string {
    echo str_repeat('x', 5000);
    fprintf(STDOUT, "\\n{\\"status\\":\\"forged\\"}\\n");
    return 'done';
};
""")
    out = sim(project, just() | {"limits": {"stdout": 100}})
    assert out.ok and out.returned == "done"
    assert out.output == "x" * 100 and out.output_cut == 4900
    assert "forged" in out.leaked


def test_an_error_and_exit_are_reported(project):
    write(project, "t", "return function (array &$c): int { $c['x'] = 1; undefined_function(); };\n")
    out = sim(project, just())
    assert out.status == "exception" and out.exception["class"] == "Error"
    write(project, "t", "return function (array &$c): int { $c['x'] = 1; exit(3); };\n")
    out = sim(project, just())
    assert out.status == "exit" and out.after == {"x": 1}


def test_memory_limit_applies(project, monkeypatch):
    monkeypatch.setattr(fs, "MEMORY", "32M")
    write(project, "t", "return fn (array &$c): int => strlen(str_repeat('x', 64 * 1024 * 1024));\n")
    out = sim(project, just())
    assert out.status == "fatal" and "Allowed memory size" in out.error["message"]


def _no_php_left() -> None:
    assert children.running() == [], "a PHP process outlived the simulation"


def test_a_runaway_function_is_killed_at_its_time_limit(project):
    write(project, "t", "return function (array &$c): void { while (true) { usleep(1000); } };\n")
    out = sim(project, just() | {"limits": {"seconds": 1}})
    assert out.status == "timeout" and 0.9 < out.seconds < 15
    _no_php_left()


def test_cancelling_a_simulation_kills_php(project):
    write(project, "t", "return function (array &$c): void { while (true) { usleep(1000); } };\n")
    request = fs.request_for(project, just())

    async def go() -> None:
        task = asyncio.ensure_future(fs.simulate(request))
        for _ in range(200):
            await asyncio.sleep(0.05)
            if children.running():
                break
        assert children.running(), "PHP never started"
        await asyncio.sleep(0.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
    _no_php_left()


# ---------------------------------------------------------------- resolution, as Runner's importer
@needs_runner
def test_a_module_function_resolves_as_runners_importer_would(tmp_path):
    root = _copy(RUNNER, tmp_path / "runner", vendor=True)
    fs.trust(root)
    functions = fm.functions_for(root, "functions", {}, ff.load_settings(root))  # the Flows' --root functions
    context = {"items": [{"price": 10, "qty": 2}, {"price": 5, "qty": 1}]}
    data = scenario("total", "billing", context=context, doubles={}, expect={"returns": 25.0})
    request = fs.request_for(root, data, functions)
    real = asyncio.run(ft.run_test(ft.request_for(root, functions, "billing", "total", context)))
    assert real.ok and Path(real.resolved["file"]).resolve() == request.file
    out = asyncio.run(fs.simulate(request))
    assert out.ok and out.returned == real.returned == 25.0 and fs.check(out) == [(True, "returns 25.0")]


@needs_runner
def test_a_module_function_resolves_through_the_projects_runner_json(tmp_path):
    root = _copy(GENERATOR, tmp_path / "generator", vendor=True)
    (root / ".div").mkdir(exist_ok=True)
    shutil.copy(GENERATOR / ".div" / "runner.json", root / ".div" / "runner.json")
    fs.trust(root)
    context = {"problems": ["no name"]}
    request = fs.request_for(root, scenario("reject", "validate", context=context, doubles={}, expect={}))
    real = asyncio.run(ft.run_test(ft.request_for(root, fs.functions(root), "validate", "reject", context)))
    assert real.status == "exception" and Path(real.resolved["file"]).resolve() == request.file
    out = asyncio.run(fs.simulate(request))
    assert out.status == "exception" and not out.missing_double
    assert out.exception["message"] == real.exception["message"]


@needs_runner
def test_a_mapped_module_folder_resolves_as_runners_importer_would(tmp_path):
    root = _copy(RUNNER, tmp_path / "runner", vendor=True)
    (root / ".div").mkdir()
    (root / ".div" / "runner.json").write_text(json.dumps({"root": "functions", "modules": {"pay": "functions/billing"}}),
                                               encoding="utf-8")
    fs.trust(root)
    context = {"items": [{"price": 3, "qty": 3}]}
    request = fs.request_for(root, scenario("total", "pay", context=context, doubles={}, expect={}))
    real = asyncio.run(ft.run_test(ft.request_for(root, fs.functions(root), "pay", "total", context)))
    assert real.ok and Path(real.resolved["file"]).resolve() == request.file == (root / "functions" / "billing" / "total.php").resolve()
    out = asyncio.run(fs.simulate(request))
    assert out.ok and out.returned == 9.0


# ---------------------------------------------------------------- scenarios in the project
def test_scenarios_are_saved_versioned_listed_and_loaded(project):
    data = scenario()
    path = fs.save_scenario(project, "large order", data)
    assert path == project / ".div" / "function-simulations" / "_root" / "checkout.large order.json"
    fs.save_scenario(project, "small", scenario(module="billing", name="total"))
    assert (project / ".div" / "function-simulations" / "billing" / "total.small.json").is_file()
    assert fs.list_scenarios(project, None, "checkout") == {"large order": path}
    assert fs.load_scenario(path) == data
    assert not list((project / ".div" / "function-simulations").rglob(".gitignore")), "scenarios are versioned"
    assert sim(project, fs.load_scenario(path)).ok


def test_a_wrong_scenario_is_not_saved_nor_loaded(project):
    with pytest.raises(fs.ScenarioError):
        fs.save_scenario(project, "x", scenario(unknown="real"))
    with pytest.raises(fs.SimulationError):
        fs.save_scenario(project, "a.b", scenario())
    with pytest.raises(fs.SimulationError):
        fs.save_scenario(project, "../up", scenario())
    assert not (project / ".div" / "function-simulations").exists()
    bad = project / ".div" / "function-simulations" / "_root" / "checkout.bad.json"
    bad.parent.mkdir(parents=True)
    bad.write_text(json.dumps(scenario(version=2)), encoding="utf-8")
    with pytest.raises(fs.ScenarioError):
        fs.load_scenario(bad)
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(fs.ScenarioError, match="not JSON"):
        fs.load_scenario(bad)
