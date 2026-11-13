from pathlib import Path

from divide import manual
from divide.app import Divide
from divide.ui.help import HelpWindow


async def settle(pilot, n=8):
    for _ in range(n):
        await pilot.pause()


def test_every_cross_reference_leads_somewhere():
    names = manual.page_names()
    assert {"divide:Home", "divide:Help", "divide:Dialector", "div:02.10 Lists (loops)"} <= set(names)
    generated = [manual.LIBRARY] + [f(b.id) for b in manual.books() for f in (manual.contents_of, manual.index_of)]
    for name in names + generated:
        topic = manual.layout(name, 76)
        assert topic is not None and topic.lines, name
        for line in topic.lines:
            assert sum(len(s.text) for s in line) <= 76 or any(s.style == "code" for s in line), (name, line)
        for link in topic.links:
            if link.external:
                assert "://" in link.target or link.target.startswith("mailto:"), (name, link.target)
                continue
            page, _, anchor = link.target.partition("#")
            target = manual.layout(page, 76)
            assert target is not None, (name, link.target)
            assert not anchor or anchor in target.anchors, (name, link.target)


def test_books():
    ids = [b.id for b in manual.books()]
    assert ids[:2] == ["divide", "div"]
    assert manual.qualify("Dialector") == "divide:Dialector" and manual.split("div:README") == ("div", "README")
    # every book has its pages and a home; the library leads to every contents
    for b in manual.books():
        assert manual.page_names(b.id) and manual.source(f"{b.id}:{b.home}") is not None, b.id
    library = manual.layout(manual.LIBRARY, 76)
    assert {link.target for link in library.links} == {manual.contents_of(i) for i in ids}
    # a book without a sidebar: its list of pages, nested by their numbers
    contents = manual.layout(manual.contents_of("div"), 76)
    text = ["".join(s.text for s in line) for line in contents.lines]
    assert " • 2. Template Features" in text and "   • 2.10 Lists (loops)" in text
    # links by file name, inside the book; links out of it are text
    lists = manual.layout("div:02.10 Lists (loops)", 76)
    assert [link.target for link in lists.links] == ["div:02.11 Dynamic vars inside a loop"]
    assert manual.resolve_target("div:README", "../releases/README.md") is None
    assert manual.resolve_target("divide:Home", "div:README") == "div:README"
    assert manual.window_title("div:02.10 Lists (loops)") == "Help: Div · 2.10 Lists (loops)"


def test_markdown_is_laid_out():
    topic = manual.layout("Help", 60)
    assert topic.name == "divide:Help"
    text = ["".join(s.text for s in line) for line in topic.lines]
    assert text[0] == "Help" and set(text[1]) == {"═"}
    assert not any("![" in line or "**" in line or "[[" in line for line in text)
    # a table: keys in their column, the last column wraps under itself
    row = next(i for i, line in enumerate(text) if line.startswith("Ctrl+F1"))
    assert text[row + 1].startswith(" " * text[row].index("the topic"))
    # external links are text; links to topics are cross references
    styles = {s.style for line in topic.lines for s in line}
    assert {"url", "bold", "heading", "title"} <= styles and "link" not in styles
    # web pages are links too, opened by the browser
    assert all(link.external for link in topic.links) and topic.links
    assert any(s.style == "link" for line in manual.layout("Dialector", 60).lines for s in line)


def test_index_and_search():
    index = manual.layout(manual.index_of("divide"), 76)
    targets = {link.target for link in index.links}
    assert "divide:Dialector" in targets and any(t.startswith("divide:Dialector#") for t in targets)
    assert all(t.startswith("divide:") for t in targets)
    found = manual.search("dialect", first="divide")
    assert found and found[0][1] == "divide:Dialector"
    assert manual.search("loops", first="div")[0][1] == "div:02.10 Lists (loops)"


async def test_help_window(tmp_path: Path):
    (tmp_path / "a.tpl").write_text("{$dialector}\n")
    app = Divide(tmp_path, [tmp_path / "a.tpl"])
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        await pilot.press("f1")  # context help: the editor's topic
        await settle(pilot)
        win = app.help_window()
        assert isinstance(win, HelpWindow) and app.active_window() is win
        assert win.view.name_ == "divide:Editing-Templates" and win.title == "Help: Editing Templates"

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
        assert win.view.name_ == "divide:Editing-Templates" and win.view.selected == second

        await pilot.press("shift+f1")
        await settle(pilot)
        assert win.view.name_ == manual.index_of("divide") and app.help_window() is win

        # another book: its contents and index follow it
        win.open("div:02.10 Lists (loops)")
        await settle(pilot)
        assert win.title == "Help: Div · 2.10 Lists (loops)" and win.book == "div"
        await pilot.press("shift+f1")
        await settle(pilot)
        assert win.view.name_ == "div:_Index"

        await pilot.press("escape")
        await settle(pilot)
        assert app.help_window() is None

        # Ctrl+F1: the topic of the word under the cursor
        app.active_editor().editor.move_cursor((0, 4))
        await pilot.press("ctrl+f1")
        await settle(pilot)
        assert app.help_window().view.name_ == "divide:Dialector"


async def test_web_links_open_in_the_browser(tmp_path: Path):
    app = Divide(tmp_path, [])
    opened = []
    app.open_url = lambda url, **kw: opened.append(url)  # type: ignore[method-assign]
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        app.open_help("Home")
        await settle(pilot)
        view = app.help_window().view
        web = next(i for i, link in enumerate(view.topic.links) if link.external)
        view.selected = web
        await pilot.press("enter")
        await settle(pilot)
        assert opened == [view.topic.links[web].target] and view.name_ == "divide:Home"
        # drawn as the terminal's own hyperlink (OSC 8)
        y = view.topic.links[web].places[0][0]
        view.scroll_to(y=y, animate=False)
        await settle(pilot)
        strip = view.render_line(y - view.scroll_offset.y)
        assert any(seg.style and seg.style.link == opened[0] for seg in strip)
