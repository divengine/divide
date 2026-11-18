from pathlib import Path

from textual import events
from textual_vision.constants import Command
from textual_vision.events import CommandMessage

from divide.app import Divide
from divide.ui.dialogs import DialogScreen, InputDialog, MessageBox
from divide.ui.explorer import LocalMenu


async def settle(pilot, n=12):
    for _ in range(n):
        await pilot.pause()


async def until(pilot, check, tries=100, message=None):
    for _ in range(tries):
        if check():
            return
        await pilot.pause(0.05)
    raise AssertionError(f"timed out: {message()}" if message else "timed out")


def project(tmp_path: Path) -> Path:
    (tmp_path / "page.tpl").write_text("x", encoding="utf-8")
    (tmp_path / "parts").mkdir()
    (tmp_path / "parts" / "a.tpl").write_text("a", encoding="utf-8")
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
        await until(pilot, nav.is_file, message=lambda: sorted(p.name for p in (root / "parts").iterdir()))
        await until(pilot, lambda: tree.selected_path == nav, message=lambda: tree.selected_path)  # reloaded in the background
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


async def test_a_click_puts_the_bar_on_a_file_a_double_click_opens_it(tmp_path):
    root = project(tmp_path)
    app = Divide(root, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        tree = app.project_window().project_tree
        page_line = next(c for c in tree.root.children if c.data.path.name == "page.tpl").line
        await pilot.click(tree, offset=(8, page_line))
        await settle(pilot, 4)
        assert app.editor_windows() == [] and tree.cursor_line == page_line
        await pilot.click(tree, offset=(8, page_line), times=2)
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


def test_file_marks_are_ascii():
    """One ASCII character each: the same width in every terminal, font and platform."""
    from divide.app import SPINNER
    from divide.ui import icons

    marks = [m for m, _ in [*icons.BY_EXTENSION.values(), *icons.BY_NAME.values(), icons.FILE]]
    assert all(len(m) == 1 and m.isascii() and m.isprintable() and m != " " for m in marks)
    assert SPINNER.isascii()


async def test_file_type_marks_are_an_option(tmp_path, monkeypatch):
    from divide.ui import icons

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    project = tmp_path / "p"
    (project / "sub").mkdir(parents=True)
    (project / "a.php").write_text("<?php\n", encoding="utf-8")
    (project / "b.tpl").write_text("x\n", encoding="utf-8")
    app = Divide(project, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await until(pilot, lambda: app.project_window() is not None)  # it opens by itself: no files given
        await settle(pilot)
        tree = app.project_window().project_tree
        lines = lambda: [tree.render_line(y).text.rstrip() for y in range(4)]
        plain = lines()
        assert tree.icons == icons.PLAIN and plain[2].endswith(" ► a.php")  # it unfolds into its members
        app.set_icons(icons.MARKS)
        await pilot.pause()
        marked = lines()
        assert marked[2].endswith(" ? a.php") and marked[3].endswith(" { b.tpl")
        assert [len(l) for l in marked] == [len(l) for l in plain]  # the same width
        assert "► sub" in marked[1]  # folders keep their arrow
        assert app.icons == icons.MARKS  # remembered
        app.set_icons(icons.PLAIN)
        await pilot.pause()
        assert lines() == plain


async def test_the_filter_finds_files_in_folders_never_opened(tmp_path):
    (tmp_path / "src" / "deep").mkdir(parents=True)
    (tmp_path / "src" / "deep" / "Invoice.tpl").write_text("x", encoding="utf-8")
    (tmp_path / "src" / "other.tpl").write_text("x", encoding="utf-8")
    (tmp_path / "readme.md").write_text("x", encoding="utf-8")
    app = Divide(tmp_path, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        tree = app.project_window().project_tree
        tree.focus()
        await settle(pilot)
        await pilot.press(*"invo")
        await until(pilot, lambda: any(line.node.data.path.name == "Invoice.tpl" for line in tree._tree_lines))
        await settle(pilot)
        names = [line.node.data.path.name for line in tree._tree_lines]
        assert names == ["src", "deep", "Invoice.tpl"]
        assert tree.cursor_node.data.path.name == "Invoice.tpl"
        await pilot.press("escape")
        await settle(pilot)
        assert "readme.md" in [line.node.data.path.name for line in tree._tree_lines]


def node_of(tree, path):
    node = tree._node_for(path)
    assert node is not None, path
    return node


async def on_tree(pilot, app, path):
    """The project window in front, its bar on ``path``."""
    if app.project_window() is None:
        app.toggle_project()
        await settle(pilot)
    app.raise_window(app.project_window())
    tree = app.project_window().project_tree
    tree.focus()
    await tree.reveal(path)
    await settle(pilot, 4)
    assert tree.selected_path == path
    return tree


async def test_cut_and_paste_moves_a_file_with_its_window_and_breakpoints(tmp_path):
    root = project(tmp_path)
    page = root / "page.tpl"
    app = Divide(root, [page])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        app.breakpoints[page] = {1}
        tree = await on_tree(pilot, app, page)
        await pilot.press("ctrl+x")
        await settle(pilot, 4)
        assert tree.clipboard == (page, True)
        await pilot.press("escape")  # never mind
        await settle(pilot, 4)
        assert tree.clipboard is None
        await pilot.press("ctrl+x")
        await settle(pilot, 4)
        assert tree.clipboard == (page, True)

        await on_tree(pilot, app, root / "parts")
        await pilot.press("ctrl+v")
        moved = root / "parts" / "page.tpl"
        await until(pilot, lambda: tree.selected_path == moved)
        assert moved.read_text(encoding="utf-8") == "x" and not page.exists()
        assert [w.path for w in app.editor_windows()] == [moved]
        assert app.editor_windows()[0].title == "parts/page.tpl"
        assert app.breakpoints == {moved: {1}}
        assert tree.clipboard is None


async def test_copy_paste_makes_a_copy_and_asks_before_replacing(tmp_path):
    root = project(tmp_path)
    page = root / "page.tpl"
    (root / "a.tpl").write_text("old", encoding="utf-8")
    app = Divide(root, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        tree = await on_tree(pilot, app, page)
        await pilot.press("ctrl+c", "ctrl+v")  # in its own folder: a copy beside it
        await until(pilot, lambda: (root / "page copy.tpl").is_file())
        assert page.read_text(encoding="utf-8") == "x" and tree.clipboard == (page, False)  # a copy can be pasted again

        await on_tree(pilot, app, root / "parts" / "a.tpl")
        await pilot.press("ctrl+x")
        await on_tree(pilot, app, page)
        await pilot.press("ctrl+v")
        await until(pilot, lambda: isinstance(app.screen, DialogScreen))
        assert isinstance(app.screen.dialog, MessageBox) and "a.tpl already exists" in app.screen.dialog._text
        await pilot.press("y")
        await until(pilot, lambda: not (root / "parts" / "a.tpl").exists())
        assert (root / "a.tpl").read_text(encoding="utf-8") == "a"


async def test_a_paste_from_the_terminal_pastes_what_was_cut(tmp_path):
    """Ctrl+V, in some terminals, never reaches divide as a key: the terminal sends its
    clipboard as a paste, and on the tree that is Ctrl+V too."""
    root = project(tmp_path)
    page = root / "page.tpl"
    app = Divide(root, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        tree = await on_tree(pilot, app, page)
        tree.post_message(events.Paste("whatever the terminal holds"))  # nothing cut: nothing done
        await settle(pilot, 4)
        assert page.exists() and not (root / "parts" / "page.tpl").exists()
        await pilot.press("ctrl+x")
        await on_tree(pilot, app, root / "parts")
        tree.post_message(events.Paste("whatever the terminal holds"))
        await until(pilot, lambda: (root / "parts" / "page.tpl").is_file())
        assert not page.exists()


async def test_a_folder_does_not_go_inside_itself_and_move_to(tmp_path):
    root = project(tmp_path)
    app = Divide(root, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        tree = await on_tree(pilot, app, root / "parts")
        await pilot.press("ctrl+x")
        await on_tree(pilot, app, root / "parts" / "a.tpl")
        await pilot.press("ctrl+v")
        await until(pilot, lambda: isinstance(app.screen, DialogScreen))
        assert "inside itself" in app.screen.dialog._text
        await pilot.press("enter")
        await settle(pilot)
        assert (root / "parts" / "a.tpl").is_file()

        await on_tree(pilot, app, root / "page.tpl")
        await pilot.press("alt+f10")
        await settle(pilot, 4)
        assert isinstance(app.screen, LocalMenu)
        await pilot.press("m")  # Move to...
        await until(pilot, lambda: isinstance(app.screen, DialogScreen))
        dialog = app.screen.dialog
        assert isinstance(dialog, InputDialog) and dialog.browse_folders
        dialog.input.data = "deep/er"  # made if missing
        await pilot.press("enter")
        moved = root / "deep" / "er" / "page.tpl"
        await until(pilot, lambda: tree.selected_path == moved)
        assert not (root / "page.tpl").exists()


async def test_rename_with_a_path_moves_it(tmp_path):
    root = project(tmp_path)
    app = Divide(root, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        tree = await on_tree(pilot, app, root / "parts" / "a.tpl")
        await pilot.press("f2")  # the name without the extension is selected
        await settle(pilot, 4)
        await pilot.press(*"../b", "enter")
        await until(pilot, lambda: tree.selected_path == root / "b.tpl")
        assert not (root / "parts" / "a.tpl").exists()


async def test_drag_a_file_onto_a_folder(tmp_path):
    from textual import events

    def mouse(kind, line, button=1):
        return kind(tree, 8, line, 0, 0, button, False, False, False)

    root = project(tmp_path)
    app = Divide(root, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        tree = await on_tree(pilot, app, root / "page.tpl")
        page, parts = node_of(tree, root / "page.tpl"), node_of(tree, root / "parts")
        tree.on_mouse_down(mouse(events.MouseDown, page.line))
        tree.on_mouse_move(mouse(events.MouseMove, page.line))  # no row moved: no drag yet
        assert tree._drag is None
        tree.on_mouse_move(mouse(events.MouseMove, tree.root.line))  # its own folder: nowhere to go
        assert tree._drag is page and tree._drop is None
        tree.on_mouse_move(mouse(events.MouseMove, parts.line))
        assert tree._drop is parts
        tree.on_mouse_up(mouse(events.MouseUp, parts.line))
        await until(pilot, lambda: isinstance(app.screen, DialogScreen))
        assert "page.tpl to parts/" in app.screen.dialog._text
        await pilot.press("y")
        await until(pilot, lambda: (root / "parts" / "page.tpl").is_file())
        assert not (root / "page.tpl").exists() and tree._drag is None and tree._drop is None
