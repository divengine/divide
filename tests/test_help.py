from pathlib import Path

from divide import manual
from divide.app import Divide
from divide.ui.help import HelpWindow


async def settle(pilot, n=8):
    for _ in range(n):
        await pilot.pause()


def test_every_cross_reference_leads_somewhere():
    names = manual.page_names()
    assert {"Home", "Help", "Dialector", "Editing-Templates"} <= set(names)
    for name in names + [manual.CONTENTS, manual.INDEX]:
        topic = manual.layout(name, 76)
        assert topic is not None and topic.lines, name
        for line in topic.lines:
            assert sum(len(s.text) for s in line) <= 76 or any(s.style == "code" for s in line), (name, line)
        for link in topic.links:
            page, _, anchor = link.target.partition("#")
            target = manual.layout(page or name, 76)
            assert target is not None, (name, link.target)
            assert not anchor or anchor in target.anchors, (name, link.target)


def test_markdown_is_laid_out():
    topic = manual.layout("Help", 60)
    text = ["".join(s.text for s in line) for line in topic.lines]
    assert text[0] == "Help" and set(text[1]) == {"═"}
    assert not any("![" in line or "**" in line or "[[" in line for line in text)
    # a table: keys in their column, the last column wraps under itself
    row = next(i for i, line in enumerate(text) if line.startswith("Ctrl+F1"))
    assert text[row + 1].startswith(" " * text[row].index("the topic"))
    # external links are text; links to topics are cross references
    styles = {s.style for line in topic.lines for s in line}
    assert {"url", "bold", "heading", "title"} <= styles and "link" not in styles
    assert any(s.style == "link" for line in manual.layout("Dialector", 60).lines for s in line)


def test_index_and_search():
    index = manual.layout(manual.INDEX, 76)
    targets = {link.target for link in index.links}
    assert "Dialector" in targets and any(t.startswith("Dialector#") for t in targets)
    found = manual.search("dialect")
    assert found and found[0][1] == "Dialector"


async def test_help_window(tmp_path: Path):
    (tmp_path / "a.tpl").write_text("{$dialector}\n")
    app = Divide(tmp_path, [tmp_path / "a.tpl"])
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        await pilot.press("f1")  # context help: the editor's topic
        await settle(pilot)
        win = app.help_window()
        assert isinstance(win, HelpWindow) and app.active_window() is win
        assert win.view.name_ == "Editing-Templates" and win.title == "Help: Editing Templates"

        first = win.view.selected
        await pilot.press("tab")
        await settle(pilot)
        second = win.view.selected
        assert second != first
        target = win.view.topic.links[second].target
        await pilot.press("enter")
        await settle(pilot)
        assert win.view.name_ == target.partition("#")[0]

        await pilot.press("alt+f1")  # back, to the same link
        await settle(pilot)
        assert win.view.name_ == "Editing-Templates" and win.view.selected == second

        await pilot.press("shift+f1")
        await settle(pilot)
        assert win.view.name_ == manual.INDEX and app.help_window() is win

        await pilot.press("escape")
        await settle(pilot)
        assert app.help_window() is None

        # Ctrl+F1: the topic of the word under the cursor
        app.active_editor().editor.move_cursor((0, 4))
        await pilot.press("ctrl+f1")
        await settle(pilot)
        assert app.help_window().view.name_ == "Dialector"
