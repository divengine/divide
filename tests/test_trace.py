"""Debug > Render trace: Div's mutations of a template, replayed.

The rendering tests need php and Div (DIVIDE_DIV_PHP), as in test_render.py.
"""

from pathlib import Path

import pytest

from divide.app import Divide
from divide.run.render import render
from divide.run.trace import Event, cause_text, changed_span, mutations, trace_render
from divide.ui.tracer import TraceWindow, row_text

from test_render import ENGINE, needs_div


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


def test_changed_span():
    assert changed_span("a{$x}b", "a7b") == ((1, 5), (1, 2))
    assert changed_span("same", "same") == ((4, 4), (4, 4))
    assert changed_span("", "new") == ((0, 0), (0, 3))
    assert changed_span("aXa", "aa") == ((1, 2), (1, 1))  # the overlap of prefix and suffix is not counted twice


def test_mutations_from_events():
    events = [
        Event(1, 1, "Parsing all...", "{?( {$n} > 0 )?}yes{/?}{$n}"),
        Event(1, 1, "Parsing from the original source", None),
        Event(1, 1, "Template | size: 26", None),
        Event(1, 1, "Parsing conditions...", None),
        Event(1, 1, "Parsing condition (from 0 to 14):  {$n}  > 0 ", None),
        Event(2, 2, "Parsing all...", " {$n} > 0 "),  # a sub-parse: the condition's expression
        Event(2, 2, "Template | size: 10", None),
        Event(2, 2, "Parsing matches...", None),
        Event(3, 2, "Parsing includes...", "2"),  # a clone on a value: never parses itself
        Event(2, 2, "Template | size: 7", " 2 > 0 "),
        Event(2, 2, "Parser duration: 0.001 secs", None),
        Event(1, 1, "The condition  2 > 0  is true", None),
        Event(1, 1, "Parsing includes...", "yes{$n}"),
        Event(1, 1, "Parsing matches...", None),
        Event(1, 1, "Parsing match: n in 'yes{$n}'", None),
        Event(1, 1, "Template | size: 4", "yes2"),
        Event(1, 1, "Template | size: 4", None),
        Event(1, 1, "Parser duration: 0.002 secs", None),
    ]
    rows = mutations(events)
    assert [(r.kind, r.run, r.level) for r in rows] == [
        ("start", 1, 1), ("start", 2, 2), ("change", 2, 2), ("end", 2, 2), ("change", 1, 1), ("change", 1, 1), ("end", 1, 1),
    ]
    assert rows[1].context == "Condition: {$n} > 0" and rows[1].label == "Sub-parse: Condition: {$n} > 0"
    assert rows[2].before == " {$n} > 0 " and rows[2].after == " 2 > 0 " and rows[2].label == "Matches"
    assert rows[4].label == "Condition: {$n} > 0 › The condition 2 > 0 is true" and rows[4].delta == -20
    assert rows[5].label == "Matches › Match: n" and rows[5].after == "yes2" and rows[5].cycle == 1
    assert rows[6].label == "Fixed point: nothing changes after 3 cycles" and rows[6].after == "yes2"
    assert row_text(rows[5]).split()[:2] == ["-3", "Matches"]


def test_cause_text_of_lists():
    causes = ["Parsing loops, SUPER KEY = ''...", "Parsing the list: items..", "Checking logical order at 3...",
              "Parsing item 0 of the list 'items'...", "Parsing item 1 of the list 'items'..."]
    assert cause_text(causes) == "Loops, SUPER KEY = '' › List: items (2 items)"
    assert cause_text(["Template | size: 3"]) == "(between cycles)"


def make_page(tmp_path: Path) -> Path:
    (tmp_path / "parts").mkdir()
    (tmp_path / "parts" / "greet.tpl").write_text("Hi {$name}!")
    page = tmp_path / "page.tpl"
    page.write_text("{% parts/greet %}\n?$vip VIP $vip?\n[$items]<{$value}>[/$items]\n")
    (tmp_path / "page.json").write_text('{"name": "Rafa", "vip": true, "items": [1, 2]}')
    return page


@needs_div
async def test_trace_renders_like_render(tmp_path):
    page = make_page(tmp_path)
    code, data = page.read_text(), (tmp_path / "page.json").read_text()
    plain = await render(Path(ENGINE), page, code, data, cwd=tmp_path)
    trace = await trace_render(Path(ENGINE), page, code, data, cwd=tmp_path)
    assert trace.result.output == plain.output == "Hi Rafa!\nVIP\n<1><2>\n"
    rows = trace.mutations
    assert rows[0].kind == "start" and rows[0].after == code
    assert rows[-1].kind == "end" and rows[-1].level == 1
    labels = [r.label for r in rows]
    assert any("Trying to include parts/greet.tpl" in label for label in labels)
    assert any("List: items (2 items)" in label for label in labels)
    assert sum(r.kind == "start" and r.level == 2 for r in rows) >= 2  # the two items
    for r in rows:  # every change goes from its before to its after
        if r.kind == "change":
            (b0, b1), (a0, a1) = r.changed()
            assert r.before[:b0] + r.after[a0:a1] + r.before[b1:] == r.after


@needs_div
async def test_trace_window(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVIDE_DIV_PHP", ENGINE)
    page = make_page(tmp_path)
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(120, 40)) as pilot:
        for _ in range(6):
            await pilot.pause()
        app.run_command(app_command("CM_TRACE_RENDER"))
        for _ in range(200):  # the progress box closes by itself on a success
            if isinstance(app.active_window(), TraceWindow):
                break
            await pilot.pause(0.05)
        window = app.active_window()
        assert isinstance(window, TraceWindow) and window.list.focused == 0
        assert window.view.text == page.read_text() and window.view.lang == "div"
        assert window.rows[-1].kind == "output" and window.rows[-1].after == "Hi Rafa!\nVIP\n<1><2>\n"

        # F8 goes over the sub-parses, F7 into them, Shift+F8 back out
        await pilot.press("f8")
        assert window.rows[window.list.focused].run == 1
        include = next(i for i, r in enumerate(window.rows) if "parts/greet.tpl" in r.label)
        window.list.focus_item(include)
        await pilot.pause()
        row = window.rows[include]
        (a0, a1) = row.changed()[1]
        assert window.view.text == row.after and window.view.marks == [(a0, a1, "trace.new")]
        assert "Trying to include parts/greet.tpl" in app.status_line._hint_text

        # Space: before the mutation, what it took away in red
        await pilot.press("space")
        (b0, b1) = row.changed()[0]
        assert window.view.text == row.before and window.view.marks == [(b0, b1, "trace.old")]
        await pilot.press("space")

        item = next(i for i, r in enumerate(window.rows) if r.kind == "start" and r.level == 2)
        window.list.focus_item(item - 1)
        await pilot.press("f7")
        assert window.list.focused == item
        await pilot.press("f7")
        assert window.rows[window.list.focused].level == 2
        await pilot.press("shift+f8")
        assert window.rows[window.list.focused].level == 1 or window.rows[window.list.focused].kind == "output"


def app_command(name: str) -> int:
    import divide.app as module

    return getattr(module, name)


@needs_div
async def test_f7_traces_a_template(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVIDE_DIV_PHP", ENGINE)
    page = make_page(tmp_path)
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(120, 40)) as pilot:
        for _ in range(6):
            await pilot.pause()
        await pilot.press("f7")
        for _ in range(200):
            if isinstance(app.active_window(), TraceWindow):
                break
            await pilot.pause(0.05)
        window = app.active_window()
        assert isinstance(window, TraceWindow) and window.list.focused == 0
        await pilot.press("f7")  # in the trace window F7 is its own: the next row
        assert app.active_window() is window and window.list.focused == 1
