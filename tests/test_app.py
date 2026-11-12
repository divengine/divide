import shutil
from pathlib import Path

from textual_vision.input_line import InputLine

from divide.app import Divide
from divide.ui.dialogs import DialogScreen, FileDialog
from divide.ui.windows import EditorWindow, ProjectWindow

ROOT = Path(__file__).resolve().parents[1]


async def settle(pilot, n: int = 3) -> None:
    for _ in range(n):
        await pilot.pause()


async def test_open_edit_save(tmp_path):
    tpl = tmp_path / "showcase.tpl"
    shutil.copy(ROOT / "examples" / "showcase.tpl", tpl)
    app = Divide(tmp_path, [tpl])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        win = app.query_one(EditorWindow)
        ed = win.editor
        assert app.focused is ed
        assert ed.div_enabled
        names = {h[2] for line in ed._highlights.values() for h in line}
        assert {"div.loop", "div.var", "div.tplvar", "div.comment"} <= names
        ed.move_cursor((0, 0))
        await pilot.press("X")
        assert win.dirty
        await settle(pilot)
        assert win.frame.indicator == "* 1:2"
        await pilot.press("f2")
        await settle(pilot)
        assert tpl.read_text().startswith("X<!--{")
        assert not win.dirty
        await pilot.press("Y", "ctrl+s")
        await settle(pilot)
        assert tpl.read_text().startswith("XY<!--{")


async def test_dialect_detected(tmp_path):
    (tmp_path / "angle.dialect").write_text("{'DIV_TAG_REPLACEMENT_PREFIX': '<<', 'DIV_TAG_REPLACEMENT_SUFFIX': '>>'}")
    tpl = tmp_path / "a.tpl"
    tpl.write_text("@_DIALECT = angle.dialect\nHello <<$name>>\n")
    app = Divide(tmp_path, [tpl])
    async with app.run_test() as pilot:
        await settle(pilot)
        ed = app.query_one(EditorWindow).editor
        assert ed.dialect.name == "angle"
        assert (6, 8, "div.replace") in ed._highlights[1]
        assert "angle" in app.status_line._hint_text


async def test_close_dirty_window_asks(tmp_path):
    f = tmp_path / "x.tpl"
    f.write_text("{$a}")
    app = Divide(tmp_path, [f])
    async with app.run_test() as pilot:
        await settle(pilot)
        await pilot.press("Z", "alt+f3")
        await settle(pilot)
        assert isinstance(app.screen, DialogScreen)
        await pilot.click("#no")
        await settle(pilot)
        assert not app.editor_windows()
        assert f.read_text() == "{$a}"


async def test_close_dirty_cancel_and_yes_letter(tmp_path):
    f = tmp_path / "x.tpl"
    f.write_text("{$a}")
    app = Divide(tmp_path, [f])
    async with app.run_test() as pilot:
        await settle(pilot)
        await pilot.press("Z", "ctrl+w")
        await settle(pilot)
        await pilot.press("escape")
        await settle(pilot)
        assert len(app.editor_windows()) == 1
        await pilot.press("ctrl+w")
        await settle(pilot)
        await pilot.press("y")  # plain letter presses ~Y~es
        await settle(pilot)
        assert not app.editor_windows()
        assert f.read_text() == "Z{$a}"


async def test_open_dialog(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "page.tpl").write_text("{$x}")
    app = Divide(tmp_path, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        assert app.project_window() is not None  # shown when no file is given
        await pilot.press("f3")
        await settle(pilot)
        dialog = app.screen.query_one(FileDialog)
        assert app.focused is dialog.query_one(InputLine)
        assert dialog._entries[-1] == "sub/"
        dialog.input.data = "sub"
        await pilot.press("enter")  # into the folder
        await settle(pilot)
        assert dialog.directory == (tmp_path / "sub").resolve()
        assert "page.tpl" in dialog._entries
        dialog.input.data = "page.tpl"
        await pilot.press("enter")
        await settle(pilot)
        win = app.active_editor()
        assert win is not None and win.path == (tmp_path / "sub" / "page.tpl").resolve()
        assert app.focused is win.editor


async def test_menu_and_windows(tmp_path):
    a, b = tmp_path / "a.tpl", tmp_path / "b.tpl"
    a.write_text("a")
    b.write_text("b")
    app = Divide(tmp_path, [a, b])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        wa, wb = app.editor_windows()
        assert (wa.number, wb.number) == (1, 2)
        assert app.active_editor() is wb
        await pilot.press("f6")
        await settle(pilot)
        assert app.active_editor() is wa and app.focused is wa.editor
        await pilot.press("alt+2")
        await settle(pilot)
        assert app.active_editor() is wb
        # Options > Turbo C colors, through the menu
        await pilot.press("alt+o", "c")
        await settle(pilot)
        assert app.theme == "turbo-c"
        # Window > Project toggles the project window
        await pilot.press("ctrl+b")
        await settle(pilot)
        assert isinstance(app.active_window(), ProjectWindow)
        await pilot.press("ctrl+b")
        await settle(pilot)
        assert app.project_window() is None


async def test_new_and_save_as(tmp_path):
    app = Divide(tmp_path, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        await pilot.press("alt+f", "n")
        await settle(pilot)
        win = app.active_editor()
        assert win is not None and win.path is None and win.title == "NONAME00.TPL"
        await pilot.press("H", "i", "f2")
        await settle(pilot)
        dialog = app.screen.query_one(FileDialog)
        dialog.input.data = "hello.tpl"
        await pilot.press("enter")
        await settle(pilot)
        assert (tmp_path / "hello.tpl").read_text() == "Hi"
        assert win.path == (tmp_path / "hello.tpl").resolve() and win.title == "hello.tpl"


# Regressions: Textual runs every handler in the MRO unless prevent_default() is called.


async def test_save_as_with_ok_button(tmp_path):
    app = Divide(tmp_path, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        await pilot.press("alt+f", "n")
        await settle(pilot)
        await pilot.press("A", "f2")
        await settle(pilot)
        dialog = app.screen.query_one(FileDialog)
        dialog.input.data = "new.tpl"
        await pilot.click("#ok")
        await settle(pilot)
        assert not isinstance(app.screen, DialogScreen)
        assert (tmp_path / "new.tpl").read_text() == "A"


async def test_exit_asks_about_unsaved(tmp_path):
    f = tmp_path / "x.tpl"
    f.write_text("")
    app = Divide(tmp_path, [f])
    async with app.run_test() as pilot:
        await settle(pilot)
        await pilot.press("Z", "alt+x")
        await settle(pilot)
        assert isinstance(app.screen, DialogScreen)
        assert app.is_running
        await pilot.press("c")
        await settle(pilot)
        assert app.is_running and len(app.editor_windows()) == 1


async def test_frame_close_and_zoom_icons(tmp_path):
    from textual_vision.constants import Command
    from textual_vision.events import CommandMessage

    f = tmp_path / "x.tpl"
    f.write_text("")
    app = Divide(tmp_path, [f])
    async with app.run_test() as pilot:
        await settle(pilot)
        win = app.editor_windows()[0]
        win.frame.post_message(CommandMessage(Command.ZOOM))
        await settle(pilot)
        assert win.zoomed
        await pilot.press("Z")
        win.frame.post_message(CommandMessage(Command.CLOSE))  # the [■] icon
        await settle(pilot)
        assert isinstance(app.screen, DialogScreen)
        await pilot.press("escape")
        await settle(pilot)
        assert app.editor_windows() == [win]
