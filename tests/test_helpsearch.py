"""Help > Search: the books by words, ranked (SQLite FTS5)."""

import sqlite3
from pathlib import Path

from divide import manual
from divide.app import Divide
from divide.manual import fulltext
from divide.ui.helpsearch import HelpSearchDialog, lit


async def settle(pilot, n=8):
    for _ in range(n):
        await pilot.pause()


def test_sections_of_a_page():
    found = fulltext.sections("divide:Debugging-PHP")
    headings = [h for h, _, _ in found]
    assert headings[0] == "" and "Breakpoints" in headings  # the opening, then each section
    anchor = dict((h, a) for h, a, _ in found)["Breakpoints"]
    assert manual.resolve_target("divide:Debugging-PHP", f"#{anchor}") == f"divide:Debugging-PHP#{anchor}"
    assert all("![" not in text and "**" not in text for _, _, text in found)  # words, not Markdown


def test_search_ranks_and_stems():
    hits = fulltext.search("breakpoint")
    assert hits[0].target == "divide:Debugging-PHP#breakpoints" and hits[0].label == "Breakpoints · Debugging PHP"
    assert fulltext.MARK_START in hits[0].snippet or fulltext.MARK_START in hits[1].snippet
    assert [h.rank for h in hits] == sorted(h.rank for h in hits)  # best first
    # stems: "configure" finds "configuration"; the last word is a prefix while it is typed
    assert fulltext.search("configure") and fulltext.search("xdeb")
    # all the words when a section has them all, else any of them
    both = fulltext.search("xdebug path")
    assert both and all("xdebug" in (h.title + h.heading + h.snippet).lower() for h in both)
    assert fulltext.search("xdebug zzqqx")  # nothing has both: any
    # FTS5's operators are plain words; nothing typed, nothing found
    assert [h.target for h in fulltext.search('debugging OR "')] == [h.target for h in fulltext.search("debugging or")]
    assert fulltext.search("  ") == []


def test_index_file_is_current_or_rebuilt(tmp_path: Path, monkeypatch):
    built = tmp_path / "search.sqlite"
    rows = fulltext.build(built)
    assert rows > 100
    db = sqlite3.connect(built)
    assert db.execute("SELECT value FROM meta").fetchone()[0] == fulltext.fingerprint()
    db.execute("UPDATE meta SET value = 'old'")
    db.commit()
    db.close()
    monkeypatch.setattr(fulltext, "INDEX_FILE", built)
    fulltext._connection.cache_clear()
    try:
        db = fulltext.connection()  # stale: built again, in memory
        assert db.execute("PRAGMA database_list").fetchone()[2] == ""
        assert fulltext.search("breakpoint")
    finally:
        fulltext._connection.cache_clear()


def test_shipped_index_is_current():
    """tools/sync_book.py --index after changing a book (the app would rebuild it in memory)."""
    db = sqlite3.connect(fulltext.INDEX_FILE)
    assert db.execute("SELECT value FROM meta").fetchone()[0] == fulltext.fingerprint()


def test_lit():
    assert lit("Breakpoints · Debugging PHP", ["break", "php"]) == (0, 1, 2, 3, 4, 24, 25, 26)


async def test_help_search_dialog(tmp_path: Path):
    (tmp_path / "a.tpl").write_text("{$nothingtofind}\n")
    app = Divide(tmp_path, [tmp_path / "a.tpl"])
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        await pilot.press("alt+h", "s")
        await settle(pilot)
        dialog = app.screen.query_one(HelpSearchDialog)
        await pilot.press(*"breakpoint")
        await settle(pilot, 4)
        assert dialog.hits and dialog.list.rows[0].text == "Breakpoints · Debugging PHP"
        assert "Debugging PHP" in str(dialog.info.render())
        await pilot.press("enter")
        await settle(pilot)
        win = app.help_window()
        assert win is not None and win.view.name_ == "divide:Debugging-PHP"
        await pilot.press("escape")
        await settle(pilot)
        # Ctrl+F1 on a word with no topic of its own: the search, with the word
        app.active_editor().editor.move_cursor((0, 4))
        await pilot.press("ctrl+f1")
        await settle(pilot)
        dialog = app.screen.query_one(HelpSearchDialog)
        assert dialog.input.data == "nothingtofind"
        await pilot.press("escape")
