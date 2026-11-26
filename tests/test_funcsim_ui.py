"""Function Mock Simulation from the keyboard (#23), on a copy of examples/runner with a Function written
for injection (``checkout``): the dialog (its scan of the doubles, its refusals with nothing run, the
pin), the project's opt-in, the playback window (its keys move only a cursor), Save as scenario, a
stale scenario re-pinned only on an explicit choice, the fallback without Xdebug, the entry points
(Shift+T on a Step, Function... > Simulate..., the Functions window) and Test Function kept the real
Run, at 80x24 and 120x34 in the phosphor themes.

A Mock Simulation runs real PHP: the MOCK SIMULATION banner is checked wherever it is shown.

Needs php; the traced tests need Xdebug (php.ini or DIVIDE_XDEBUG=path/xdebug.so).
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from divide.run import funcsim as fs

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "examples" / "runner"
FLOW = "flows/order.yml"
XDEBUG = os.environ.get("DIVIDE_XDEBUG")
pytestmark = pytest.mark.skipif(not shutil.which("php"), reason="needs php")

CHECKOUT = """<?php

declare(strict_types=1);

// A Function written for injection: its dependencies come from the context.
return function (array &$context): string {
    $total = 0.0;
    foreach ($context["items"] ?? [] as $item) {
        $total += $item["price"] * $item["qty"];
    }
    $tax = $context["_importer"]("tax", "billing");
    $total += $tax($context);
    if ($total > 100) {
        $context["_logger"]("INFO", "large order");
        $context["review"] = true;
    }
    $sent = $context["mailer"]->send($context["email"], "Total: " . $total);
    $context["total"] = $total;
    echo "sent: ", $sent ? "yes" : "no", "\\n";
    return $sent ? "notified" : "pending";
};
"""
CONTEXT = {"items": [{"price": 60, "qty": 1}, {"price": 20, "qty": 2}], "email": "buyer@example.com"}
DOUBLES = {"importer": {"billing:tax": {"returns": 21.0}}, "services": {"mailer": {"send": {"returns": True}}}}


def _xdebug() -> bool:
    if XDEBUG and Path(XDEBUG).is_file():
        return True
    return bool(shutil.which("php")) and "xdebug" in subprocess.run(["php", "-m"], capture_output=True, text=True).stdout.lower().split()


needs_xdebug = pytest.mark.skipif(not _xdebug(), reason="needs Xdebug (php.ini or DIVIDE_XDEBUG)")


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "runner"
    shutil.copytree(RUNNER, root, ignore=shutil.ignore_patterns("vendor", "composer.lock", ".div"))
    if (RUNNER / "vendor").is_dir():
        try:
            (root / "vendor").symlink_to(RUNNER / "vendor", target_is_directory=True)
        except OSError:  # Windows without the right to make links
            shutil.copytree(RUNNER / "vendor", root / "vendor")
    (root / ".div").mkdir()
    (root / ".div" / "runner.json").write_text(json.dumps({"root": "functions", "modules": {}}), encoding="utf-8")
    (root / "functions" / "checkout.php").write_text(CHECKOUT, encoding="utf-8")
    home = tmp_path / "config"
    (home / "divide").mkdir(parents=True)
    settings = {"lsp": {"php": "off"}}
    if XDEBUG:
        settings["xdebug"] = XDEBUG
    (home / "divide" / "config.json").write_text(json.dumps(settings), encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    return root.resolve()


async def wait(pilot, condition, what: str, tries: int = 400) -> None:
    for _ in range(tries):
        await pilot.pause(0.05)
        if condition():
            return
    pytest.fail(what)


def settings(project: Path) -> dict:
    return json.loads((project.parent / "config" / "divide" / "config.json").read_text(encoding="utf-8"))


def dialog_of(app, kind):
    dialog = getattr(app.screen, "dialog", None)
    return dialog if isinstance(dialog, kind) else None


async def open_dialog(app, pilot, project: Path):
    """Run > Mock Simulation of a Function, with checkout.php the active editor."""
    from divide.app import CM_FUNCTION_SIMULATE
    from divide.ui.funcsim import FunctionSimulationDialog
    await pilot.pause(0.3)
    app.run_command(CM_FUNCTION_SIMULATE)
    await wait(pilot, lambda: dialog_of(app, FunctionSimulationDialog), "no Mock Simulation dialog")
    return dialog_of(app, FunctionSimulationDialog)


def choose(dialog, name: str) -> None:
    """A saved scenario picked in the Scenario line (as its history list sets it)."""
    dialog.scenario_input.data = name
    dialog.on_input_line_changed(None)


def playback(app):
    from divide.ui.funcsim import FunctionPlaybackWindow
    win = app.active_window()
    return win if isinstance(win, FunctionPlaybackWindow) else None


async def finish_progress(app, pilot) -> None:
    from divide.ui.progress import ProgressScreen
    await wait(pilot, lambda: not isinstance(app.screen, ProgressScreen) or not app.screen.dialog.running, "the run did not end")
    if isinstance(app.screen, ProgressScreen):
        await pilot.press("escape")


async def test_the_scan_prefills_the_doubles_and_an_incomplete_scenario_runs_nothing(project):
    from divide.app import Divide
    from divide.ui.funcsim import FunctionSimulationDialog

    marker = project / "ran.txt"  # the file's top-level code writes it: it shows whether PHP ran
    text = CHECKOUT.replace("declare(strict_types=1);\n", "declare(strict_types=1);\n\nfile_put_contents(__DIR__ . '/../ran.txt', 'x');\n")
    (project / "functions" / "checkout.php").write_text(text, encoding="utf-8")
    fs.trust(project)
    app = Divide(project, [project / "functions" / "checkout.php"])
    async with app.run_test(size=(120, 34)) as pilot:
        dialog = await open_dialog(app, pilot, project)
        doubles = json.loads(dialog.doubles_input.data)
        assert doubles == {"importer": {"billing:tax": {"returns": None}}, "services": {"mailer": {"send": {"returns": None}}}}
        assert "MOCK SIMULATION: real PHP runs" in str(dialog.query_one(".fs-banner").render())
        assert "pinned to the file's version" in str(dialog.about.render())
        assert "answering null" in str(dialog.status.render())

        # a double the Function calls taken out: refused, nothing runs
        dialog.doubles_input.data = json.dumps({"importer": {"billing:tax": {"returns": 1}}})
        await pilot.press("alt+m")
        await pilot.pause(0.5)
        assert dialog_of(app, FunctionSimulationDialog) is dialog
        assert "No double for mailer->send" in str(dialog.status.render())
        # a wrong outcome (two of returns / throws), and a context that is not JSON: refused too
        dialog.doubles_input.data = json.dumps({"importer": {"billing:tax": {"returns": 1, "throws": "x"}},
                                                "services": {"mailer": {"send": {"returns": True}}}})
        await pilot.press("alt+m")
        await pilot.pause(0.3)
        assert dialog_of(app, FunctionSimulationDialog) is dialog and "exactly one of" in str(dialog.status.render())
        dialog.doubles_input.data = json.dumps(DOUBLES)
        dialog.context_input.data = "{1"
        await pilot.press("alt+m")
        await pilot.pause(0.3)
        assert dialog_of(app, FunctionSimulationDialog) is dialog and "not JSON" in str(dialog.status.render())
        dialog.context_input.data = json.dumps(CONTEXT)
        dialog.lines_input.data = "0"
        await pilot.press("alt+m")
        await pilot.pause(0.3)
        assert dialog_of(app, FunctionSimulationDialog) is dialog and "limits.lines" in str(dialog.status.render())
        await pilot.press("escape")
        await pilot.pause(0.3)
    assert not marker.exists()  # nothing ran
    assert not (project / ".div" / "function-simulation").exists()


async def test_the_first_simulation_asks_for_the_opt_in_and_without_xdebug_offers_the_result_only(project, monkeypatch):
    from divide.app import Divide
    from divide.run import dbgp
    from divide.ui.dialogs import MessageBox

    async def no_xdebug(*args, **kwargs):
        return None

    monkeypatch.setattr(dbgp, "xdebug_ini", no_xdebug)
    app = Divide(project, [project / "functions" / "checkout.php"])
    async with app.run_test(size=(120, 34)) as pilot:
        dialog = await open_dialog(app, pilot, project)
        dialog.context_input.data = json.dumps(CONTEXT)
        dialog.doubles_input.data = json.dumps(DOUBLES)
        await pilot.press("alt+m")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "no opt-in question")
        box = dialog_of(app, MessageBox)
        assert "not a sandbox and not side-effect-free" in box._text
        await pilot.press("escape")  # not allowed: nothing runs, nothing recorded, not even in the settings
        await pilot.pause(0.4)
        assert not fs.trusted(project) and playback(app) is None
        assert "function_simulations" not in settings(project)

        dialog = await open_dialog(app, pilot, project)
        assert json.loads(dialog.context_input.data) == {}  # the context is never kept in the user's settings
        dialog.context_input.data = json.dumps(CONTEXT)
        dialog.doubles_input.data = json.dumps(DOUBLES)
        await pilot.press("alt+m")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "no opt-in question")
        await pilot.press("a")
        await wait(pilot, lambda: dialog_of(app, MessageBox) and "Xdebug" in dialog_of(app, MessageBox)._text, "no Xdebug question")
        assert "PHP runs for real all the same" in dialog_of(app, MessageBox)._text
        await pilot.press("w")
        await finish_progress(app, pilot)
        await wait(pilot, lambda: playback(app) is not None, "no playback window")
        win = playback(app)
        assert fs.trusted(project)
        assert not win.traced and len(win.playback) == 0
        assert "Run without the line trace" in str(win.info.render())
        assert "Returned" in str(win.verdict.render()) and "notified" in str(win.verdict.render())
        assert "MOCK SIMULATION" in str(win.bar.render()) and "Not a sandbox" in str(win.bar.render())
    assert not (project / ".div" / "function-simulation").exists()  # an untraced run is not kept
    # after the opt-in, the user's settings keep the preferences only: no context, no doubles
    kept = settings(project)["function_simulations"]
    assert list(kept.values()) == [{"name": "", "trace": True, "tripwire": False}]
    text = (project.parent / "config" / "divide" / "config.json").read_text(encoding="utf-8")
    assert "buyer@example.com" not in text and "mailer" not in text and "billing:tax" not in text


def test_older_settings_with_a_scenario_are_cut_down_to_the_preferences(project):
    from divide import config
    from divide.ui.funcsim import last_input, remember_input

    data = config.load()
    data["function_simulations"] = {"other|:x": {"name": "a", "trace": True, "tripwire": False,
                                                 "scenario": {"context": {"secret": "s3cr3t"}}}}
    config.save(data)
    assert last_input(project, None, "checkout") == {}
    remember_input(project, None, "checkout", {"name": "large", "trace": True, "tripwire": True,
                                              "scenario": {"context": CONTEXT, "doubles": DOUBLES}})
    kept = settings(project)["function_simulations"]
    assert kept == {"other|:x": {"name": "a", "trace": True, "tripwire": False},
                    f"{project}|:checkout": {"name": "large", "trace": True, "tripwire": True}}
    assert last_input(project, None, "checkout") == {"name": "large", "trace": True, "tripwire": True}


async def test_scanned_null_doubles_need_a_confirmation_and_null_stays_a_valid_answer(project):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox
    from divide.ui.funcsim import FunctionSimulationDialog

    fs.trust(project)
    app = Divide(project, [project / "functions" / "checkout.php"])
    async with app.run_test(size=(120, 34)) as pilot:
        dialog = await open_dialog(app, pilot, project)
        dialog.context_input.data = json.dumps(CONTEXT)
        dialog.options.value &= ~1  # no line trace: this test needs no Xdebug
        dialog.post_message(type(dialog.options).Changed(dialog.options.value))
        await pilot.pause(0.2)
        assert dialog.placeholders(json.loads(dialog.doubles_input.data)) == ["billing:tax", "mailer->send"]

        # Save asks too; Back saves nothing
        dialog.scenario_input.data = "nulls"
        await pilot.press("alt+v")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "Save did not ask about the null doubles")
        assert "billing:tax, mailer->send" in dialog_of(app, MessageBox)._text
        await pilot.press("escape")
        await pilot.pause(0.3)
        assert not (project / ".div" / "function-simulations").exists()

        # Simulate asks; Back runs nothing and the dialog stays
        await pilot.press("alt+m")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "Simulate did not ask about the null doubles")
        box = dialog_of(app, MessageBox)
        assert "answer null" in box._text and "billing:tax, mailer->send" in box._text
        await pilot.press("b")
        await wait(pilot, lambda: dialog_of(app, FunctionSimulationDialog) is dialog, "Back did not return to the dialog")
        assert "Not run" in str(dialog.status.render()) and playback(app) is None

        # a value given to one: only the other is asked about
        doubles = json.loads(dialog.doubles_input.data)
        doubles["importer"]["billing:tax"] = {"returns": 0}
        dialog.doubles_input.data = json.dumps(doubles)
        await pilot.press("alt+m")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "no question for the one left null")
        box = dialog_of(app, MessageBox)
        assert "mailer->send" in box._text and "billing:tax" not in box._text
        await pilot.press("k")  # Keep null and simulate: null is the answer meant
        await finish_progress(app, pilot)
        await wait(pilot, lambda: playback(app) is not None, "no playback window")
        verdict = str(playback(app).verdict.render())
        assert "pending" in verdict  # the mailer's double answered null, as confirmed
    # a null the user saved in a scenario is intended: no question
    scenario = fs.new_scenario(None, "checkout", project / "functions" / "checkout.php", context=CONTEXT)
    scenario["doubles"] = {"importer": {"billing:tax": {"returns": None}}, "services": {"mailer": {"send": {"returns": None}}}}
    fs.save_scenario(project, "intended", scenario)
    app = Divide(project, [project / "functions" / "checkout.php"])
    async with app.run_test(size=(120, 34)) as pilot:
        dialog = await open_dialog(app, pilot, project)
        choose(dialog, "intended")
        await pilot.pause(0.2)
        assert dialog.placeholders(json.loads(dialog.doubles_input.data)) == []
        assert "answering null" not in str(dialog.status.render())


@needs_xdebug
async def test_a_traced_run_plays_back_line_by_line_and_moving_runs_nothing(project):
    from divide.app import Divide
    from divide.ui.funcsim import SaveScenarioDialog

    fs.trust(project)
    file = project / "functions" / "checkout.php"
    app = Divide(project, [file])
    async with app.run_test(size=(120, 34)) as pilot:
        dialog = await open_dialog(app, pilot, project)
        dialog.context_input.data = json.dumps(CONTEXT)
        dialog.doubles_input.data = json.dumps(DOUBLES)
        await pilot.press("alt+m")
        await finish_progress(app, pilot)
        await wait(pilot, lambda: playback(app) is not None, "no playback window")
        win = playback(app)
        await pilot.pause(0.3)
        assert win.trace.status == "returned" and win.trace.pinned and win.folder is not None
        lines = [e["line"] for e in win.playback.events]
        assert lines[0] == 7 and 20 in lines
        bar = str(win.bar.render())
        assert "MOCK SIMULATION" in bar and "pinned" in bar and "NOT pinned" not in bar
        assert win.playback.cursor == 0 and win.code.execution_row == 6

        before = file.read_bytes()
        runs = sorted(p.name for p in (project / ".div" / "function-simulation").iterdir())
        await pilot.press("f7")
        await pilot.press("f7")
        assert win.playback.cursor == 2 and win.code.execution_row == lines[2] - 1
        await pilot.press("shift+f7")
        assert win.playback.cursor == 1
        await pilot.press("ctrl+end")
        assert win.playback.cursor == len(lines) - 1
        assert win.view.context.get("total") is None or win.view.context.get("total") == 121.0
        await pilot.press("ctrl+home")
        assert win.playback.cursor == 0
        await pilot.press("f8")
        assert win.playback.cursor == 1
        assert "Double calls (2)" in str(win.info.render())
        assert 'mailer->send("buyer@example.com", "Total: 121") #1: returns' in str(win.info.render())  # a call, args inside
        assert file.read_bytes() == before  # moving runs nothing, writes nothing
        assert sorted(p.name for p in (project / ".div" / "function-simulation").iterdir()) == runs
        assert not app.debugging

        # X: the context in Output, labelled
        await pilot.press("ctrl+end")
        await pilot.press("x")
        await pilot.pause(0.3)
        out = app.output_window()
        assert out is not None and "MOCK SIMULATION" in out.view.text and "buyer@example.com" in out.view.text
        app.raise_window(win)
        win.code.focus()
        await pilot.pause(0.2)

        # S: Save as scenario, expecting what this run did
        await pilot.press("s")
        await wait(pilot, lambda: dialog_of(app, SaveScenarioDialog), "no Save as scenario")
        save = dialog_of(app, SaveScenarioDialog)
        save.name_input.data = "large order"
        save.options.value = 1
        await pilot.press("alt+k")
        await pilot.pause(0.5)
        saved = json.loads((project / ".div/function-simulations/_root/checkout.large order.json").read_text(encoding="utf-8"))
        assert saved["expect"] == {"returns": "notified", "context": {"review": True, "total": 121.0}}
        assert saved["function"]["sha256"] == fs.sha256(file)
    assert not (project / ".div" / "runner").exists() and not (project / ".div" / "simulation").exists()  # Flow checkpoints untouched


@needs_xdebug
async def test_an_unpinned_scenario_is_never_shown_as_pinned(project):
    from divide.app import Divide

    fs.trust(project)
    app = Divide(project, [project / "functions" / "checkout.php"])
    async with app.run_test(size=(120, 34)) as pilot:
        dialog = await open_dialog(app, pilot, project)
        dialog.context_input.data = json.dumps(CONTEXT)
        dialog.doubles_input.data = json.dumps(DOUBLES)
        dialog.options.value &= ~(1 << 1)  # the pin taken out: a visible choice
        dialog.post_message(type(dialog.options).Changed(dialog.options.value))
        await pilot.pause(0.3)
        assert dialog.pin_sha is None and "NOT pinned to a source version" in str(dialog.about.render())
        await pilot.press("alt+m")
        await finish_progress(app, pilot)
        await wait(pilot, lambda: playback(app) is not None, "no playback window")
        win = playback(app)
        await pilot.pause(0.3)
        assert not win.trace.pinned
        assert "NOT pinned to a source version" in str(win.bar.render())
        trace = json.loads((win.folder / "trace.json").read_text(encoding="utf-8"))
        assert trace["function"]["pinned"] is False


async def test_a_stale_scenario_is_re_pinned_only_when_asked(project):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox

    fs.trust(project)
    file = project / "functions" / "checkout.php"
    scenario = fs.new_scenario(None, "checkout", file, context=CONTEXT)
    scenario["doubles"] = DOUBLES
    fs.save_scenario(project, "large", scenario)
    old = scenario["function"]["sha256"]
    file.write_text(CHECKOUT.replace("Total: ", "Sum: "), encoding="utf-8")  # changed since it was pinned
    app = Divide(project, [file])
    async with app.run_test(size=(120, 34)) as pilot:
        dialog = await open_dialog(app, pilot, project)
        choose(dialog, "large")
        await pilot.pause(0.3)
        assert dialog.pin_sha == old and "STALE" in str(dialog.about.render())
        assert dialog.query_one("#repin").display and not dialog.query_one("#replay").display
        dialog.options.value &= ~1  # no line trace: the stale check comes first either way
        dialog.post_message(type(dialog.options).Changed(dialog.options.value))
        await pilot.pause(0.2)
        await pilot.press("alt+m")
        await finish_progress(app, pilot)
        await wait(pilot, lambda: dialog_of(app, MessageBox), "no stale question")
        assert "changed since the scenario was pinned" in dialog_of(app, MessageBox)._text
        await pilot.press("escape")  # not re-pinned: nothing ran, the saved scenario as it was
        await pilot.pause(0.4)
        assert playback(app) is None
        assert fs.load_scenario(project / ".div/function-simulations/_root/checkout.large.json")["function"]["sha256"] == old

        dialog = await open_dialog(app, pilot, project)
        choose(dialog, "large")
        await pilot.pause(0.3)
        await pilot.press("alt+r")  # Re-pin, in the dialog
        await pilot.pause(0.3)
        assert dialog.pin_sha == fs.sha256(file) and "STALE" not in str(dialog.about.render())
        assert not dialog.query_one("#repin").display and dialog.query_one("#replay").display
        await pilot.press("alt+m")
        await finish_progress(app, pilot)
        await wait(pilot, lambda: playback(app) is not None, "no playback window")
        assert playback(app).trace.status == "returned"
        # the saved scenario changes only on Save
        assert fs.load_scenario(project / ".div/function-simulations/_root/checkout.large.json")["function"]["sha256"] == old


@pytest.mark.skipif(not (RUNNER / "vendor" / "divengine" / "runner" / "src" / "runner.php").is_file(),
                    reason="needs composer install --working-dir examples/runner")
async def test_shift_t_simulates_and_t_stays_the_real_test(project):
    from divide.app import CM_FLOW_DESIGN
    from divide.ui.dialogs import MessageBox
    from divide.ui.flowboard import FlowDesignWindow
    from divide.ui.flowfunctions import FunctionsWindow
    from divide.ui.flowmodel import StepDialog
    from divide.ui.functest import WARNING, FunctionTestDialog
    from divide.ui.funcsim import FunctionSimulationDialog

    from divide.app import Divide

    app = Divide(project, [project / FLOW])
    async with app.run_test(size=(160, 44)) as pilot:
        await pilot.pause(0.3)
        app.run_command(CM_FLOW_DESIGN)
        await wait(pilot, lambda: isinstance(app.active_window(), FlowDesignWindow) and app.active_window().board is not None,
                   "no Flow Designer")
        designer = app.active_window()
        designer.select(("step", "main", "total"))
        await pilot.pause(0.2)
        await pilot.press("T")
        await wait(pilot, lambda: dialog_of(app, FunctionSimulationDialog), "Shift+T opened no Mock Simulation")
        dialog = dialog_of(app, FunctionSimulationDialog)
        assert dialog.func_name == "compute_total" and dialog.file == project / "functions" / "compute_total.php"
        await pilot.press("escape")
        await pilot.pause(0.3)

        designer.board_view.focus()
        await pilot.press("t")  # T: Test Function, the real Run / Debug, with its own warning
        await wait(pilot, lambda: dialog_of(app, FunctionTestDialog), "T opened no Test Function")
        assert "Runs the real PHP code" in WARNING
        await pilot.press("escape")
        await pilot.pause(0.3)

        # the Step dialog: Function... > Simulate...
        designer.board_view.focus()
        await pilot.press("enter")
        await wait(pilot, lambda: dialog_of(app, StepDialog), "no Step dialog")
        step = dialog_of(app, StepDialog)
        step.inputs["activity"].focus()
        await pilot.pause(0.1)
        step.run_worker(step._function(), exclusive=True)
        await wait(pilot, lambda: dialog_of(app, MessageBox), "no Function... box")
        await pilot.press("m")
        await wait(pilot, lambda: dialog_of(app, FunctionSimulationDialog), "Function... > Simulate... opened nothing")
        assert dialog_of(app, FunctionSimulationDialog).func_name == "compute_total"
        await pilot.press("escape")
        await pilot.pause(0.3)
        assert designer.source.editor.text == (project / FLOW).read_text(encoding="utf-8")  # the Flow not changed

        # the Functions window: Ctrl+F9 stays Test Function; Alt+F10 > Simulate...
        app.open_flow_functions(designer.source)
        await wait(pilot, lambda: isinstance(app.active_window(), FunctionsWindow) and app.active_window().catalog is not None,
                   "no Functions window")
        functions = app.active_window()
        functions.select(("function", None, "checkout"))
        await pilot.pause(0.3)
        await pilot.press("ctrl+f9")
        await wait(pilot, lambda: dialog_of(app, FunctionTestDialog), "Ctrl+F9 opened no Test Function")
        await pilot.press("escape")
        await pilot.pause(0.3)
        functions.fn_tree.focus()
        await pilot.press("alt+f10")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "no local menu")
        await pilot.press("m")
        await wait(pilot, lambda: dialog_of(app, FunctionSimulationDialog), "Simulate... opened nothing")
        assert dialog_of(app, FunctionSimulationDialog).func_name == "checkout"
        await pilot.press("escape")


@pytest.mark.parametrize("size", [(80, 24), (120, 34)])
@pytest.mark.parametrize("palette", ["phosphor-green", "phosphor-amber-black", "turbo-pascal"])
async def test_the_dialog_and_the_banner_fit(project, size, palette):
    from divide import themes
    from divide.app import Divide
    from divide.ui.funcsim import FunctionPlaybackWindow
    from divide.run import functrace as ftr

    fs.trust(project)
    app = Divide(project, [project / "functions" / "checkout.php"], palette=palette)
    async with app.run_test(size=size) as pilot:
        dialog = await open_dialog(app, pilot, project)
        await pilot.pause(0.3)
        width, height = size
        for selector in (".fs-banner", "#simulate", "#cancel", "CheckBoxes", ".fs-status"):
            region = dialog.query_one(selector).region
            assert region.width > 0 and region.right <= width and region.bottom <= height, (selector, region)
        await pilot.press("escape")
        await pilot.pause(0.2)

        # a playback (from a trace document: nothing runs here)
        file = project / "functions" / "checkout.php"
        scenario = fs.new_scenario(None, "checkout", file, context=CONTEXT)
        trace = ftr.parse_trace({"protocol": ftr.PROTOCOL, "version": 1, "scenario": {},
                                 "function": {"module": None, "name": "checkout", "file": "functions/checkout.php",
                                              "sha256": fs.sha256(file), "pinned": True},
                                 "result": {"status": "returned", "return": "notified", "return_type": "string",
                                            "before": CONTEXT, "after": {**CONTEXT, "total": 121.0}, "calls": [], "logs": [],
                                            "stdout": "sent: yes\n"},
                                 "events": [{"seq": 1, "type": "line", "line": 7, "depth": 0,
                                             "locals": {"set": {"context.email": "buyer@example.com"}}},
                                            {"seq": 2, "type": "line", "line": 8, "depth": 0, "locals": {"set": {"total": 0.0}}}],
                                 "truncated": False})
        win = app.open_function_playback(project, trace, scenario)
        await pilot.pause(0.4)
        assert isinstance(app.active_window(), FunctionPlaybackWindow)
        assert win.bar.region.width > 0 and win.bar.region.bottom <= height and win.code.region.width > 0
        assert "MOCK SIMULATION" in str(win.bar.render())
        assert app.context_topic() == "Function-Mock-Simulation"  # F1: its help page
        await wait(pilot, lambda: win.has_class("narrow") == (win.size.width < 100), "the panel's layout does not follow the width")
        assert themes.current().name == palette


def test_a_double_call_reads_as_a_call_never_as_what_it_returned():
    from divide.ui.funcsim import _call_args
    assert _call_args([None, "Total: 0"]) == 'null, "Total: 0"'
    assert _call_args([]) == ""
    assert _call_args(["x" * 100]).endswith("~")  # cut, and says so
