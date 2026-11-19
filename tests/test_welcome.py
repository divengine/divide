"""divide without a folder: the Welcome window, File > Open folder / Close folder, the recent lists."""

from pathlib import Path

import pytest

from divide import app as appmod
from divide import recent
from divide.app import CM_CLOSE_FOLDER, Divide
from divide.ui.dialogs import DialogScreen
from divide.ui.welcome import WelcomeWindow
from divide.ui.windows import ProjectWindow
from textual_vision.constants import Command


async def until(pilot, pred, tries=200):
    for _ in range(tries):
        if pred():
            return
        await pilot.pause(0.02)
    raise AssertionError("timed out")


def rows(win: WelcomeWindow) -> list[str]:
    tree = win.git_tree
    return [str(tree.get_node_at_line(i).label) for i in range(tree.last_line + 1)]


def kinds(app) -> list[str]:
    return sorted(type(w).__name__ for w in app.windows())


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "shop"
    (root / "layout").mkdir(parents=True)
    (root / "index.tpl").write_text("<h1>{$title}</h1>\n", encoding="utf-8")
    (root / "layout" / "header.tpl").write_text("<header>\n", encoding="utf-8")
    return root


@pytest.mark.parametrize("args, folder, files", [
    ([], None, []),
    (["."], "cwd", []),
    (["index.tpl"], None, ["index.tpl"]),
    ([".", "index.tpl"], "cwd", ["index.tpl"]),
])
def test_the_command_line_opens_a_folder_only_when_it_is_given(monkeypatch, project, args, folder, files):
    seen = {}

    class Fake:
        def __init__(self, root, files, **_kw):
            seen.update(root=root, files=files)

        def run(self):
            pass

    monkeypatch.chdir(project)
    monkeypatch.setattr(appmod, "Divide", Fake)
    appmod.main(args)
    assert seen["root"] == (project.resolve() if folder else None)
    assert seen["files"] == [Path(f) for f in files]


async def test_nothing_given_shows_the_welcome_window(project):
    recent.add("folders", project)
    recent.add("files", project / "index.tpl")
    app = Divide(None, [])
    async with app.run_test(size=(120, 34)) as pilot:
        await until(pilot, lambda: app.welcome_window() is not None and len(rows(app.welcome_window())) > 5)
        assert kinds(app) == ["WelcomeWindow"] and app.folder is None
        assert rows(app.welcome_window()) == [
            "Start", "New file", "Open a file...", "Open a folder...", "Help",
            "Recent folders  1", "shop", "Recent files  1", "index.tpl"]


async def test_a_recent_folder_becomes_the_project(project):
    recent.add("folders", project)
    app = Divide(None, [])
    async with app.run_test(size=(120, 34)) as pilot:
        await until(pilot, lambda: app.welcome_window() is not None)
        app.welcome_chosen("folder", project)
        await until(pilot, lambda: app.project_window() is not None)
        assert app.folder == project.resolve() and app.root == project.resolve()
        assert kinds(app) == ["ProjectWindow"]  # the Welcome window is gone
        assert str(app.project_window().project_tree.root.label).startswith("shop")


async def test_a_file_on_its_own_and_ctrl_b_offers_a_folder(project):
    app = Divide(None, [project / "layout" / "header.tpl"])
    async with app.run_test(size=(120, 34)) as pilot:
        await until(pilot, lambda: app.active_editor() is not None)
        assert app.folder is None and app.root == (project / "layout").resolve()
        assert app.active_editor().title == "header.tpl"
        assert recent.entries("files") == [(project / "layout" / "header.tpl").resolve()]
        await pilot.press("ctrl+b")
        await until(pilot, lambda: isinstance(app.screen, DialogScreen))
        assert "No folder is open" in app.screen.dialog._text
        await pilot.press("escape")
        await until(pilot, lambda: not isinstance(app.screen, DialogScreen))
        assert app.project_window() is None


async def test_opening_another_folder_closes_the_windows_of_the_last(project, tmp_path):
    other = tmp_path / "blog"
    other.mkdir()
    app = Divide(project, [project / "index.tpl"])
    async with app.run_test(size=(120, 34)) as pilot:
        await until(pilot, lambda: app.active_editor() is not None)
        assert await app.open_folder(other)
        await until(pilot, lambda: app.project_window() is not None)
        assert kinds(app) == ["ProjectWindow"] and app.folder == other.resolve()
        assert [p.name for p in recent.entries("folders")] == ["blog", "shop"]


async def test_unsaved_changes_are_asked_about_before_the_folder_changes(project, tmp_path):
    app = Divide(project, [project / "index.tpl"])
    async with app.run_test(size=(120, 34)) as pilot:
        await until(pilot, lambda: app.active_editor() is not None)
        app.active_editor().editor.insert("x")
        app.run_command(CM_CLOSE_FOLDER)
        await until(pilot, lambda: isinstance(app.screen, DialogScreen))
        await pilot.press("escape")  # cancel: nothing closes
        await until(pilot, lambda: not isinstance(app.screen, DialogScreen))
        assert app.folder == project.resolve() and app.active_editor() is not None


async def test_close_folder_goes_back_to_the_welcome_window(project):
    app = Divide(project, [])
    async with app.run_test(size=(120, 34)) as pilot:
        await until(pilot, lambda: app.project_window() is not None)
        app.run_command(CM_CLOSE_FOLDER)
        await until(pilot, lambda: app.welcome_window() is not None)
        assert kinds(app) == ["WelcomeWindow"] and app.folder is None
        await until(pilot, lambda: "shop" in rows(app.welcome_window()))


async def test_del_forgets_a_recent_file(project):
    recent.add("files", project / "index.tpl")
    app = Divide(None, [])
    async with app.run_test(size=(120, 34)) as pilot:
        await until(pilot, lambda: app.welcome_window() is not None and "index.tpl" in rows(app.welcome_window()))
        win = app.welcome_window()
        win.git_tree.put_bar(f"files:{(project / 'index.tpl').resolve()}")
        await until(pilot, lambda: win.row is not None and win.row.kind == "file")
        await pilot.press("delete")
        await until(pilot, lambda: "index.tpl" not in rows(win))
        assert recent.entries("files") == []
