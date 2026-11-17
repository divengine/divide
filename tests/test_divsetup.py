"""Options > Div setup: the window over a setup file, its sections and their dialogs."""

import json
from pathlib import Path

from textual_vision.constants import Command

from divide.app import Divide
from divide.run import setup as div_setup
from divide.ui.dialogs import DialogScreen
from divide.ui.divsetup import (
    SECTIONS, DivSetupWindow, SetupSectionDialog, parse_field, set_value, value_text,
)


async def settle(pilot, n=10):
    for _ in range(n):
        await pilot.pause()


async def until(pilot, check, tries=100):
    for _ in range(tries):
        if check():
            return
        await pilot.pause(0.05)
    raise AssertionError("timed out")


def field(key):
    return next(f for s in SECTIONS for f in s.fields if f.key == key)


def test_fields_and_values():
    assert parse_field(field("paths.include"), " a ; b;") == (["a", "b"], None)
    assert parse_field(field("php.allowed_functions"), "md5, sha1") == (["md5", "sha1"], None)
    assert parse_field(field("parser.max_cycles"), "x")[1] is not None
    assert parse_field(field("data.globals"), "{site: 'Shop'}") == ({"site": "Shop"}, None)
    assert parse_field(field("files.template_ext"), "  ") == (None, None)
    assert value_text(field("paths.include"), ["a", "b"]) == "a; b"
    assert value_text(field("data.globals"), {"a": 1}) == '{"a": 1}'
    data = {"parser": {"max_cycles": 5}}
    set_value(data, "paths.packages", "tpl")
    set_value(data, "parser.max_cycles", None, remove=True)
    assert data == {"paths": {"packages": "tpl"}}


async def test_edit_a_section_and_save(tmp_path):
    (tmp_path / "templates").mkdir()
    page = tmp_path / "page.tpl"
    page.write_text("Hi")
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await app.open_div_setup()
        await settle(pilot)
        win = app.active_window()
        assert isinstance(win, DivSetupWindow) and not win.user
        assert win.source.path == tmp_path.resolve() / ".div" / "setup.json"
        assert "Engine and paths" in win.sections.items[0]
        assert "(Div)" in str(win.effect.render())  # nothing set: Div's defaults
        win.edit_section(0)
        await until(pilot, lambda: isinstance(app.screen, DialogScreen))
        dialog = app.screen.dialog
        assert isinstance(dialog, SetupSectionDialog)
        dialog.inputs["paths.packages"].data = "templates"
        dialog.inputs["paths.include"].data = "missing-folder"
        dialog.end_modal(Command.OK)
        await settle(pilot)
        assert isinstance(app.screen, DialogScreen)  # refused: the folder does not exist
        assert "not a folder" in str(dialog.status.render())
        dialog.inputs["paths.include"].data = ""
        dialog.end_modal(Command.OK)
        await until(pilot, lambda: not isinstance(app.screen, DialogScreen))
        await settle(pilot)
        assert json.loads(win.source.editor.text) == {"paths": {"packages": "templates"}}
        assert win.source.dirty and "1/4" in win.sections.items[0]
        app.raise_window(win)
        await settle(pilot)
        await pilot.press("f2")
        await settle(pilot)
        file = tmp_path / ".div" / "setup.json"
        assert json.loads(file.read_text()) == {"paths": {"packages": "templates"}}
        assert app.div_setup().constants["PACKAGES"] == str((tmp_path / "templates").resolve()) + "/"
        assert "project" in str(win.effect.render())


async def test_the_users_setup_and_restore(tmp_path):
    app = Divide(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await app.open_div_setup(user=True)
        await settle(pilot)
        win = app.active_window()
        assert isinstance(win, DivSetupWindow) and win.user
        assert win.source.path == div_setup.user_file()
        win.write({"parser": {"max_cycles": 7}, "files": {"template_ext": "html"}})
        await settle(pilot)
        win.sections.focus_item(2)  # Parser
        await settle(pilot)
        app.div_setup_action(win, "restore")
        await until(pilot, lambda: isinstance(app.screen, DialogScreen))
        await pilot.press("y")
        await until(pilot, lambda: not isinstance(app.screen, DialogScreen))
        await settle(pilot)
        assert json.loads(win.source.editor.text) == {"files": {"template_ext": "html"}}


async def test_left_out_settings_show_as_you_edit(tmp_path):
    (tmp_path / ".div").mkdir()
    (tmp_path / ".div" / "setup.json").write_text('{"parser": {"max_cycles": 0}}')
    app = Divide(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await app.open_div_setup()
        await settle(pilot)
        win = app.active_window()
        assert isinstance(win, DivSetupWindow)
        assert "max_cycles" in str(win.verdict_box.render())
        assert win.sections.items[2].startswith("!")
        editor = win.source.editor
        assert any("max_cycles" in d.message for d in editor.diagnostics)  # in the editor too
        assert Path(win.source.path).name == "setup.json"
