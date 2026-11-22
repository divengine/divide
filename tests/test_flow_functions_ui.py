"""The Functions window and the Step dialog's Function... button, driven from the keyboard on a copy of
examples/generator, then the Flow checked and run by the real Runner (php and ``composer install
--working-dir examples/generator``; without them the tests skip)."""

import shutil
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "generator"
FLOW = "flows/generate_php_dto.yml"
VENDOR = EXAMPLE / "vendor"
pytestmark = pytest.mark.skipif(
    not (shutil.which("php") and (VENDOR / "divengine" / "runner" / "bin" / "run.php").is_file()
         and (VENDOR / "divengine" / "div" / "src" / "div.php").is_file()),
    reason="needs php and composer install --working-dir examples/generator")


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "generator"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build", "vendor", ".div", "composer.lock"))
    try:
        (root / "vendor").symlink_to(VENDOR, target_is_directory=True)
    except OSError:  # Windows without the right to make links
        shutil.copytree(VENDOR, root / "vendor")
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


async def test_module_and_function_made_attached_edited_checked_and_run_from_the_designer(project):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox
    from divide.ui.flow import FlowDialog, save_flow_settings
    from divide.ui.flowfunctions import FunctionDialog, FunctionsWindow, ModuleDialog
    from divide.ui.flowmodel import StepDialog
    from divide.ui.windows import EditorWindow

    flow = project / FLOW
    save_flow_settings(flow, {"context": "generate.json", "root": "functions", "save": ""})
    app = Divide(project, [flow])
    async with app.run_test(size=(160, 44)) as pilot:
        designer = await open_designer(app, pilot)
        code = designer.source

        # 1. the Functions window from the board: the root, its Modules, the Steps that use each Function
        await pilot.press("f")
        await wait(pilot, lambda: isinstance(app.active_window(), FunctionsWindow) and app.active_window().catalog, "no Functions window")
        win = app.active_window()
        rows = win.rows()
        assert rows[0].startswith("Function root functions/  (--root of the Run Flow dialog)")
        assert any(r.startswith("validate/  4") for r in rows) and any(r.startswith("outputs_current  condition · 1 Step(s)") for r in rows)
        assert not any("Not found" in r for r in rows)

        # 2. a Module (Shift+Ins), 3. a Function in it (Ins on the Module): made, and open in the PHP editor
        await pilot.press("shift+insert")
        await wait(pilot, lambda: dialog_of(app, ModuleDialog), "no Module dialog")
        dialog_of(app, ModuleDialog).name_input.data = "publish"
        await pilot.press("alt+k")
        await wait(pilot, lambda: (project / "functions/publish").is_dir() and win.selected() and win.selected().kind == "module",
                   "no Module made")
        await pilot.press("insert")
        await wait(pilot, lambda: dialog_of(app, FunctionDialog), "no Function dialog")
        dialog = dialog_of(app, FunctionDialog)
        assert dialog.module_input.data == "publish"
        await pilot.press(*"stamp")  # typed: where it goes is said as it is typed
        await pilot.pause(0.1)
        assert "Written to functions/publish/stamp.php" in str(dialog.where.render())
        await pilot.press("alt+k")
        made = project / "functions/publish/stamp.php"
        await wait(pilot, lambda: isinstance(app.active_window(), EditorWindow) and app.active_window().path == made, "not opened")
        editor = app.active_window()
        assert editor.editor.lang == "php" and editor.editor.cursor_location[0] == made.read_text().split("\n").index(
            "return function (array &$context): mixed {")  # at the callable

        # 4. its PHP written and saved in the editor
        editor.editor.text = editor.editor.text.replace("    return null;", "    $context['stamped'] = 'yes';\n    return 'stamped';")
        await pilot.press("f2")
        await wait(pilot, lambda: "stamped" in made.read_text(), "not saved")

        # 5. attached to a new Step from the board (its module and activity offered), one edit of the YAML
        app.raise_window(designer)
        designer.select(("step", "main", "report"))
        await pilot.pause(0.2)
        await pilot.press("insert")
        await wait(pilot, lambda: dialog_of(app, StepDialog), "no Step dialog")
        step = dialog_of(app, StepDialog)
        assert "publish" in step.offers["module"]()
        step.id_input.data, step.inputs["module"].data, step.inputs["activity"].data = "stamp", "publish", "stamp"
        await pilot.press("alt+k")
        await wait(pilot, lambda: "      stamp:\n        module: publish\n        activity: stamp\n" in code.editor.text, "no Step written")

        # 6. a condition made from the Step dialog's Function... button: the file only on the Step's OK
        await pilot.press("insert")
        await wait(pilot, lambda: dialog_of(app, StepDialog), "no Step dialog")
        step = dialog_of(app, StepDialog)
        step.id_input.data, step.inputs["module"].data = "gate", "publish"
        await pilot.press("alt+f")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "no Function question")
        await pilot.press("n")
        await wait(pilot, lambda: dialog_of(app, FunctionDialog), "no Function dialog")
        fn = dialog_of(app, FunctionDialog)
        assert fn.module_input.data == "publish"
        fn.name_input.data, fn.role.value = "ready", 2  # the second button: Condition
        await pilot.press("alt+k")
        await wait(pilot, lambda: dialog_of(app, StepDialog) and dialog_of(app, StepDialog).pending is not None, "nothing pending")
        step = dialog_of(app, StepDialog)
        assert step.inputs["condition"].data == "ready" and not (project / "functions/publish/ready.php").exists()
        step.inputs["activity"].data = "stamp"
        await pilot.press("alt+k")
        ready = project / "functions/publish/ready.php"
        await wait(pilot, lambda: ready.is_file() and isinstance(app.active_window(), EditorWindow) and app.active_window().path == ready,
                   "condition not made and opened")
        assert "      gate:\n        module: publish\n        condition: ready\n        activity: stamp\n" in code.editor.text

        # the same, cancelled: no file, no YAML change
        app.raise_window(designer)
        before = code.editor.text
        await pilot.press("insert")
        await wait(pilot, lambda: dialog_of(app, StepDialog), "no Step dialog")
        dialog_of(app, StepDialog).id_input.data = "never"
        await pilot.press("alt+f")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "no Function question")
        await pilot.press("n")
        await wait(pilot, lambda: dialog_of(app, FunctionDialog), "no Function dialog")
        dialog_of(app, FunctionDialog).name_input.data = "never_made"
        await pilot.press("alt+k")
        await wait(pilot, lambda: dialog_of(app, StepDialog) and dialog_of(app, StepDialog).pending is not None, "nothing pending")
        await pilot.press("escape")
        await wait(pilot, lambda: dialog_of(app, StepDialog) is None, "Step dialog still open")
        assert code.editor.text == before and not (project / "functions/never_made.php").exists()

        # the YAML edits are the code's own: unsaved, undoable
        assert code.dirty

        # 7. checked: Runner compiles it, every reference resolves, the callables are fine
        app.raise_window(designer)
        app.check_flow(code.editor)
        await wait(pilot, lambda: "the Flow compiles" in str(designer.verdict.render()), "not checked")
        assert code.editor.diagnostics == []
        win.reload()
        cat = win.catalog
        assert [(r.step_name, r.key) for r in cat.entry("publish", "stamp").references] == [("main.stamp", "activity"), ("main.gate", "activity")]
        assert [(r.step_name, r.key) for r in cat.entry("publish", "ready").references] == [("main.gate", "condition")]

        # 8. run by Runner (Ctrl+F9 saves the Flow first): the new Steps ran and changed the context
        await pilot.press("ctrl+f9")
        await wait(pilot, lambda: dialog_of(app, MessageBox) or dialog_of(app, FlowDialog), "no Run Flow dialog")
        if dialog_of(app, MessageBox):  # save it first
            await pilot.press("alt+y")
        await wait(pilot, lambda: dialog_of(app, FlowDialog), "no Run Flow dialog")
        await pilot.press("enter")
        await wait(pilot, lambda: app.output_window() is not None and "State: done" in app.output_window().view.text, "not run")
        out = app.output_window().view.text
        assert '"stamp": "stamped"' in out and '"gate": "stamped"' in out and '"stamped": "yes"' in out


async def test_a_missing_function_is_made_from_the_window_and_the_settings_file_gives_the_root(project):
    from divide.app import CM_FLOW_FUNCTIONS, Divide
    from divide.ui.dialogs import MessageBox
    from divide.ui.flowfunctions import FunctionDialog, FunctionsWindow

    flow = project / FLOW
    flow.write_text(flow.read_text().replace("activity: write_report", "activity: write_summary"))
    app = Divide(project, [flow])
    async with app.run_test(size=(80, 25)) as pilot:
        await pilot.pause(0.3)
        app.run_command(CM_FLOW_FUNCTIONS)  # no Run Flow settings: the project is the root
        await wait(pilot, lambda: isinstance(app.active_window(), FunctionsWindow) and app.active_window().catalog, "no window")
        win = app.active_window()
        assert win.has_class("narrow")
        assert win.rows()[0].startswith("Function root ./  (the project: Runner's default)")
        assert len(win.catalog.missing) == 12  # every reference: the Functions are in functions/

        # Alt+F10 > Settings: .div/runner.json made (after asking) and opened
        await pilot.press("alt+f10")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "no menu")
        await pilot.press("alt+s")
        await wait(pilot, lambda: dialog_of(app, MessageBox) and "Make .div/runner.json" in dialog_of(app, MessageBox)._text, "no question")
        await pilot.press("alt+y")
        settings = project / ".div/runner.json"
        await wait(pilot, lambda: settings.is_file(), "no settings file")
        settings.write_text('{"root": "functions", "modules": {}}\n')
        app.raise_window(win)
        win.reload()
        await pilot.pause(0.2)
        assert win.rows()[0].startswith("Function root functions/  (.div/runner.json)")
        assert [r.qualified for r in win.catalog.missing] == ["write_summary"]

        # Enter on the missing one: the Function dialog with its name and use, then the file
        node = next(n for n in win.fn_tree._tree_nodes.values() if n.data is not None and n.data.kind == "gone" and n.data.ref)
        win.fn_tree.focus()
        win.fn_tree.move_cursor(node)
        await pilot.pause(0.1)
        assert "Missing write_summary" in str(win.info.render()) and "looked at  functions/write_summary.php" in str(win.info.render())
        await pilot.press("enter")
        await wait(pilot, lambda: dialog_of(app, FunctionDialog), "no Function dialog")
        fn = dialog_of(app, FunctionDialog)
        assert (fn.module_input.data, fn.name_input.data, fn.role_name()) == ("", "write_summary", "activity")
        await pilot.press("alt+k")
        await wait(pilot, lambda: (project / "functions/write_summary.php").is_file(), "not made")
        await wait(pilot, lambda: win.catalog is not None and not win.catalog.missing, "still missing")


async def test_a_run_gets_the_root_and_modules_of_the_settings_file(project):
    """No function root in the Run Flow dialog: .div/runner.json gives it (as --root), and a Module
    it maps elsewhere reaches Runner in the context's _modules."""
    import json

    from divide.app import Divide
    from divide.run import flowmodel as fm
    from divide.ui.flow import FlowDialog, save_flow_settings

    (project / ".div").mkdir()
    (project / ".div/runner.json").write_text(json.dumps({"root": "functions", "modules": {"extra": "lib/extra"}}))
    (project / "lib/extra").mkdir(parents=True)
    (project / "lib/extra/note.php").write_text("<?php\nreturn fn (array &$context): string => 'noted';\n")
    flow = project / FLOW
    doc = fm.parse(flow.read_text())
    flow.write_text(fm.apply(doc.text, fm.add_step(doc, doc.block("main"), doc.step("main", "report"), "note",
                                                   {"module": "extra", "activity": "note"})))
    save_flow_settings(flow, {"context": "generate.json", "root": "", "save": ""})
    app = Divide(project, [flow])
    async with app.run_test(size=(120, 34)) as pilot:
        await pilot.pause(0.3)
        assert app.flow_functions(app.active_window()).folder("extra") == project / "lib/extra"
        await pilot.press("ctrl+f9")
        await wait(pilot, lambda: dialog_of(app, FlowDialog), "no Run Flow dialog")
        dialog = dialog_of(app, FlowDialog)
        assert dialog.default_root == "functions" and dialog.root_input.data == ""  # the label says it is the file's
        await pilot.press("enter")
        await wait(pilot, lambda: app.output_window() is not None and "State:" in app.output_window().view.text, "not run")
        out = app.output_window().view.text
        assert "State: done" in out and '"note": "noted"' in out, out[:2000]
    assert json.loads((project / "generate.json").read_text()) == {"model": "model/package_info.json", "output": "build"}
