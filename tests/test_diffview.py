"""The diff viewer: unified and side by side, numbers, the words that changed, the bar."""

from textual.app import App, ComposeResult

from divide import config
from divide.ui.diffview import DiffView

DIFF = "\n".join([
    "diff --git a/index.tpl b/index.tpl", "index 1..2 100644", "--- a/index.tpl", "+++ b/index.tpl",
    "@@ -1,4 +1,5 @@ <main>", " <main>", "-  <h1>{$title}</h1>", "+  <h1 class=\"t\">{$title}</h1>",
    "+  <p>{$tagline}</p>", "   {% footer %}", " </main>",
    "@@ -20,2 +21,2 @@", " a", "-b", "+c",
    "diff --git a/logo.png b/logo.png", "Binary files a/logo.png and b/logo.png differ", "",
])


class Host(App):
    def __init__(self) -> None:
        super().__init__()
        self.view = DiffView()
        self.chosen = []

    def compose(self) -> ComposeResult:
        yield self.view

    def on_diff_view_line_chosen(self, message) -> None:
        self.chosen.append((message.path, message.line))


async def test_unified_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(config, "set_value", lambda key, value: None)
    app = Host()
    async with app.run_test(size=(100, 30)) as pilot:
        view = app.view
        view.side_by_side = False
        view.show(DIFF)
        await pilot.pause()
        rows = view.rows_text()
        assert rows[0] == " M index.tpl  +3 -2"
        assert rows[1].strip() == "@@ -1 +1 @@ <main>"
        assert rows[2] == " 1  1   <main>"
        assert rows[3] == " 2    -   <h1>{$title}</h1>"
        assert rows[4] == "    2 +   <h1 class=\"t\">{$title}</h1>"
        assert rows[5] == "    3 +   <p>{$tagline}</p>"
        assert rows[-2] == " B logo.png" and rows[-1].strip() == "Binary file: not shown"
        changed = next(r for r in view.rows if r.kind == "line" and r.left.kind == "+")
        assert changed.left_spans == ((5, 15),)  # the words that came in: ' class="t"'
        assert view.rows[view.cursor].kind == "line"  # the bar starts on the first line


async def test_side_by_side_pairs_and_the_bar(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "set_value", lambda key, value: None)
    app = Host()
    async with app.run_test(size=(100, 30)) as pilot:
        view = app.view
        view.side_by_side = False
        view.show(DIFF)
        view.focus()
        await pilot.pause()
        await pilot.press("down")  # on the removed h1
        await pilot.press("s")
        await pilot.pause()
        assert view.side_by_side
        row = view.rows[view.cursor]
        assert row.kind == "pair" and row.left.text == "  <h1>{$title}</h1>" and row.right.text.startswith("  <h1 class")
        text = view.rows_text()[view.cursor]
        assert text.index("<h1>{$title}") < text.index("│") < text.index("<h1 class")
        lonely = view.rows[view.cursor + 1]
        assert lonely.left is None and lonely.right.text == "  <p>{$tagline}</p>"
        await pilot.press("enter")
        assert app.chosen == [("index.tpl", 2)]
        await pilot.press("n")  # the next hunk
        assert view.rows[view.cursor].right.new == 21
        await pilot.press("p")
        assert view.rows[view.cursor - 1].kind == "hunk" and view.rows[view.cursor - 1].hunk.new_start == 1


async def test_a_message_and_a_conflict(tmp_path, monkeypatch):
    app = Host()
    async with app.run_test(size=(80, 20)) as pilot:
        view = app.view
        view.show_message("Changes\n\nFiles changed since the last commit.")
        await pilot.pause()
        assert view.rows_text()[0] == "Changes"
        view.show("<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> other\n", conflict=True)
        await pilot.pause()
        assert [r.style for r in view.rows] == ["meta", "mod", "meta", "add", "meta"]
        assert view.rows_text()[1] == "2 ours"
