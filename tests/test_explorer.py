from pathlib import Path

from textual_vision.constants import Command
from textual_vision.events import CommandMessage

from divide.app import Divide
from divide.ui.dialogs import DialogScreen, InputDialog, MessageBox
from divide.ui.explorer import LocalMenu


async def settle(pilot, n=12):
    for _ in range(n):
        await pilot.pause()


async def until(pilot, check, tries=100):
    for _ in range(tries):
        if check():
            return
        await pilot.pause(0.05)
    raise AssertionError("timed out")


def project(tmp_path: Path) -> Path:
    (tmp_path / "page.tpl").write_text("x")
    (tmp_path / "parts").mkdir()
    (tmp_path / "parts" / "a.tpl").write_text("a")
    (tmp_path / ".git").mkdir()
    return tmp_path.resolve()


async def test_new_file_rename_delete(tmp_path):
    root = project(tmp_path)
    app = Divide(root, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        tree = app.project_window().project_tree
        assert app.focused is tree
        assert ".git" not in [c.label.plain for c in tree.root.children]

        await pilot.press("insert")
        await settle(pilot, 4)
        assert isinstance(app.screen, DialogScreen) and isinstance(app.screen.dialog, InputDialog)
        await pilot.press(*"parts/menu.tpl", "enter")
        await settle(pilot)
        menu = root / "parts" / "menu.tpl"
        assert menu.is_file()
        assert [w.path for w in app.editor_windows()] == [menu]  # opened
        await until(pilot, lambda: tree.selected_path == menu)  # and shown in the tree

        app.raise_window(app.project_window())
        tree.focus()
        await settle(pilot, 4)
        await pilot.press("f2")  # the name without the extension is selected
        await settle(pilot, 4)
        await pilot.press(*"nav", "enter")
        await settle(pilot)
        nav = root / "parts" / "nav.tpl"
        await until(pilot, lambda: tree.selected_path == nav)  # the tree is reloaded in the background
        assert nav.is_file() and not menu.exists()
        win = app.editor_windows()[0]
        assert win.path == nav and win.title == "parts/nav.tpl" and tree.selected_path == nav

        await pilot.press("delete")
        await settle(pilot, 4)
        assert isinstance(app.screen.dialog, MessageBox) and "parts/nav.tpl" in app.screen.dialog._text
        await pilot.press("y")
        await settle(pilot)
        assert not nav.exists() and app.editor_windows() == []


async def test_local_menu_new_folder_and_bad_names(tmp_path):
    root = project(tmp_path)
    app = Divide(root, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        tree = app.project_window().project_tree
        await pilot.press("alt+f10")
        await settle(pilot, 4)
        assert isinstance(app.screen, LocalMenu)
        await pilot.press("d")  # New folder
        await settle(pilot, 4)
        await pilot.press(*"assets/css", "enter")
        await settle(pilot)
        await until(pilot, lambda: tree.selected_path == root / "assets" / "css")
        assert (root / "assets" / "css").is_dir()

        await pilot.press("insert")
        await settle(pilot, 4)
        await pilot.press(*"../outside.tpl", "enter")
        await settle(pilot, 4)
        assert isinstance(app.screen.dialog, MessageBox) and "inside the project" in app.screen.dialog._text
        assert not (root.parent / "outside.tpl").exists()


async def test_delete_keeps_unsaved_windows(tmp_path):
    root = project(tmp_path)
    page = root / "page.tpl"
    app = Divide(root, [page])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        win = app.editor_windows()[0]
        win.editor.insert("changed ")
        app.toggle_project()
        await settle(pilot)
        tree = app.project_window().project_tree
        tree.focus()
        await tree.reveal(page)
        await settle(pilot, 4)
        await pilot.press("delete", "y")
        await settle(pilot)
        assert not page.exists()
        assert app.editor_windows() == [win]  # unsaved work is not thrown away


async def test_right_click_opens_local_menu_not_the_file(tmp_path):
    root = project(tmp_path)
    app = Divide(root, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        tree = app.project_window().project_tree
        page_line = next(c for c in tree.root.children if c.data.path.name == "page.tpl").line
        await pilot.click(tree, offset=(8, page_line), button=3)
        await settle(pilot, 4)
        assert isinstance(app.screen, LocalMenu) and app.editor_windows() == []
        assert tree.selected_path == root / "page.tpl"
        await pilot.press("o")  # Open
        await settle(pilot)
        assert [w.path for w in app.editor_windows()] == [root / "page.tpl"]


async def test_window_tile_arranges_every_window(tmp_path):
    root = project(tmp_path)
    app = Divide(root, [root / "page.tpl", root / "parts" / "a.tpl"])
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot)
        app.toggle_project()
        await settle(pilot)
        app.post_message(CommandMessage(Command.TILE))
        await settle(pilot)
        regions = [w.region for w in app.windows()]
        assert len({r.x for r in regions} | {r.y for r in regions}) > 2  # not all stacked at (0, 1)
        assert all(not a.overlaps(b) for i, a in enumerate(regions) for b in regions[i + 1 :])


async def test_nerd_font_icons_are_an_option(tmp_path, monkeypatch):
    from divide.ui import icons

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    project = tmp_path / "p"
    (project / "sub").mkdir(parents=True)
    (project / "a.php").write_text("<?php\n")
    (project / "b.tpl").write_text("x\n")
    app = Divide(project, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        if app.project_window() is None:
            app.toggle_project()
        for _ in range(6):
            await pilot.pause()
        tree = app.project_window().project_tree
        lines = lambda: [tree.render_line(y).text for y in range(4)]
        assert tree.icons == icons.PLAIN and not any(icons.BY_EXTENSION[".php"][0] in l for l in lines())
        app.set_icons(icons.NERD)
        await pilot.pause()
        text = "\n".join(lines())
        assert icons.FOLDER in text and icons.BY_EXTENSION[".php"][0] in text and icons.BY_EXTENSION[".tpl"][0] in text
        assert app.icons == icons.NERD  # remembered
        app.set_icons(icons.PLAIN)
        await pilot.pause()
        assert icons.FOLDER not in "\n".join(lines())
