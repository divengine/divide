"""Go to file (Ctrl+P) and the command palette (Alt+P, or a > in Go to file)."""

import pytest

from divide.app import CM_ABOUT, Divide
from divide.ui import history
from divide.ui.dialogs import MessageBox
from divide.ui.palette import (
    COMMANDS_TITLE,
    FILES_TITLE,
    PaletteDialog,
    file_item,
    match,
    menu_items,
    project_files,
    rank,
)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


async def settle(pilot, times: int = 6) -> None:
    for _ in range(times):
        await pilot.pause()


def test_match_scores_words_runs_and_names():
    assert match("xyz", "abc") is None
    assert match("ba", "ab") is None  # the letters in order
    score, offsets = match("fop", "File > Open...")
    assert offsets == [0, 7, 8]
    # the file name over its folders, word starts over letters inside words
    names = [file_item(n) for n in ("history/notes.md", "src/ui/history.py", "dialogs.py")]
    assert [i.text for i in rank("hist", names)][0] == "src/ui/history.py"
    assert [i.text for i in rank("dp", names)] == ["dialogs.py"]
    # long paths cost little: no combinations are tried
    long = "a/" * 200 + "a" * 300
    assert match("a" * 40, long) is not None


def test_project_files(tmp_path):
    (tmp_path / "a.tpl").write_text("", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("", encoding="utf-8")
    (tmp_path / "parts").mkdir()
    (tmp_path / "parts" / "b.tpl").write_text("", encoding="utf-8")
    assert project_files(tmp_path) == ["a.tpl", "parts/b.tpl"]  # not a repository: a walk


def test_menu_items():
    app = Divide.__new__(Divide)
    found = menu_items(app.init_menu_bar())
    by_text = {i.text: i for i in found}
    assert by_text["File > Open..."].key == "F3"
    assert by_text["Help > About..."].value == (CM_ABOUT, None)
    assert not any(t.endswith(" > ") for t in by_text)


async def test_go_to_file_and_commands(tmp_path):
    (tmp_path / "parts").mkdir()
    for name in ("page.tpl", "parts/header.tpl", "parts/footer.tpl", "notes.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    app = Divide(tmp_path, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+p")
        await settle(pilot)
        dialog = app.screen.query_one(PaletteDialog)
        assert dialog.title == FILES_TITLE and len(dialog.shown) == 4
        await pilot.press(*"phd")
        await settle(pilot, 3)
        assert [i.text for i in dialog.shown] == ["parts/header.tpl"]
        await pilot.press("enter")
        await settle(pilot)
        assert app.active_editor().path == tmp_path / "parts" / "header.tpl"
        # a > turns it into the commands; Down moves the bar, the keys stay in the line
        await pilot.press("ctrl+p")
        await settle(pilot)
        dialog = app.screen.query_one(PaletteDialog)
        assert dialog.shown[0].text == "parts/header.tpl"  # the open ones first
        await pilot.press(">", *"about")
        await settle(pilot, 3)
        assert dialog.title == COMMANDS_TITLE and dialog.shown[0].text == "Help > About..."
        await pilot.press("enter")
        await settle(pilot)
        assert isinstance(app.screen.query_one(MessageBox), MessageBox)  # the About box
        assert history.entries("commands") == ["Help > About..."]
        await pilot.press("escape")
        await settle(pilot)
        # a command run lately is the first one shown
        await pilot.press("alt+p")
        await settle(pilot)
        dialog = app.screen.query_one(PaletteDialog)
        assert dialog.input.data == ">" and dialog.shown[0].text == "Help > About..."
        await pilot.press("backspace")
        await settle(pilot, 3)
        assert dialog.title == FILES_TITLE
        await pilot.press("escape")
        await settle(pilot)
        assert not app.screen.query(PaletteDialog)
