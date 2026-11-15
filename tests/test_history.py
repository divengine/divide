"""File > Open laid out as Turbo Pascal's, and THistory: input lines remember."""

from datetime import datetime

import pytest

from divide import config
from divide.app import Divide
from divide.ui import history
from divide.ui.dialogs import FileDialog, FileList, file_info
from divide.ui.history import HistoryInput, HistoryList
from divide.ui.windows import PassiveScrollBar


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


async def settle(pilot, times: int = 6) -> None:
    for _ in range(times):
        await pilot.pause()


def test_history_store():
    assert history.entries("file") == []
    for text in ("a.tpl", "b.tpl", "a.tpl", "  ", *(f"{n}.php" for n in range(30))):
        history.add("file", text)
    found = history.entries("file")
    assert found[0] == "29.php" and len(found) == history.MAX_ENTRIES
    assert found.count("a.tpl") <= 1 and "" not in found
    history.add("find", "needle")
    assert history.entries("find") == ["needle"]  # each line its own history
    assert set(config.load()["history"]) == {"file", "find"}


def test_file_info(tmp_path):
    path = tmp_path / "about.pas"
    path.write_text("x" * 77)
    when = datetime(2019, 5, 4, 22, 16).timestamp()
    import os

    os.utime(path, (when, when))
    line = file_info(path, "about.pas", 50)
    assert line.startswith("about.pas") and line.endswith("77  May 4, 2019  10:16pm") and len(line) <= 50
    assert "Directory" in file_info(tmp_path, "../", 50)


async def test_open_dialog_and_its_history(tmp_path):
    (tmp_path / "sub").mkdir()
    for name in ("a.tpl", "b.tpl", "notes.txt"):
        (tmp_path / name).write_text(name)
    app = Divide(tmp_path, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        await pilot.press("f3")
        await settle(pilot)
        dialog = app.screen.query_one(FileDialog)
        files = dialog.query_one(FileList)
        assert dialog.query_one(PassiveScrollBar) is files.v_scroll_bar  # the list's own bar
        assert dialog._entries == ["..", "sub/", "a.tpl", "b.tpl", "notes.txt"]
        assert dialog.info_lines[0].endswith(tmp_path.name + "/*")  # the folder (cut at the left when long)
        # Tab: from the name line into the list (keys too), the pane follows the bar
        await pilot.press("tab")
        await settle(pilot, 3)
        assert app.focused is files
        await pilot.press("down", "down")
        await settle(pilot, 3)
        assert dialog.input.data == "a.tpl" and "a.tpl" in dialog.info_lines[1]
        await pilot.press("enter")
        await settle(pilot)
        assert app.active_editor() is not None and app.active_editor().path == tmp_path / "a.tpl"
        assert history.entries("file") == ["a.tpl"]  # what was opened is remembered
        # the next time: Down in the name line lists it, Enter puts it back
        history.add("file", "notes.txt")
        await pilot.press("f3")
        await settle(pilot)
        dialog = app.screen.query_one(FileDialog)
        await pilot.press("down")
        await settle(pilot, 3)
        popup = app.screen.query_one(HistoryList)
        assert popup.region.y == dialog.query_one(HistoryInput).region.y + 1  # under the line
        await pilot.press("down", "enter")
        await settle(pilot, 3)
        assert not app.screen.query(HistoryList) and dialog.input.data == "a.tpl"
        assert app.focused is dialog.input
        await pilot.press("escape")  # Cancel: nothing remembered
        await settle(pilot)
        assert history.entries("file") == ["notes.txt", "a.tpl"]


async def test_find_remembers(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("one two three\n")
    app = Divide(tmp_path, [path])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+f")
        await settle(pilot)
        await pilot.press(*"two", "enter")
        await settle(pilot)
        assert history.entries("find") == ["two"]
