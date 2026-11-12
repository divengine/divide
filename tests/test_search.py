from pathlib import Path

import pytest

from divide.app import Divide
from divide.editor.search import SearchError, SearchOptions, compile_pattern, find, replace_all
from divide.ui.dialogs import DialogScreen, GotoLineDialog, MessageBox, SearchDialog
from divide.ui.windows import EditorWindow


def test_find_options():
    text = "Name name NAME names"
    assert find(text, compile_pattern("name", SearchOptions()), 0).span() == (0, 4)
    assert find(text, compile_pattern("name", SearchOptions(case_sensitive=True)), 0).span() == (5, 9)
    ww = compile_pattern("name", SearchOptions(whole_words=True))
    assert [m.span() for m in ww.finditer(text)] == [(0, 4), (5, 9), (10, 14)]
    assert find(text, compile_pattern("name", SearchOptions()), 15, backward=True).span() == (10, 14)
    assert find(text, compile_pattern("zzz", SearchOptions()), 0) is None


def test_regex_and_errors():
    opts = SearchOptions(regex=True)
    new, n = replace_all("{$a} {$bb}", compile_pattern(r"\{\$(\w+)\}", opts), r"[\1]", opts)
    assert (new, n) == ("[a] [bb]", 2)
    with pytest.raises(SearchError):
        compile_pattern("(", opts)
    with pytest.raises(SearchError):
        compile_pattern("", SearchOptions())
    # literal mode escapes metacharacters and does not expand groups
    lit = SearchOptions()
    assert replace_all("a.b axb", compile_pattern("a.b", lit), r"\1", lit) == (r"\1 axb", 1)


def test_empty_regex_matches_are_skipped():
    opts = SearchOptions(regex=True)
    p = compile_pattern(r"x*", opts)
    assert find("aaxa", p, 0).span() == (2, 3)
    assert replace_all("aaxa", p, "-", opts) == ("aa-a", 1)


def test_replace_all_from_start_offset():
    o = SearchOptions()
    assert replace_all("ab ab ab", compile_pattern("ab", o), "X", o, start=3) == ("ab X X", 2)


# ------------------------------------------------------------------- app


async def settle(pilot, n=3):
    for _ in range(n):
        await pilot.pause()


async def open_app(tmp_path, text):
    f = tmp_path / "s.tpl"
    f.write_text(text)
    return Divide(tmp_path, [f])


async def run_search(pilot, app, key, query, replacement=None, *, flags=None, button="#ok"):
    await pilot.press(key)
    await settle(pilot)
    dialog = app.screen.query_one(SearchDialog)
    dialog.query_input.data = query
    if replacement is not None:
        dialog.replace_input.data = replacement
    if flags is not None:
        dialog.flags.value = flags
    await pilot.click(button)
    await settle(pilot)


async def test_find_and_search_again(tmp_path):
    app = await open_app(tmp_path, "{$a}\n{$b}\n{$a}\n")
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        ed = app.query_one(EditorWindow).editor
        await run_search(pilot, app, "ctrl+f", "{$a}")
        assert ed.selected_text == "{$a}" and ed.selection.start == (0, 0)
        await pilot.press("ctrl+l")
        await settle(pilot)
        assert ed.selection.start == (2, 0)
        await pilot.press("ctrl+l")  # no more: message box
        await settle(pilot)
        assert isinstance(app.screen, DialogScreen)
        assert isinstance(app.screen.dialog, MessageBox)
        await pilot.press("enter")
        await settle(pilot)
        assert not isinstance(app.screen, DialogScreen)


async def test_find_prefills_word_at_cursor(tmp_path):
    app = await open_app(tmp_path, "hello world\n")
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        app.query_one(EditorWindow).editor.move_cursor((0, 8))
        await pilot.press("ctrl+f")
        await settle(pilot)
        assert app.screen.query_one(SearchDialog).query_input.data == "world"


async def test_change_all_without_prompt_is_one_undo(tmp_path):
    app = await open_app(tmp_path, "x {$a} {$a} {$a}")
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        ed = app.query_one(EditorWindow).editor
        await run_search(pilot, app, "ctrl+r", "{$a}", "{$b}", flags=0, button="#all")
        assert ed.text == "x {$b} {$b} {$b}"
        ed.undo()
        assert ed.text == "x {$a} {$a} {$a}"


async def test_replace_with_prompt(tmp_path):
    app = await open_app(tmp_path, "a a a")
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        ed = app.query_one(EditorWindow).editor
        await run_search(pilot, app, "ctrl+r", "a", "b", flags=8, button="#all")  # prompt on
        await pilot.press("y")  # first: yes
        await settle(pilot)
        await pilot.press("n")  # second: no
        await settle(pilot)
        await pilot.press("y")  # third: yes
        await settle(pilot)
        assert ed.text == "b a b"
        assert not isinstance(app.screen, DialogScreen)


async def test_goto_line(tmp_path):
    app = await open_app(tmp_path, "1\n2\n3\n4\n")
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        ed = app.query_one(EditorWindow).editor
        await pilot.press("ctrl+g")
        await settle(pilot)
        app.screen.query_one(GotoLineDialog).input.data = "3"
        await pilot.press("enter")
        await settle(pilot)
        assert ed.cursor_location == (2, 0)


async def test_typing_replaces_prefill_and_enter_is_ok(tmp_path):
    app = await open_app(tmp_path, "hello world\nworld\n")
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        ed = app.query_one(EditorWindow).editor
        ed.move_cursor((0, 1))
        await pilot.press("ctrl+f")
        await settle(pilot)
        await pilot.press("w", "o", "r", "l", "d", "enter")
        await settle(pilot)
        assert not isinstance(app.screen, DialogScreen)
        assert ed.selection.start == (0, 6) and ed.selected_text == "world"
