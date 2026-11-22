"""Function tests (divide.run.functest): one Runner Function called with a JSON context in its own
PHP process, resolved by Runner's own importer, on a copy of examples/generator; the debugger
runs the same call (needs Xdebug: php.ini or DIVIDE_XDEBUG=path/xdebug.so).

Needs php and ``composer install --working-dir examples/generator``; skips without them.
"""

import asyncio
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from divide.run import flowfunctions as ff
from divide.run import flowmodel as fm
from divide.run import functest as ft

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "generator"
VENDOR = EXAMPLE / "vendor"
pytestmark = pytest.mark.skipif(
    not (shutil.which("php") and (VENDOR / "divengine" / "runner" / "src" / "runner.php").is_file()),
    reason="needs php and composer install --working-dir examples/generator")
XDEBUG = os.environ.get("DIVIDE_XDEBUG")


def _xdebug() -> bool:
    if not shutil.which("php"):
        return False
    if XDEBUG and Path(XDEBUG).is_file():
        return True
    return "xdebug" in subprocess.run(["php", "-m"], capture_output=True, text=True).stdout.lower().split()


needs_xdebug = pytest.mark.skipif(not _xdebug(), reason="needs Xdebug (php.ini or DIVIDE_XDEBUG=path/xdebug.so)")
MODEL = {"model": "model/package_info.json", "output": "build"}


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "generator"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build", "vendor", "composer.lock"))
    try:
        (root / "vendor").symlink_to(VENDOR, target_is_directory=True)
    except OSError:  # Windows without the right to make links
        shutil.copytree(VENDOR, root / "vendor")
    return root.resolve()


def functions(project: Path, context: dict | None = None) -> fm.Functions:
    return fm.functions_for(project, "", context or {}, ff.load_settings(project))


def call(project: Path, module, name, context=None, *, mapping=None, timeout=ft.TIMEOUT) -> ft.TestResult:
    request = ft.request_for(project, functions(project, mapping), module, name, context or {})
    return asyncio.run(ft.run_test(request, timeout=timeout))


def write(project: Path, rel: str, source: str) -> Path:
    path = project / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


# ------------------------------------------------------------------ what a call gives
def test_an_activity_returns_structured_output_and_changes_the_context_by_reference(project):
    before = (project / "functions/load_model.php").read_text()
    result = call(project, None, "load_model", MODEL)
    assert (result.status, result.return_type, result.returned) == ("returned", "string", "model/package_info.json")
    assert result.resolved["file"] == str(project / "functions/load_model.php") and result.resolved["by_reference"]
    assert result.before == MODEL and result.after["dto"]["class"] == "PackageInfo"
    assert {(c.path, c.kind) for c in result.changes} == {("trail", "added"), ("problems", "added"), ("dto", "added"), ("inputs", "added")}
    assert "_importer" not in result.after  # a helper, not data
    assert (project / "functions/load_model.php").read_text() == before  # never rewritten
    write(project, "functions/shape.php", "<?php\nreturn function (array &$context): array {\n"
          "    $context['seen'] = ($context['seen'] ?? 0) + 1;\n"
          "    return ['ok' => true, 'items' => [1, 2.5, null], 'when' => new DateTimeImmutable('2020-01-01T00:00:00Z')];\n};\n")
    result = call(project, None, "shape", {"seen": 1})
    assert result.returned["ok"] is True and result.returned["items"] == [1, 2.5, None]
    assert result.returned["when"]["__divide"] == "object" and result.returned["when"]["class"] == "DateTimeImmutable"
    assert [(c.path, c.kind, c.before, c.after) for c in result.changes] == [("seen", "changed", 1, 2)]
    text = ft.report(result, role="activity")
    assert "Real PHP code ran" in text and "Not a sandbox" in text
    assert "in a Flow, Runner keeps an activity's result in $context[<the Step's id>]" in text
    assert "  ~ seen: 1 -> 2" in text


def test_a_condition_that_returns_false_is_said_as_a_condition(project):
    result = call(project, "validate", "has_problems", {"problems": []})
    assert (result.status, result.returned, result.return_type) == ("returned", False, "bool")
    assert "As a condition: false, the Step would skip the rest." in ft.report(result, role="condition")
    assert call(project, "validate", "has_problems", {"problems": ["x"]}).returned is True


def test_the_selected_module_resolves_also_through_relative_module_mappings(project):
    for module, word in (("alpha", "a"), ("beta", "b")):
        write(project, f"functions/{module}/same.php", f"<?php\nreturn fn (array &$context): string => '{word}';\n")
    write(project, "functions/same.php", "<?php\nreturn fn (array &$context): string => 'root';\n")
    write(project, "lib/mapped/same.php", "<?php\nreturn fn (array &$context): string => 'mapped';\n")
    assert [call(project, m, "same").returned for m in ("alpha", "beta", None)] == ["a", "b", "root"]
    mapped = call(project, "alpha", "same", mapping={"_modules": {"alpha": "lib/mapped"}})  # relative to the project
    assert mapped.returned == "mapped" and mapped.resolved["file"] == str(project / "lib/mapped/same.php")
    assert mapped.request.modules == {"alpha": project / "lib/mapped"}


def test_a_function_that_imports_another_gets_runners_importer(project):
    write(project, "functions/twice.php", "<?php\nreturn function (array &$context): string {\n"
          "    $load = $context['_importer']('load_model');\n    $load($context);\n"
          "    return $context['_importer']('has_problems', 'validate')($context) ? 'bad' : 'good';\n};\n")
    result = call(project, None, "twice", MODEL)
    assert (result.status, result.returned) == ("returned", "good") and "dto" in result.after


# ------------------------------------------------------------------ failures
def test_an_exception_is_reported_with_its_place(project):
    result = call(project, "validate", "reject", {"problems": ["a field twice"]})
    assert result.status == "exception" and result.exception["class"] == "RuntimeException"
    assert "a field twice" in result.exception["message"]
    path, line = result.location()
    assert path == project / "functions/validate/reject.php" and line > 1
    assert "Exception RuntimeException" in ft.report(result)


def test_what_the_function_prints_never_mixes_with_the_result(project):
    write(project, "functions/noisy.php", "<?php\necho \"loading\\n\";\nreturn function (array &$context): int {\n"
          "    echo '{\"status\": \"returned\", \"return\": 666}';\n    fwrite(STDERR, \"to stderr\\n\");\n"
          "    trigger_error('careful', E_USER_WARNING);\n    print_r([1]);\n    return 7;\n};\n")
    result = call(project, None, "noisy")
    assert (result.status, result.returned) == ("returned", 7)
    assert result.stdout.startswith('loading\n{"status": "returned", "return": 666}Array')
    assert "to stderr" in result.stderr and "careful" in result.stderr
    assert [(m.level, m.line) for m in result.messages] == [("warning", 6)]


def test_fatal_errors_exit_and_a_missing_function_are_told_apart(project):
    write(project, "functions/broken.php", "<?php\nreturn function (array &$context) {\n    return undefined_function_x();\n};\n")
    fatal = call(project, None, "broken")
    assert fatal.status == "exception" and fatal.exception["class"] == "Error"  # PHP 8: an Error, thrown
    write(project, "functions/parse.php", "<?php\nreturn function (array &$context) {\n    return 1 +;\n};\n")
    parse = call(project, None, "parse")
    assert parse.status == "missing" and any("Error requiring file" in log["message"] for log in parse.logs)
    write(project, "functions/quits.php", "<?php\nreturn function (array &$context) {\n    $context['half'] = 1;\n    exit(3);\n};\n")
    quits = call(project, None, "quits")
    assert (quits.status, quits.exit_code, quits.after) == ("exit", 3, {"half": 1})
    write(project, "functions/oom.php", "<?php\nreturn function (array &$context) {\n    $x = str_repeat('x', 900 * 1024 * 1024);\n};\n")
    oom = call(project, None, "oom")
    assert oom.status == "fatal" and "memory" in oom.error["message"].lower()
    missing = call(project, None, "no_such_function_anywhere")
    assert missing.status == "missing" and "found no callable" in missing.message
    with pytest.raises(ft.TestError, match="no file functions/render/nope.php"):
        ft.request_for(project, functions(project), "render", "nope", {})
    with pytest.raises(ft.TestError, match="not a Runner reference"):
        ft.request_for(project, functions(project), "render", "../x", {})


def test_a_malformed_context_or_expectation_is_refused_before_anything_runs(project):
    for text in ("{nope", "[1, 2]", '"text"'):
        with pytest.raises(ft.TestError):
            ft.parse_context(text)
    assert ft.parse_context("  ") == {}
    with pytest.raises(ft.TestError):
        ft.parse_expectation("{x", "")
    with pytest.raises(ft.TestError):
        ft.parse_expectation("", "[1]")


def test_a_time_limit_and_a_cancel_end_php(project):
    write(project, "functions/slow.php", "<?php\nreturn function (array &$context) {\n    sleep(20);\n    return 1;\n};\n")
    started = time.monotonic()
    result = call(project, None, "slow", timeout=1.5)
    assert result.status == "timeout" and time.monotonic() - started < 10
    assert "Stopped after the time limit" in ft.report(result)

    async def cancelled():
        request = ft.request_for(project, functions(project), None, "slow", {})
        task = asyncio.ensure_future(ft.run_test(request))
        await asyncio.sleep(1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    started = time.monotonic()
    asyncio.run(cancelled())
    assert time.monotonic() - started < 10


# ------------------------------------------------------------------ expectations and scenarios
def test_expectations_on_the_return_and_a_subset_of_the_context_after(project):
    result = call(project, None, "load_model", MODEL)
    holds = ft.check(result, ft.parse_expectation('"model/package_info.json"', '{"dto": {"class": "PackageInfo"}, "problems": []}'))
    assert [ok for ok, _t in holds] == [True, True]
    fails = ft.check(result, ft.parse_expectation('"other"', '{"dto": {"class": "Nope"}}'))
    assert [ok for ok, _t in fails] == [False, False]
    assert "  FAIL  returns \"other\"" in ft.report(result, fails)
    assert ft.check(result, ft.parse_expectation("", "")) == []
    assert not ft.contains(1, True) and ft.contains(2, 2.0) and not ft.contains([1, 2], [1])


def test_scenarios_are_saved_in_the_project_only_when_asked_and_keep_each_other(project):
    assert ft.load_scenarios(project, "validate", "has_problems") == {}
    path = ft.save_scenario(project, "validate", "has_problems", "clean", ft.Scenario('{"problems": []}', "false", ""))
    ft.save_scenario(project, "validate", "has_problems", "dirty", ft.Scenario('{"problems": ["x"]}', "true", '{"problems": ["x"]}'))
    assert path == project / ".div/function-tests/validate/has_problems.json"
    data = json.loads(path.read_text())
    assert data["function"] == "validate:has_problems" and sorted(data["scenarios"]) == ["clean", "dirty"]
    loaded = ft.load_scenarios(project, "validate", "has_problems")
    assert loaded["clean"].context == '{"problems": []}' and loaded["dirty"].expected == '{"problems": ["x"]}'
    with pytest.raises(ft.TestError):
        ft.save_scenario(project, "validate", "has_problems", "../bad", ft.Scenario())
    with pytest.raises(ft.TestError):
        ft.save_scenario(project, "validate", "has_problems", "bad context", ft.Scenario("[1]"))
    assert not (project / ".div/runner").exists() or not any((project / ".div/runner").rglob("*.json"))  # no Flow checkpoint touched


def test_a_by_value_callable_is_called_and_its_lost_changes_said(project):
    write(project, "functions/reader.php", "<?php\nreturn function (array $context): int {\n"
          "    $context['lost'] = true;\n    return count($context);\n};\n")
    result = call(project, None, "reader", {"a": 1})
    # it sees a, _importer (as in a Flow) and its own lost key; the context after is as it was
    assert (result.returned, result.after, result.resolved["by_reference"]) == (3, {"a": 1}, False)
    assert "takes the context by value" in ft.report(result)


# ------------------------------------------------------------------ the debugger
@needs_xdebug
def test_the_same_call_under_xdebug_stops_in_the_function_and_writes_its_result(project):
    from divide.run.dbgp import DebugSession, xdebug_ini

    async def debug():
        ini = await xdebug_ini(extension=XDEBUG)
        assert ini is not None
        request = ft.request_for(project, functions(project), "validate", "has_problems", {"problems": []})
        work, result_file, args = ft.debug_request(request)
        session = DebugSession(ft.HARNESS, args, cwd=project, ini=ini + ft.limits())
        try:
            await session.start()
            await session.set_breakpoint(ft.HARNESS, ft.call_line(), temporary=True)  # as Debug Function does
            where = await session.resume("run")
            assert (where.file, where.line) == (ft.HARNESS, ft.call_line())
            where = await session.resume("step_into")  # into the Function, an arrow function here
            assert where is not None and where.file == request.expected
            seen = await session.evaluate("count($context['problems'])")  # the context passed, where it stopped
            assert seen.value == "0"
            assert await session.resume("run") is None  # to the end
            await session.closed.wait()
            script = type("S", (), {"exit_code": session.exit_code, "seconds": 0.0, "output": session.output,
                                    "errors": session.errors, "stopped": False})()
            return ft.read_result(request, result_file, script)
        finally:
            await session.stop()
            shutil.rmtree(work, ignore_errors=True)

    result = asyncio.run(debug())
    assert (result.status, result.returned) == ("returned", False)


def test_render_php_class_from_the_context_load_model_leaves_with_its_real_side_effect(project):
    """The issue's case: module render, activity php_class, its context the one load_model leaves.
    It writes build/src/PackageInfo.php: a Function test runs real code, with its side effects."""
    loaded = call(project, None, "load_model", MODEL)
    result = call(project, "render", "php_class", loaded.after)
    assert (result.status, result.returned) == ("returned", "src/PackageInfo.php"), result.stderr
    assert result.resolved["file"] == str(project / "functions/render/php_class.php")
    assert (project / "build/src/PackageInfo.php").is_file()  # a real file, written by the real Function
    assert "Real PHP code ran: it may have written files" in ft.report(result, role="activity")
