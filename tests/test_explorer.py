from pathlib import Path

from divide.app import Divide
from divide.ui.dialogs import DialogScreen, InputDialog, MessageBox
from divide.ui.explorer import LocalMenu


async def settle(pilot, n=12):
    for _ in range(n):
        await pilot.pause()


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
        assert tree.selected_path == menu  # and shown in the tree

        app.raise_window(app.project_window())
        tree.focus()
        await settle(pilot, 4)
        await pilot.press("f2")  # the name without the extension is selected
        await settle(pilot, 4)
        await pilot.press(*"nav", "enter")
        await settle(pilot)
        nav = root / "parts" / "nav.tpl"
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
        assert (root / "assets" / "css").is_dir() and tree.selected_path == root / "assets" / "css"

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
