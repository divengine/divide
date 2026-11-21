"""Runner Flows from divide, through the real Runner installed by Composer (examples/runner).

Each test copies examples/runner (its vendor/ with divengine/runner, installed by
``composer install --working-dir examples/runner``) into a folder of its own and
runs Flows with Runner's own bootstrap, as divide does: nothing of the SFM
runtime is imitated here. Without php or that installation, the tests skip.
"""

import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from divide.run import children
from divide.run.flow import (Runner, check_context_file, check_context_text, find_runner, is_flow, read_saved, run_flow,
                             version_tuple)
from divide.run.script import ScriptError

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "runner"
BOOTSTRAP = EXAMPLE / "vendor" / "divengine" / "runner" / "bin" / "run.php"
needs_runner = pytest.mark.skipif(not (shutil.which("php") and BOOTSTRAP.is_file()),
                                  reason="needs php and composer install --working-dir examples/runner")


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "runner"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("*.context.json", "*.state.json", ".div"))
    return root


def runner_of(root: Path) -> Runner:
    runner = find_runner(root)
    assert runner.usable, runner.problem
    return runner


def write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def function(root: Path, name: str, body: str) -> None:
    write(root, f"functions/{name}.php", f"<?php\n\ndeclare(strict_types=1);\n\n{body}\n")


def php_children(pid: int) -> list[str]:
    found = []
    for entry in Path("/proc").iterdir():
        try:
            if entry.name.isdigit() and int((entry / "stat").read_text().rsplit(")", 1)[1].split()[1]) == pid:
                found.append((entry / "cmdline").read_bytes().split(b"\0")[0].decode())
        except (OSError, IndexError, ValueError):
            continue
    return [c for c in found if Path(c).name.startswith("php")]


# ------------------------------------------------------------------ recognising and finding
def test_a_flow_is_a_yaml_file_with_blocks():
    assert is_flow(Path("flows/a.yml"), "id: a\nblocks:\n  main:\n    steps: {}\n")
    assert is_flow(Path("a.yaml"), "# comment\nblocks:   # the Blocks\n")
    assert not is_flow(Path("a.yml"), "services:\n  blocks:\n")  # not at the root
    assert not is_flow(Path("a.json"), "blocks:\n")
    assert not is_flow(None, "blocks:\n")
    assert version_tuple("v0.2.0") == (0, 2, 0) and version_tuple("0.10.3") == (0, 10, 3)
    assert version_tuple("0.3.x-dev") == (0, 3, 0) and version_tuple("dev-main") is None


def test_runner_missing_or_too_old(tmp_path):
    missing = find_runner(tmp_path)
    assert not missing.usable and "composer require divengine/runner" in missing.problem
    old = tmp_path / "old"
    write(old, "vendor/divengine/runner/bin/run.php", "<?php\n")
    write(old, "vendor/composer/installed.json", json.dumps({"packages": [{"name": "divengine/runner", "version": "v0.1.4"}]}))
    found = find_runner(old)
    assert not found.usable and "0.1.4" in found.problem and "0.2.0" in found.problem
    custom = tmp_path / "custom"  # composer.json's config.vendor-dir
    write(custom, "composer.json", '{"config": {"vendor-dir": "lib/vendor"}}')
    write(custom, "lib/vendor/divengine/runner/bin/run.php", "<?php\n")
    write(custom, "lib/vendor/composer/installed.json", json.dumps({"packages": [{"name": "divengine/runner", "version": "v0.2.3"}]}))
    found = find_runner(custom)
    assert found.usable and found.version == "v0.2.3" and found.bootstrap == custom / "lib/vendor/divengine/runner/bin/run.php"


@needs_runner
def test_the_example_project_has_runner_installed():
    runner = find_runner(EXAMPLE)
    assert runner.usable and version_tuple(runner.version) >= (0, 2, 0)


def test_contexts_are_checked(tmp_path):
    assert check_context_text('{"a": 1}') is None
    assert "JSON object" in check_context_text("[1, 2]")
    assert "not JSON" in check_context_text("{a: 1}")
    assert "no such file" in check_context_file(tmp_path / "none.json")
    assert "not JSON" in check_context_file(write(tmp_path, "bad.json", "{"))
    assert check_context_file(write(tmp_path, "ok.json", "{}")) is None
    assert read_saved(tmp_path / "none.json").exists is False
    assert read_saved(write(tmp_path, "list.json", "[1]")).problem
    broken = read_saved(write(tmp_path, "p.json", '{"_runner_state": "paused"}'))
    assert not broken.resumable and "_flow_state" in broken.problem


# ------------------------------------------------------------------ running
@needs_runner
async def test_a_basic_flow_runs(project):
    run = await run_flow(runner_of(project), project / "flows/hello.yml", cwd=project,
                         context_text='{"name": "Rafa"}', functions=project / "functions")
    assert (run.state, run.exit_code) == ("done", 0)
    assert run.context["greet"] == "Hello Rafa" and run.context["greeted"] is True
    assert run.saved_to is None and run.logs and "Processed successfully" in run.result
    assert run.stdout.lstrip().startswith("{")  # --json: the context on stdout, alone


@needs_runner
async def test_pause_and_resume_across_processes_through_nested_calls(project):
    runner, flow, state = runner_of(project), project / "flows/order.yml", project / "order.state.json"
    first = await run_flow(runner, flow, cwd=project, context=project / "order.json", functions=project / "functions",
                           save_to=state)
    assert (first.state, first.exit_code, first.saved_to) == ("paused", 3, state)
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["_flow_state"] == {"block": "approval", "step_index": 1}  # main -> review -> approval.ask
    assert saved["_flow_stack"] == [{"block": "main", "step_index": 2}, {"block": "review", "step_index": 2}]
    assert saved["trail"] == ["total", "check"]
    info = read_saved(state)
    assert info.resumable and (info.block, info.step, info.calls) == ("approval", "ask", 2)
    second = await run_flow(runner, flow, cwd=project, context=state, save_to=state, resumed=True)  # a new PHP process
    assert (second.state, second.exit_code) == ("done", 0)
    assert second.context["trail"] == ["total", "check", "record", "receipt"]  # nothing ran twice
    assert second.context["receipt"] == "Total: 25.00 (approved)" and second.context["review_done"] is True
    assert second.context["_flow_stack"] == [] and not second.context["_flow_state"]
    assert read_saved(state).state == "done" and not read_saved(state).resumable


@needs_runner
async def test_module_qualified_functions(project):
    run = await run_flow(runner_of(project), project / "flows/invoice.yml", cwd=project, context=project / "order.json",
                         functions=project / "functions")
    assert run.state == "done"
    assert (run.context["lines"], run.context["shipping"], run.context["sum"]) == (25.0, 5.0, 30.0)  # billing:total, shipping:total


@needs_runner
async def test_relative_paths_are_the_projects(project):
    """Runner resolves relative paths from where it runs: the project, as divide runs it."""
    write(project, "ctx.json", '{"_root_folder": "functions", "name": "Ana"}')
    run = await run_flow(runner_of(project), project / "flows/hello.yml", cwd=project, context=project / "ctx.json")
    assert run.state == "done" and run.context["greet"] == "Hello Ana"


@needs_runner
async def test_invalid_yaml_context_and_execution_errors(project):
    runner = runner_of(project)
    write(project, "flows/broken.yml", "blocks:\n  main:\n    steps:\n      - activity: greet\n")  # a list: rejected
    broken = await run_flow(runner, project / "flows/broken.yml", cwd=project, functions=project / "functions")
    assert broken.state == "error" and broken.diagnostics
    bad = await run_flow(runner, project / "flows/hello.yml", cwd=project, context_text="[1]")
    assert bad.state == "invocation" and bad.exit_code == 2 and "JSON object" in bad.diagnostics[0] and bad.context is None
    missing = await run_flow(runner, project / "flows/hello.yml", cwd=project, context=project / "none.json")
    assert missing.state == "invocation" and "not found" in missing.diagnostics[0]
    function(project, "explode", 'return function (array &$context): void { throw new RuntimeException("no stock"); };')
    write(project, "flows/fail.yml", "blocks:\n  main:\n    steps:\n      a:\n        activity: explode\n")
    failed = await run_flow(runner, project / "flows/fail.yml", cwd=project, functions=project / "functions",
                            save_to=project / "fail.json")
    assert (failed.state, failed.exit_code) == ("error", 1)
    assert "no stock" in json.dumps(failed.context) and "no stock" in " ".join(failed.diagnostics)
    assert failed.saved_to == project / "fail.json" and read_saved(project / "fail.json").state == "error"


@needs_runner
async def test_a_context_that_cannot_be_saved_or_a_dying_php(project):
    runner = runner_of(project)
    state = write(project, "keep.json", '{"before": true}')
    function(project, "closure", 'return function (array &$context): void { $context["cb"] = fn () => 1; };')
    write(project, "flows/closure.yml", "blocks:\n  main:\n    steps:\n      a:\n        activity: closure\n")
    run = await run_flow(runner, project / "flows/closure.yml", cwd=project, functions=project / "functions", save_to=state)
    assert run.state == "unsaved" and run.saved_to is None and "Closure" in run.diagnostics[0]
    assert json.loads(state.read_text()) == {"before": True}  # the saved context is as it was
    function(project, "quit", 'return function (array &$context): void { exit(5); };')
    write(project, "flows/quit.yml", "blocks:\n  main:\n    steps:\n      a:\n        activity: quit\n")
    run = await run_flow(runner, project / "flows/quit.yml", cwd=project, functions=project / "functions", save_to=state)
    assert (run.state, run.exit_code) == ("crashed", 5) and json.loads(state.read_text()) == {"before": True}


def test_without_php(project, monkeypatch, tmp_path):
    empty = tmp_path / "bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    with pytest.raises(ScriptError, match="php not found"):
        asyncio.run(run_flow(Runner(project / "vendor/divengine/runner/bin/run.php", "v0.2.0"),
                             project / "flows/hello.yml", cwd=project))


def slow_project(project: Path) -> Path:
    """A Flow that pauses, then sleeps when resumed (long enough to be stopped)."""
    function(project, "nap", 'return function (array &$context): string { sleep(20); return "woke"; };')
    write(project, "flows/slow.yml", "blocks:\n  main:\n    steps:\n      first:\n        context:\n"
                                     "          started: true\n        pause: true\n      nap:\n        activity: nap\n")
    return project / "flows/slow.yml"


@needs_runner
async def test_a_stopped_run_keeps_the_checkpoint_and_leaves_no_php(project):
    runner, flow, state = runner_of(project), slow_project(project), project / "slow.json"
    paused = await run_flow(runner, flow, cwd=project, functions=project / "functions", save_to=state)
    assert paused.state == "paused"
    checkpoint = state.read_bytes()
    task = asyncio.ensure_future(run_flow(runner, flow, cwd=project, context=state, save_to=state, resumed=True))
    linux = sys.platform.startswith("linux")
    for _ in range(100):
        await asyncio.sleep(0.05)
        if not linux or php_children(os.getpid()):
            break
    await asyncio.sleep(0.5)
    started = time.monotonic()
    task.cancel()
    run = await task
    assert run.state == "cancelled" and run.saved_to is None and time.monotonic() - started < 5
    assert state.read_bytes() == checkpoint  # the paused checkpoint is untouched: it can still be resumed
    assert read_saved(state).resumable
    assert not list(project.glob(".slow.json.*"))
    if linux:
        assert php_children(os.getpid()) == []
    assert children.running() == []


# ------------------------------------------------------------------ the IDE
async def wait(pilot, condition, what: str, tries: int = 200) -> None:
    for _ in range(tries):
        await pilot.pause(0.05)
        if condition():
            return
    pytest.fail(what)


def test_checkpoints_are_one_per_flow_under_div_runner(tmp_path):
    from divide.run.flow import default_checkpoint, is_managed, prepare_checkpoint

    project = tmp_path / "p"
    yml, yaml = default_checkpoint(project / "flows/order.yml", project), default_checkpoint(project / "flows/order.yaml", project)
    assert yml == project / ".div/runner/flows/order.yml.context.json" and yml != yaml
    assert default_checkpoint(project / "order.yml", project) != yml
    a, b = default_checkpoint(tmp_path / "a/x.yml", project), default_checkpoint(tmp_path / "b/x.yml", project)
    assert a != b and is_managed(a, project) and is_managed(yml, project)
    assert not is_managed(project / "flows/order.context.json", project)
    prepare_checkpoint(yml, project)
    assert yml.parent.is_dir() and (project / ".div/runner/.gitignore").read_text(encoding="utf-8").endswith("*\n")
    other = project / "mine/state.json"
    prepare_checkpoint(other, project)
    assert not other.parent.exists()  # the user's own folders are theirs


def dialog_of(app, kind):
    return getattr(app.screen, "dialog", None) if isinstance(getattr(app.screen, "dialog", None), kind) else None


@needs_runner
async def test_run_pause_resume_in_the_ide(project):
    from divide import config
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox
    from divide.ui.flow import FlowDialog

    flow = project / "flows/order.yml"
    app = Divide(project, [flow])
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("ctrl+f9")  # on a Flow: the Run Flow dialog
        await wait(pilot, lambda: dialog_of(app, FlowDialog), "no Run Flow dialog")
        dialog = dialog_of(app, FlowDialog)
        assert dialog.save_input.data == ".div/runner/flows/order.yml.context.json" and dialog.resume_button.disabled
        dialog.context_input.data = "order.json"
        dialog.root_input.data = "functions"
        await pilot.press("enter")  # Run
        output = lambda: app.output_window().view.text if app.output_window() else ""  # noqa: E731
        await wait(pilot, lambda: "State: paused at approval.ask" in output(), "the run did not pause")
        assert "Context saved to .div/runner/flows/order.yml.context.json" in output() and '"trail"' in output()
        saved = project / ".div/runner/flows/order.yml.context.json"
        assert read_saved(saved).resumable
        assert (project / ".div/runner/.gitignore").read_text(encoding="utf-8").splitlines()[-1] == "*"  # out of Git
        assert config.load()["flows"][str(flow)] == {"context": "order.json", "root": "functions", "save": ".div/runner/flows/order.yml.context.json"}
        await pilot.press("escape")
        app.raise_window(app.window_for(flow))
        await pilot.pause(0.2)

        await pilot.press("ctrl+f9")  # Run again while a paused run is saved: asked, never silent
        await wait(pilot, lambda: dialog_of(app, FlowDialog), "no Run Flow dialog")
        dialog = dialog_of(app, FlowDialog)
        assert not dialog.resume_button.disabled and dialog.resume_button.is_default and "Paused at approval.ask" in str(dialog.saved_line.render())
        await pilot.press("alt+r")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "starting over was not asked")
        checkpoint = saved.read_bytes()
        await pilot.press("n")
        await pilot.pause(0.3)
        assert saved.read_bytes() == checkpoint

        app.raise_window(app.window_for(flow))
        await pilot.press("ctrl+f9")
        await wait(pilot, lambda: dialog_of(app, FlowDialog), "no Run Flow dialog")
        await pilot.press("enter")  # Resume, the default now
        await wait(pilot, lambda: "State: resumed, done" in output(), "the run did not resume")
        report = output()
        assert '"total",\n    "check",\n    "record",\n    "receipt"' in report and "Total: 25.00 (approved)" in report
        await pilot.press("escape")
        app.raise_window(app.window_for(flow))
        await pilot.pause(0.2)

        await pilot.press("ctrl+f9")  # a finished run in divide's checkpoint: Run replaces it, unasked
        await wait(pilot, lambda: dialog_of(app, FlowDialog), "no Run Flow dialog")
        assert "Run replaces it" in str(dialog_of(app, FlowDialog).saved_line.render())
        await pilot.press("alt+r")
        await wait(pilot, lambda: "State: paused at approval.ask" in output() or dialog_of(app, MessageBox), "the run did not start")
        assert dialog_of(app, MessageBox) is None and read_saved(saved).resumable
        await pilot.press("escape")


@needs_runner
async def test_resume_needs_a_paused_context(project):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox
    from divide.ui.flow import FlowDialog

    flow = project / "flows/order.yml"
    app = Divide(project, [flow])
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("ctrl+f9")
        await wait(pilot, lambda: dialog_of(app, FlowDialog), "no Run Flow dialog")
        dialog = dialog_of(app, FlowDialog)
        assert dialog.resume_button.disabled and "Nothing saved yet" in str(dialog.saved_line.render())
        assert not dialog._check("resume")  # a missing context is not a reason to start over
        assert not (project / ".div").exists()  # nothing made before a run
        write(project, "flows/order.context.json", '{"_runner_state": "done", "_flow_state": []}')
        dialog.save_input.data = "flows/order.context.json"  # a file the user chose, finished
        dialog.show_saved()
        assert dialog.resume_button.disabled and "asks before replacing a file of yours" in str(dialog.saved_line.render())
        await pilot.press("alt+r")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "replacing a file of the user's was not asked")
        await pilot.press("n")
        await pilot.pause(0.3)
    assert (project / "flows/order.context.json").read_text(encoding="utf-8") == '{"_runner_state": "done", "_flow_state": []}'
    assert not (project / ".div").exists()


@needs_runner
async def test_esc_stops_a_run_in_the_ide(project):
    from divide.app import Divide
    from divide.ui.flow import FlowDialog
    from divide.ui.progress import ProgressScreen

    flow = slow_project(project)
    state = project / ".div/runner/flows/slow.yml.context.json"
    state.parent.mkdir(parents=True)
    assert (await run_flow(runner_of(project), flow, cwd=project, functions=project / "functions", save_to=state)).state == "paused"
    checkpoint = state.read_bytes()
    app = Divide(project, [flow])
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("ctrl+f9")
        await wait(pilot, lambda: dialog_of(app, FlowDialog), "no Run Flow dialog")
        await pilot.press("enter")  # Resume: it sleeps
        await wait(pilot, lambda: isinstance(app.screen, ProgressScreen), "no progress box")
        await pilot.pause(1.0)
        await pilot.press("escape")  # stop PHP
        await wait(pilot, lambda: app.output_window() is not None and "State: stopped" in app.output_window().view.text,
                   "the run was not stopped")
        assert "slow.yml.context.json is as it was" in app.output_window().view.text
    assert state.read_bytes() == checkpoint and children.running() == []


async def test_without_runner_the_ide_says_how_to_install_it(tmp_path):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox

    if not shutil.which("php"):
        pytest.skip("needs php")
    flow = write(tmp_path, "flows/a.yml", "blocks:\n  main:\n    steps:\n      a:\n        context:\n          x: 1\n")
    app = Divide(tmp_path, [flow])
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("ctrl+f9")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "nothing said")
        assert "composer require divengine/runner" in dialog_of(app, MessageBox)._text


async def test_ctrl_f9_on_other_yaml_is_not_a_flow(tmp_path):
    from divide.app import Divide

    other = write(tmp_path, "config.yml", "services:\n  web: {}\n")
    app = Divide(tmp_path, [other])
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause(0.3)
        assert not app.wants_flow()
        script = write(tmp_path, "a.php", "<?php echo 1;")
        app.open_file(script)
        await pilot.pause(0.3)
        assert app.wants_run() and not app.wants_flow()  # Ctrl+F9 on PHP runs the script, as before
