from pathlib import Path

from divide.app import Divide
from divide.lang.div.diagnostics import include_at, include_paths, check, line_col
from divide.lang.div.dialect import DEFAULT_DIALECT, Dialect
from divide.lang.div.lexer import Lexer
from divide.run.render import IncludeTarget
from divide.ui.windows import EditorWindow, MessagesWindow


def diags(text, includes=None, dialect=DEFAULT_DIALECT):
    found = check(text, Lexer(dialect).tokenize(text), dialect, includes)
    return [(line_col(text, d.start), d.severity, d.message) for d in found]


def test_loops_conditions_and_unclosed_blocks():
    text = (
        "[$items]{$value}\n"  # 1 unclosed loop
        "[/$things]\n"  # 2 orphan close
        "{?( $a > 1 )?} yes\n"  # 3 unclosed condition
        "{/?}{/?}\n"  # 4 the second one is an orphan
        "<!--{ never closed\n"  # 5
        "(# 1 + 2\n"  # 6
    )
    got = diags(text)
    assert ((1, 1), "error", "loop [$items] is never closed with [/$items]") in got
    assert ((2, 1), "error", "[/$things] closes a loop that was never opened ([$things])") in got
    assert ((4, 5), "error", "{/?} closes a condition that was never opened") in got
    assert any(where == (5, 1) and "comment <!--{ has no closing }-->" in msg for where, _, msg in got)
    assert any(where == (6, 1) and "formula (#" in msg for where, _, msg in got)
    # the first condition is closed by the first {/?}
    assert not any(where == (3, 1) for where, _, _ in got)


def test_clean_template_and_no_false_positives():
    text = '<svg fill="url(#g)"></svg>\n<!--{ a (# comment }-->\n[$a]{$value}[/$a]\n{?( 1 )?}x{/?}\n{= j: {"a": [1, 2]} =}\n'
    assert diags(text) == []


def test_includes_report_only_what_div_could_not_resolve():
    text = "{% parts/ok %}\n{% parts/missing %}\n{% parts/{$name} %}\n{%% parts/x:main %%}\n{% unknown %}\n"
    tokens = Lexer(DEFAULT_DIALECT).tokenize(text)
    assert [raw for _, _, raw in include_paths(text, tokens, DEFAULT_DIALECT)] == ["parts/ok", "parts/missing", "parts/x:main", "unknown"]
    answers = {
        "parts/ok": IncludeTarget("parts/ok", Path("/p/parts/ok.tpl")),
        "parts/missing": IncludeTarget("parts/missing", None),
        "parts/x:main": IncludeTarget("parts/x", None),
    }
    got = diags(text, answers)  # "unknown" has no answer yet: nothing is said
    assert got == [
        ((2, 4), "warning", "Div cannot find the template parts/missing"),
        ((4, 5), "warning", "Div cannot find the template parts/x"),
    ]
    assert diags(text) == []  # without Div's answers (no engine), no guessing
    assert include_at(text, tokens, DEFAULT_DIALECT, 0)[2] == "parts/ok"  # on "{% "
    assert include_at(text, tokens, DEFAULT_DIALECT, text.index("missing") + 3)[2] == "parts/missing"


def test_tplvar_json_and_dialect():
    got = diags('{= x: {"a": 1, "b": } =}\n{= t: [[:0,3:]{$value}[/]] =}\n')
    assert got == [((1, 21), "warning", "JSON in template variable: unexpected '}', expected a value")]
    broken = Dialect(name="angle", error="file not found")
    assert ((1, 1), "error", "dialect: file not found") in diags("@_DIALECT = angle.dialect\n", dialect=broken)


def test_custom_dialect_tags():
    dialect = Dialect.from_overrides({"DIV_TAG_TPLVAR_BEGIN": "<<=", "DIV_TAG_TPLVAR_END": "=>>"}, name="angle")
    assert diags("{= x: 1\n<<= y: 2\n", dialect=dialect) == [((2, 1), "error", "template variable <<= has no closing =>>")]


async def settle(pilot, n=4):
    for _ in range(n):
        await pilot.pause()


async def test_check_messages_and_navigation(tmp_path):
    tpl = tmp_path / "page.tpl"
    tpl.write_text("ok\n[$items]\n{?( 1 )?}\n")
    app = Divide(tmp_path, [tpl])
    async with app.run_test(size=(110, 34)) as pilot:
        await settle(pilot)
        win = app.query_one(EditorWindow)
        assert len(win.editor.diagnostics) == 2
        assert "2 errors" in app.status_line._hint_text
        # error spans are painted over the syntax colours
        assert any(name == "diag.error" for _, _, name in win.editor._highlights[1])

        await pilot.press("alt+f9")  # Run > Check
        await settle(pilot)
        messages = app.messages_window()
        assert isinstance(messages, MessagesWindow)
        assert [i.text for i in messages.items][0].startswith("page.tpl(2,1): Error: loop [$items]")

        await pilot.press("alt+f8")  # next error: from the Messages window back to the editor
        await settle(pilot)
        assert app.focused is win.editor
        assert win.editor.selected_text == "[$items]"
        assert app.status_line._hint_text.startswith("Error: loop [$items]")
        await pilot.press("alt+f8")
        await settle(pilot)
        assert win.editor.selection.start == (2, 0)
        assert messages.list.focused == 1

        # fixing the template updates the list live
        win.editor.move_cursor((3, 0))
        await pilot.press(*"{/?}[/$items]")
        await settle(pilot)
        assert win.editor.diagnostics == []
        assert [i.text for i in messages.items] == ["page.tpl: no Div errors"]

        # Enter on a message jumps to it
        win.editor.move_cursor((0, 0))
        await pilot.press("delete", "delete", "[", "$", "x", "]")
        await settle(pilot)
        app.raise_window(messages)
        await settle(pilot)
        messages.list.focus_item(0)
        await pilot.press("enter")
        await settle(pilot)
        assert app.focused is win.editor and win.editor.selected_text == "[$x]"
