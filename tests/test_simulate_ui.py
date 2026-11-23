"""Flow Simulation & Playback from the keyboard, on a copy of examples/runner: S on the Flow Designer's
board, the Simulate Flow dialog (incomplete doubles refused, Make doubles), the Simulation window
(the playback keys, the marks, the context, Resume in a new process), unsaved YAML simulated as a
snapshot and never written, Ctrl+F9 still the real Run, Runner 0.2 refused with a clear message, and
the window at 80, 120 and 160 columns in the phosphor themes.

Needs php and Runner >= 0.3 in examples/runner (``composer install --working-dir examples/runner``).
"""

import json
import shutil
from pathlib import Path

import pytest

from divide.run import simulate as sim
from divide.run.flow import find_runner

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "runner"
VENDOR = EXAMPLE / "vendor"
FLOW = "flows/fulfil.yml"
DOUBLES = {
    "description": "A small order: no review, the stock short once, the invoice paused",
    "doubles": {
        "compute_total": {"returns": 25, "context": {"total": 25}},
        "needs_approval": {"returns": False},
        "mark_reviewed": {"returns": True},
        "reserve_stock": {"returns": "reserved"},
        "stock_short": {"sequence": [{"returns": True}, {"returns": False}]},
        "billing:total": {"returns": 20},
        "shipping:total": {"returns": 5},
        "invoice_sum": {"pause": True, "context": {"sum": 25}},
        "format_receipt": {"returns": "receipt"},
    },
    "budget": {"steps": 200, "transfers": 50, "seconds": 5},
}
pytestmark = pytest.mark.skipif(
    not shutil.which("php") or sim.simulation_problem(find_runner(EXAMPLE)) is not None,
    reason="needs php and Runner >= 0.3 in examples/runner (composer install)")


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "runner"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("vendor", "composer.lock", ".div"))
    try:
        (root / "vendor").symlink_to(VENDOR, target_is_directory=True)
    except OSError:  # Windows without the right to make links
        shutil.copytree(VENDOR, root / "vendor")
    home = tmp_path / "config"
    (home / "divide").mkdir(parents=True)
    (home / "divide" / "config.json").write_text(json.dumps({"lsp": {"php": "off"}}))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    return root.resolve()


def write_doubles(project: Path, data=None) -> Path:
    path = project / ".div" / "simulations" / "flows" / "fulfil.yml.doubles.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data or DOUBLES, indent=2), encoding="utf-8")
    return path


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
    await wait(pilot, lambda: type(app.active_window()) is FlowDesignWindow and app.active_window().board is not None,
               "no Flow Designer")
    designer = app.active_window()
    designer.board_view.focus()
    await pilot.pause(0.1)
    return designer


async def close_progress(app, pilot):
    from divide.ui.progress import ProgressScreen
    await wait(pilot, lambda: not isinstance(app.screen, ProgressScreen) or not app.screen.dialog.running, "still running")
    if isinstance(app.screen, ProgressScreen):
        await pilot.press("escape")
    await wait(pilot, lambda: not isinstance(app.screen, ProgressScreen), "the box stays")


def painted(win) -> str:
    """The board as drawn, the playback's marks included."""
    return "\n".join("".join(ch for ch, _s in row) for row in win.board.paint(win.key, win.chosen(), win.overlay))


async def test_simulate_replay_and_resume_without_touching_the_yaml(project):
    from divide.app import Divide
    from divide.ui.simulate import SimulationDialog, SimulationWindow
    from divide.ui.windows import OutputWindow

    write_doubles(project)
    on_disk = (project / FLOW).read_text(encoding="utf-8")
    app = Divide(project, [project / FLOW])
    async with app.run_test(size=(160, 44)) as pilot:
        designer = await open_designer(app, pilot)
        editor = designer.source.editor
        # an unsaved change: simulated as it is, never saved
        editor.insert("# an unsaved note\n", (0, 0))
        await pilot.pause(0.2)
        unsaved = editor.text
        assert designer.source.dirty
        designer.board_view.focus()
        await pilot.press("s")
        await wait(pilot, lambda: dialog_of(app, SimulationDialog), "no Simulate Flow dialog")
        dialog = dialog_of(app, SimulationDialog)
        assert dialog.dirty and "Every function has a double" in str(dialog.status.render())
        dialog.context_input.data = '{"items": [{"price": 10, "qty": 2}]}'
        await pilot.press("alt+s")
        await wait(pilot, lambda: isinstance(app.active_window(), SimulationWindow), "no Simulation window", tries=400)
        await close_progress(app, pilot)
        win = app.active_window()
        session = win.session
        assert session.snapshot.read_text(encoding="utf-8") == unsaved
        assert (project / FLOW).read_text(encoding="utf-8") == on_disk and designer.source.dirty and editor.text == unsaved
        assert session.paused and "Paused at invoice.sum" in str(win.verdict.render())
        assert win.playback.cursor == len(win.playback) - 1
        board = painted(win)
        assert "=3 sum" in board and "»4 invoice" in board and "-2 review" in board  # paused, in a call, skipped

        # the playback keys move the cursor, nothing else
        await pilot.press("ctrl+home")
        await pilot.pause(0.1)
        assert win.playback.cursor == 0 and "event 1/" in str(win.bar.render())
        await pilot.press("f8")
        await pilot.pause(0.1)
        assert win.playback.event.type == "step.start" and win.key == ("step", "main", "total")
        assert "►1 total" in painted(win)
        await pilot.press("f7")
        await pilot.pause(0.1)
        assert win.playback.event.type == "activity.start"
        await pilot.press("shift+f7")
        await pilot.pause(0.1)
        assert win.playback.event.type == "step.start"
        win.select(("step", "stock", "short"))
        await pilot.press("f4")  # the selected Step's next event
        await pilot.pause(0.1)
        assert win.playback.event.key() == ("step", "stock", "short")
        await pilot.press("f7")
        await pilot.press("f7")
        await pilot.pause(0.1)
        assert win.playback.event.type == "condition" and "true: the Step goes on" in str(win.inspector.render())
        while win.playback.event.type != "jump":
            await pilot.press("f7")
            await pilot.pause(0.02)
        text = str(win.inspector.render())
        assert "JUMP" in text and "does not return" in text and win.view.context["retried"] is True
        await pilot.press("shift+f7")  # the Step's context mapping, merged just before
        await pilot.pause(0.1)
        assert win.playback.event.type == "context.update" and "+ retried = true" in str(win.inspector.render())
        win.playback.go(next(i for i, e in enumerate(win.playback.events) if e.type == "call"))
        win.refresh_view()
        assert "returns here when the Block ends" in str(win.inspector.render())
        await pilot.press("x")
        await wait(pilot, lambda: isinstance(app.active_window(), OutputWindow), "no context in Output")
        assert "Context at event" in app.active_window().view.text and '"total": 25' in app.active_window().view.text
        app.raise_window(win)
        win.board_view.focus()
        await pilot.press("ctrl+f2")
        await pilot.pause(0.1)
        assert win.playback.cursor == 0
        assert editor.text == unsaved and (project / FLOW).read_text(encoding="utf-8") == on_disk

        # Resume: a new process, the next segment added to the same playback
        await pilot.press("ctrl+f9")
        await wait(pilot, lambda: len(session.segments) == 2, "not resumed", tries=400)
        await close_progress(app, pilot)
        await wait(pilot, lambda: win.playback.segments == 2, "the playback did not grow")
        assert session.segments[-1].state == "done" and "segment 2/2" in str(win.bar.render())
        assert "√5 receipt" in painted(win) and "√3 sum" in painted(win)
        resumed = next(e for e in win.playback.events if e.segment == 2 and e.type == "call.return")
        assert resumed.data["resumed"] is True
        assert not list((project / ".div" / "runner").glob("**/*.json")) if (project / ".div" / "runner").exists() else True
        assert editor.text == unsaved and (project / FLOW).read_text(encoding="utf-8") == on_disk

        # Replay last: the recorded traces again, no PHP
        app.raise_window(designer)
        designer.board_view.focus()
        await pilot.press("s")
        await wait(pilot, lambda: dialog_of(app, SimulationDialog), "no Simulate Flow dialog")
        assert dialog_of(app, SimulationDialog).last == session.folder
        before = len(sim.sessions(project))
        await pilot.press("alt+r")
        await wait(pilot, lambda: isinstance(app.active_window(), SimulationWindow) and app.active_window() is not win, "no replay")
        assert app.active_window().playback.segments == 2 and len(sim.sessions(project)) == before


async def test_incomplete_doubles_are_refused_and_edit_doubles_adds_the_missing(project):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox
    from divide.ui.simulate import SimulationDialog

    partial = {"doubles": {"compute_total": {"returns": 1}}}
    path = write_doubles(project, partial)
    (project / ".div" / "simulations" / "broken.json").write_text('{"doubles": {"compute_total": {"returns": 1, "throws": "x"}}}')
    app = Divide(project, [project / FLOW])
    async with app.run_test(size=(120, 34)) as pilot:
        await open_designer(app, pilot)
        await pilot.press("s")
        await wait(pilot, lambda: dialog_of(app, SimulationDialog), "no Simulate Flow dialog")
        dialog = dialog_of(app, SimulationDialog)
        assert "No double yet for: needs_approval" in str(dialog.status.render())
        await pilot.press("alt+s")
        await pilot.pause(0.3)
        assert dialog_of(app, SimulationDialog) is dialog  # refused, still open
        assert not (project / ".div" / "simulation").exists()  # nothing ran
        dialog.doubles_input.data = ".div/simulations/broken.json"
        dialog.show_status()
        await pilot.press("alt+s")
        await pilot.pause(0.3)
        assert dialog_of(app, SimulationDialog) is dialog and not (project / ".div" / "simulation").exists()
        dialog.doubles_input.data = ".div/simulations/flows/fulfil.yml.doubles.json"
        await pilot.press("alt+e")  # Edit doubles: the missing ones added (asked), the file opened
        await wait(pilot, lambda: dialog_of(app, MessageBox), "no question")
        await pilot.press("y")
        await wait(pilot, lambda: getattr(app.active_editor(), "path", None) == path, "the doubles file is not open")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["doubles"]["compute_total"] == {"returns": 1}  # what was there stays
        assert data["doubles"]["needs_approval"] == {"returns": True} and data["doubles"]["format_receipt"] == {"returns": None}
        assert sim.check_spec(data, sim.requirements(sim.fm.parse((project / FLOW).read_text())), project).ok
        assert not (project / ".div" / "simulation").exists()


async def test_runner_0_2_refuses_simulation_and_ctrl_f9_is_still_the_real_run(project, tmp_path):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox
    from divide.ui.flow import FlowDialog

    (project / "vendor").unlink() if (project / "vendor").is_symlink() else shutil.rmtree(project / "vendor")
    old = project / "vendor"
    (old / "divengine" / "runner" / "bin").mkdir(parents=True)
    (old / "divengine" / "runner" / "bin" / "run.php").write_text("<?php // Runner 0.2: --save-context\n")
    (old / "composer").mkdir()
    (old / "composer" / "installed.json").write_text(json.dumps({"packages": [{"name": "divengine/runner", "version": "v0.2.0"}]}))
    write_doubles(project)
    app = Divide(project, [project / FLOW])
    async with app.run_test(size=(120, 34)) as pilot:
        await open_designer(app, pilot)
        await pilot.press("s")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "no message")
        text = dialog_of(app, MessageBox)._text
        await pilot.press("enter")
        assert not (project / ".div" / "simulation").exists()
        assert "Runner v0.2.0 is installed" in text and "0.3.0" in text and "Run (Ctrl+F9) still runs" in text
        await pilot.press("ctrl+f9")  # the real Run, unchanged, and said to be real
        await wait(pilot, lambda: dialog_of(app, FlowDialog), "no Run Flow dialog")
        dialog = dialog_of(app, FlowDialog)
        assert any("REAL RUN" in str(w.render()) for w in dialog.query("Static"))
        await pilot.press("escape")


@pytest.mark.parametrize("size,palette", [((80, 24), "phosphor-white"), ((120, 34), "phosphor-green"),
                                          ((160, 44), "phosphor-amber")])
async def test_the_simulation_window_at_80_120_160_columns_in_the_phosphor_themes(project, size, palette):
    import asyncio
    from divide.app import Divide
    from divide.ui.simulate import SimulationWindow

    flow = project / FLOW
    session = sim.new_session(project, flow, flow.read_text(encoding="utf-8"), DOUBLES, None, {"items": []})
    segment = await sim.run_segment(find_runner(project), session)
    assert segment.state == "paused"
    app = Divide(project, [flow], palette=palette)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.4)
        win = app.open_simulation(app.active_editor(), session)
        await wait(pilot, lambda: win.board is not None and win.is_mounted, "no board")
        await pilot.pause(0.3)
        assert win.has_class("narrow") == (size[0] < 100)
        assert "SIMULATION" in str(win.bar.render()) and "Paused" in str(win.verdict.render())
        win.board_view.focus()
        for key in ("ctrl+home", "f8", "f8", "f7", "shift+f8", "ctrl+end"):
            await pilot.press(key)
            await pilot.pause(0.05)
        assert win.playback.cursor == len(win.playback) - 1
        board = painted(win)
        for mark in ("=", "»", "√", "-"):
            assert mark in board
        styles = {s for row in win.board.paint(win.key, None, win.overlay) for _c, s in row}
        assert "mark" in styles and "taken" in styles  # marks and taken lines are drawn, not only coloured
        await asyncio.sleep(0)
