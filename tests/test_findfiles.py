"""Search > Find in files: a text in every file of the project."""

import pytest

from divide.app import Divide
from divide.editor.search import SearchOptions, compile_pattern
from divide.ui.findfiles import FindInFilesDialog, FindResultsWindow, masks, result_items, search, wanted
from divide.ui.windows import MessagesWindow


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


async def settle(pilot, times: int = 8) -> None:
    for _ in range(times):
        await pilot.pause()


def test_search(tmp_path):
    (tmp_path / "a.tpl").write_text("one\nTitle: {$title}\nend title\n", encoding="utf-8")
    (tmp_path / "b.php").write_text("<?php\n$title = 'x';\n", encoding="utf-8")
    (tmp_path / "c.bin").write_bytes(b"title\0\0")
    files = ["a.tpl", "b.php", "c.bin"]
    hits, in_files = search(tmp_path, files, compile_pattern("title", SearchOptions()))
    assert in_files == 2 and [(h.rel, h.line) for h in hits] == [("a.tpl", 2), ("a.tpl", 2), ("a.tpl", 3), ("b.php", 2)]
    first = hits[0]
    assert (tmp_path / "a.tpl").read_text(encoding="utf-8")[first.start:first.end] == "Title" and first.text == "Title: {$title}"
    whole = compile_pattern("title", SearchOptions(case_sensitive=True, whole_words=True))
    assert [h.line for h in search(tmp_path, ["a.tpl"], whole)[0]] == [2, 3]
    # what an editor holds wins over the file
    assert search(tmp_path, ["b.php"], whole, edited={"b.php": "nothing"})[0] == []
    rows = result_items(tmp_path, "title", "*", hits, in_files)
    assert rows[0].text == '"title" in *: 4 matches in 2 files' and len(rows) == 4  # a row per line
    assert masks(" *.tpl; *.php ") == ["*.tpl", "*.php"] and masks("") == ["*"]
    assert wanted("parts/a.tpl", ["*.tpl"]) and wanted("parts/a.tpl", ["parts/*"]) and not wanted("a.php", ["*.tpl"])


async def test_find_in_files_window(tmp_path):
    tmp_path = tmp_path / "project"  # the config (its histories) lives beside it
    (tmp_path / "parts").mkdir(parents=True)
    (tmp_path / "page.tpl").write_text("{% parts/header %}\nbody\n", encoding="utf-8")
    (tmp_path / "parts" / "header.tpl").write_text("<h1>{$title}</h1>\n<p>header</p>\n", encoding="utf-8")
    app = Divide(tmp_path, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        await pilot.press("shift+f2")
        await settle(pilot)
        dialog = app.screen.query_one(FindInFilesDialog)
        await pilot.press(*"header", "enter")
        for _ in range(60):
            await pilot.pause(0.05)
            if app.find_results_window() is not None:
                break
        await settle(pilot)
        window = app.find_results_window()
        assert isinstance(window, FindResultsWindow) and app.messages_window() is None
        texts = [i.text for i in window.items]
        assert texts[0] == '"header" in *: 2 matches in 2 files'
        assert texts[1:] == ["page.tpl(1): {% parts/header %}", "parts/header.tpl(2): <p>header</p>"]
        assert window.list.focused == 1
        await pilot.press("down", "enter")
        await settle(pilot)
        editor = app.active_editor()
        assert editor.path == tmp_path / "parts" / "header.tpl" and editor.editor.selected_text == "header"
        assert dialog.search_text == "header" and app.search_query == "header"


async def test_filtering_the_results_keeps_where_each_one_goes(tmp_path):
    tmp_path = tmp_path / "project"
    (tmp_path / "parts").mkdir(parents=True)
    (tmp_path / "page.tpl").write_text("{% parts/header %}\nbody\n", encoding="utf-8")
    (tmp_path / "parts" / "header.tpl").write_text("<h1>{$title}</h1>\n<p>header</p>\n", encoding="utf-8")
    app = Divide(tmp_path, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        await pilot.press("shift+f2")
        await settle(pilot)
        await pilot.press(*"header", "enter")
        for _ in range(60):
            await pilot.pause(0.05)
            if app.find_results_window() is not None:
                break
        await settle(pilot)
        window = app.find_results_window()
        await pilot.press(*"<P>")  # only the second file's line: the first one shown
        await settle(pilot)
        assert window.list.items == ["parts/header.tpl(2): <p>header</p>"] and window.list.current == 2
        await pilot.press("enter")
        await settle(pilot)
        editor = app.active_editor()
        assert editor.path == tmp_path / "parts" / "header.tpl" and editor.editor.selected_text == "header"
