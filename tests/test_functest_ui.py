"""Test Function and Debug Function from the keyboard, on a copy of examples/generator: T on a Step of
the Flow Designer, Ctrl+F9 in the Functions window, the Step dialog's Function... > Test..., the
report in Output and a failure's place in Messages, and a debug session that stops in the Function
(needs Xdebug: php.ini or DIVIDE_XDEBUG=path/xdebug.so).

Needs php and ``composer install --working-dir examples/generator``; skips without them.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "generator"
VENDOR = EXAMPLE / "vendor"
FLOW = "flows/generate_php_dto.yml"
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


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "generator"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build", "vendor", "composer.lock"))
    try:
        (root / "vendor").symlink_to(VENDOR, target_is_directory=True)
    except OSError:  # Windows without the right to make links
        shutil.copytree(VENDOR, root / "vendor")
    if XDEBUG:
        home = tmp_path / "config"
        (home / "divide").mkdir(parents=True)
        (home / "divide" / "config.json").write_text(json.dumps({"lsp": {"php": "off"}, "xdebug": XDEBUG}))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    return root.resolve()


async def wait(pilot, condition, what: str, tries: int = 300) -> None:
    for _ in range(tries):
        await pilot.pause(0.05)
        if condition():
            return
    pytest.fail(what)


def dialog_of(app, kind):
    dialog = getattr(app.screen, "dialog", None)
    return dialog if isinstance(dialog, kind) else None


async def open_designer(app, pilot):
    from divide.app import CM_FLOW_DESIGN
    from divide.ui.flowboard import FlowDesignWindow
    await pilot.pause(0.3)
    app.run_command(CM_FLOW_DESIGN)
    await wait(pilot, lambda: isinstance(app.active_window(), FlowDesignWindow) and app.active_window().board is not None,
               "no Flow Designer")
    return app.active_window()


def output(app) -> str:
    win = app.output_window()
    return win.view.text if win is not None else ""


async def test_from_a_step_a_condition_runs_and_an_exception_lands_in_messages(project):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox
    from divide.ui.flowmodel import StepDialog
    from divide.ui.functest import FunctionTestDialog

    app = Divide(project, [project / FLOW])
    async with app.run_test(size=(160, 44)) as pilot:
        designer = await open_designer(app, pilot)
        source_text = designer.source.editor.text

        # T on validate.reject: its activity, validate:reject, which throws on a problem
        designer.select(("step", "validate", "reject"))
        await pilot.pause(0.2)
        await pilot.press("t")
        await wait(pilot, lambda: dialog_of(app, FunctionTestDialog), "no Test Function dialog")
        dialog = dialog_of(app, FunctionTestDialog)
        assert dialog.request.qualified == "validate:reject" and dialog.request.expected == project / "functions/validate/reject.php"
        dialog.context_input.data = '{"problems": ["name twice"]}'
        await pilot.press("alt+r")
        await wait(pilot, lambda: "Function test: validate:reject" in output(app), "no report")
        text = output(app)
        assert "Exception RuntimeException" in text and "name twice" in text and "Not a sandbox" in text
        messages = app.messages_window()
        assert messages is not None and any(i.path == project / "functions/validate/reject.php" for i in messages.items)

        # a malformed context is refused in the dialog: nothing runs
        from divide.ui.progress import ProgressScreen
        if isinstance(app.screen, ProgressScreen):  # a failure's box waits for a key
            await pilot.press("escape")
        await wait(pilot, lambda: not isinstance(app.screen, ProgressScreen), "the box stays")
        app.raise_window(designer)
        designer.board_view.focus()
        await pilot.pause(0.1)
        await pilot.press("t")
        await wait(pilot, lambda: dialog_of(app, FunctionTestDialog), "no Test Function dialog")
        dialog = dialog_of(app, FunctionTestDialog)
        assert dialog.context_input.data == '{"problems": ["name twice"]}'  # the last input, remembered
        dialog.context_input.data = "[1, 2"
        await pilot.press("alt+r")
        await pilot.pause(0.3)
        assert dialog_of(app, FunctionTestDialog) is not None
        await pilot.press("escape")
        await wait(pilot, lambda: dialog_of(app, FunctionTestDialog) is None, "dialog still open")

        # Function... > Test... in the Step dialog: the condition validate:has_problems, false
        designer.board_view.focus()
        designer.select(("step", "validate", "reject"))
        await pilot.pause(0.2)
        await pilot.press("enter")
        await wait(pilot, lambda: dialog_of(app, StepDialog), "no Step dialog")
        dialog_of(app, StepDialog).inputs["condition"].focus()
        await pilot.pause(0.1)
        await pilot.press("alt+f")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "no Function question")
        await pilot.press("t")
        await wait(pilot, lambda: dialog_of(app, FunctionTestDialog), "no Test Function dialog")
        dialog = dialog_of(app, FunctionTestDialog)
        assert dialog.request.qualified == "validate:has_problems"
        dialog.context_input.data, dialog.return_input.data = '{"problems": []}', "false"
        await pilot.press("alt+r")
        await wait(pilot, lambda: "Function test: validate:has_problems" in output(app), "no report")
        text = output(app)
        assert "As a condition: false, the Step would skip the rest." in text and "  ok    returns false" in text
        assert designer.source.editor.text == source_text  # the Flow was not changed


async def test_the_functions_window_tests_and_debugs_a_function(project):
    from divide.app import CM_FLOW_FUNCTIONS, Divide
    from divide.ui.flowfunctions import FunctionsWindow
    from divide.ui.functest import FunctionTestDialog

    (project / "functions/render/summary.php").write_text(
        "<?php\n\ndeclare(strict_types=1);\n\nreturn function (array &$context): array {\n"
        "    $names = array_column($context['fields'] ?? [], 'name');\n"
        "    $context['count'] = count($names);\n"
        "    echo 'summarised';\n"
        "    return ['names' => $names];\n};\n")
    app = Divide(project, [project / FLOW])
    async with app.run_test(size=(120, 34)) as pilot:
        await pilot.pause(0.3)
        app.run_command(CM_FLOW_FUNCTIONS)
        await wait(pilot, lambda: isinstance(app.active_window(), FunctionsWindow) and app.active_window().catalog, "no window")
        win = app.active_window()
        node = next(n for n in win.fn_tree._tree_nodes.values()
                    if n.data is not None and (n.data.kind, n.data.module, n.data.name) == ("function", "render", "summary"))
        win.fn_tree.focus()
        win.fn_tree.move_cursor(node)
        await pilot.pause(0.1)
        await pilot.press("ctrl+f9")
        await wait(pilot, lambda: dialog_of(app, FunctionTestDialog), "no Test Function dialog")
        dialog = dialog_of(app, FunctionTestDialog)
        dialog.context_input.data = '{"fields": [{"name": "a"}, {"name": "b"}]}'
        dialog.expected_input.data = '{"count": 2}'
        dialog.scenario_input.data = "two fields"
        await pilot.press("alt+v")  # Save: a scenario of the project
        await wait(pilot, lambda: (project / ".div/function-tests/render/summary.json").is_file(), "not saved")
        await pilot.press("alt+r")
        await wait(pilot, lambda: "Function test: render:summary" in output(app), "no report")
        text = output(app)
        assert '"names": [\n    "a",\n    "b"\n  ]' in text and "  + count = 2" in text and "  ok    the context after has" in text
        assert "── stdout ──\nsummarised" in text

        if not _xdebug():
            return
        # Debug: it stops in the Function, at its first line; Ctrl+F9 goes on to the report
        app.raise_window(win)
        win.fn_tree.focus()
        await pilot.press("ctrl+f9")
        await wait(pilot, lambda: dialog_of(app, FunctionTestDialog), "no Test Function dialog")
        await pilot.press("alt+d")
        summary = project / "functions/render/summary.php"
        await wait(pilot, lambda: app.paused and app.session.location is not None and app.session.location.file == summary,
                   "did not stop in the Function", tries=400)
        assert app.session.location.line == 6
        await pilot.press("f8")  # a step over, in the Function
        await wait(pilot, lambda: app.paused and app.session.location.line == 7, "no step")
        await pilot.press("ctrl+f9")
        await wait(pilot, lambda: app.session is None and "Function test: render:summary" in output(app), "no report after debugging", tries=400)
        assert "  + count = 2" in output(app)
