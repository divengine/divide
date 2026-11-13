import json
import os
import shutil
from pathlib import Path

import pytest

from divide.app import Divide
from divide.lang.div import dialector as dx
from divide.lang.div.dialect import DEFAULT_TAGS, Dialect
from divide.lang.div.lexer import Lexer
from divide.run.render import ENV_ENGINE, check_dialect
from divide.ui.dialector import DialectorWindow, SectionDialog, TransformDialog, TranslateDialog
from divide.ui.dialogs import DialogScreen
from divide.ui.explorer import LocalMenu

ENGINE = os.environ.get(ENV_ENGINE)
needs_div = pytest.mark.skipif(
    not (shutil.which("php") and ENGINE and Path(ENGINE).is_file()),
    reason=f"needs php and {ENV_ENGINE} pointing to Div",
)

ERB = {
    "DIV_TAG_REPLACEMENT_PREFIX": "<%",
    "DIV_TAG_REPLACEMENT_SUFFIX": "%>",
    "DIV_TAG_MULTI_MODIFIERS_PREFIX": "<%$",
    "DIV_TAG_MULTI_MODIFIERS_SUFFIX": "|%>",
}


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


# ------------------------------------------------------------------ core
def test_sections_cover_every_tag_once_and_every_tag_has_an_example():
    assert sorted(dx.ALL_KEYS) == sorted(DEFAULT_TAGS)
    assert len(dx.ALL_KEYS) == len(set(dx.ALL_KEYS))
    assert set(dx.example({}).spans) == set(DEFAULT_TAGS)


def test_example_spans_point_at_the_tags():
    filled = dx.example(ERB)
    for key, spans in filled.spans.items():
        for a, b in spans:
            assert filled.text[a:b] == {**DEFAULT_TAGS, **ERB}[key]
    a, b = filled.sections["Replacements"]
    assert filled.text[a:b].startswith("Replacements\n------------\nHello <%$name%>")


def test_example_lexes_as_div_in_its_dialect():
    filled = dx.example(ERB)
    tokens = Lexer(Dialect.from_overrides(ERB)).tokenize(filled.text)
    start = filled.text.index("Hello ") + len("Hello ")
    assert [t.kind for t in tokens if t.start == start] == ["div.replace"]


def test_dialect_json_php_and_transform():
    tags = {**DEFAULT_TAGS, **ERB}
    assert json.loads(dx.dialect_json(tags)) == ERB
    assert dx.dialect_json(DEFAULT_TAGS) == "{}\n"
    php = dx.php_code({**DEFAULT_TAGS, "DIV_TAG_EMPTY": "it's"})
    assert "define('DIV_TAG_EMPTY', 'it\\'s');" in php and php.startswith("<?php")
    changed = dx.transform(DEFAULT_TAGS, "{", "{{")
    assert changed["DIV_TAG_REPLACEMENT_PREFIX"] == "{{" and changed["DIV_TAG_TPLVAR_BEGIN"] == "{{="
    assert all("{" in DEFAULT_TAGS[k] for k in changed) and dx.transform(DEFAULT_TAGS, "", "x") == {}


def test_differences_name_the_section():
    expected = dx.example({}).text
    read = expected.replace("{%% footer:footer.json %%}", "{%% footerfooter.json %%}")
    (d,) = dx.differences(ERB, read)
    assert d.section == "Includes and locations" and d.line == 2
    assert d.read == "{%% footerfooter.json %%}" and dx.differences(ERB, expected) == []


# ---------------------------------------------------------- Div decides
@needs_div
async def test_div_validates_and_reads_dialects_back(tmp_path):
    ok = await check_dialect(Path(ENGINE), {}, cwd=tmp_path, sample=dx.example({}).text, expected=dx.example({}).text)
    assert ok.valid and ok.readable
    bad = await check_dialect(Path(ENGINE), {"DIV_TAG_EMPTY": "@break@"}, cwd=tmp_path)
    assert bad.reason == "DIV_TAG_BREAK must be unique and not equal to DIV_TAG_EMPTY"
    erb = await check_dialect(Path(ENGINE), ERB, cwd=tmp_path, sample=dx.example(ERB).text, expected=dx.example({}).text)
    assert erb.valid
    # Everything but what Div's translator itself gets wrong reads back.
    assert {d.section for d in dx.differences(ERB, erb.translated)} <= {"Includes and locations"}


async def settle(pilot, n=8):
    for _ in range(n):
        await pilot.pause()


async def until(pilot, check, tries=80):
    for _ in range(tries):
        if check():
            return
        await pilot.pause(0.05)
    raise AssertionError("timed out")


@needs_div
async def test_dialector_end_to_end(tmp_path):
    app = Divide(tmp_path, [])
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        await pilot.press("alt+t", "d")  # Tools > Dialector: a new dialect file
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)
        win = app.active_window()
        assert isinstance(win, DialectorWindow) and (tmp_path / "my.dialect").read_text() == "{}\n"
        await until(pilot, lambda: win.verdict is not None)
        assert win.verdict.valid and win.verdict.readable

        # Replacements: the prefix becomes <%, and the preview follows while typing
        await pilot.press("enter")
        await settle(pilot)
        dialog = app.screen.dialog
        assert isinstance(dialog, SectionDialog) and dialog.section.title == "Replacements"
        await pilot.press("end", "backspace", "<", "%")
        await settle(pilot)
        assert dialog.preview.text.startswith("Hello <%$name}")
        await pilot.click("#ok")
        await settle(pilot)
        assert json.loads(win.source.editor.text) == {"DIV_TAG_REPLACEMENT_PREFIX": "<%"}
        assert win.source.dirty and "Hello <%$name}" in win.preview.text

        # an invalid dialect: Div says why, and the section is marked
        await pilot.press("down", "enter")  # Modifiers
        await settle(pilot)
        dialog = app.screen.dialog
        assert dialog.section.title == "Modifiers"
        for _ in range(18):  # Tab walks every field, scrolling the long list
            await pilot.press("tab")
        await settle(pilot)
        assert dialog.focused_key == "DIV_TAG_MODIFIER_FORMAT"
        dialog.inputs["DIV_TAG_MODIFIER_LOWERCASE"].data = "^"
        await pilot.click("#ok")
        await settle(pilot)
        await until(pilot, lambda: win.verdict is not None and win.verdict.reason)
        assert "must be unique" in win.verdict.reason
        assert win.sections.items[1].startswith("!")

        # Ctrl+Z goes back through the file's history
        await pilot.press("ctrl+z")
        await settle(pilot)
        assert json.loads(win.source.editor.text) == {"DIV_TAG_REPLACEMENT_PREFIX": "<%"}
        await until(pilot, lambda: win.verdict is not None and win.verdict.valid)

        # Transform all tags: { -> {{
        await pilot.press("alt+f10")
        await settle(pilot)
        assert isinstance(app.screen, LocalMenu)
        await pilot.press("t")
        await settle(pilot)
        dialog = app.screen.dialog
        assert isinstance(dialog, TransformDialog)
        await pilot.press("{", "tab", "{", "{")
        await settle(pilot)
        assert dialog.changes["DIV_TAG_TPLVAR_BEGIN"] == "{{="
        await pilot.click("#ok")
        await settle(pilot)
        assert json.loads(win.source.editor.text)["DIV_TAG_TPLVAR_BEGIN"] == "{{="

        # PHP code in a new window
        await pilot.press("alt+f10", "p")
        await settle(pilot)
        php = app.active_editor()
        assert php.path is None and "define('DIV_TAG_TPLVAR_BEGIN', '{{=');" in php.editor.text

        # an example template that uses the dialect (the dialect is saved first)
        app.raise_window(win)
        win.sections.focus()
        await settle(pilot)
        await pilot.press("alt+f10", "x")
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)
        example = tmp_path / "my.example.tpl"
        assert example.read_text().startswith("@_DIALECT = my.dialect\n")
        assert not win.source.dirty
        opened = app.active_editor()
        assert opened.path == example.resolve()
        assert opened.editor.dialect.name == "my" and opened.editor.dialect["DIV_TAG_TPLVAR_BEGIN"] == "{{="
        assert not [d for d in opened.editor.diagnostics if d.severity == "error"]


async def test_dialector_without_div_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_ENGINE, str(tmp_path / "missing.php"))
    (tmp_path / "x.dialect").write_text('{"DIV_TAG_EMPTY": "@nothing@"}')
    app = Divide(tmp_path, [tmp_path / "x.dialect"])
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        await pilot.press("alt+t", "d")  # on the active .dialect file
        await settle(pilot)
        win = app.active_window()
        assert isinstance(win, DialectorWindow) and win.tags["DIV_TAG_EMPTY"] == "@nothing@"
        await pilot.pause(0.6)
        await settle(pilot)
        assert "Div was not found" in str(win.verdict_box.render())
        assert win.sections.items[4].startswith("•")  # Loops and iterations: changed


def test_dialect_property_and_import():
    assert dx.set_dialect_property("@_DIALECT = a.dialect\nHi\n", "b.dialect") == "@_DIALECT = b.dialect\nHi\n"
    assert dx.set_dialect_property("@_DIALECT = a.dialect\nHi\n", None) == "Hi\n"
    assert dx.set_dialect_property("Hi\n", "b.dialect") == "@_DIALECT = b.dialect\nHi\n"
    php = "<?php\ndefine('DIV_TAG_EMPTY', 'it\\'s');\ndefine(\"DIV_TAG_ELSE\", \"@or@\");\ndefine('OTHER', 1);\n"
    assert dx.parse_import(php, php=True) == ({"DIV_TAG_EMPTY": "it's", "DIV_TAG_ELSE": "@or@"}, [])
    # the original web dialector saved single-quoted keys
    assert dx.parse_import("{ 'DIV_TAG_EMPTY': '@none@', 'DIV_TAG_X': 'y' }") == ({"DIV_TAG_EMPTY": "@none@"}, ["DIV_TAG_X"])


@needs_div
async def test_translate_a_template_between_dialects(tmp_path):
    (tmp_path / "erb.dialect").write_text(json.dumps(ERB))
    (tmp_path / "views").mkdir()
    (tmp_path / "mustache.dialect").write_text('{"DIV_TAG_REPLACEMENT_PREFIX": "{{", "DIV_TAG_REPLACEMENT_SUFFIX": "}}"}')
    page = tmp_path / "views" / "page.tpl"
    page.write_text("@_DIALECT = ../erb.dialect\nHi <%$name%>\n[$items]<li><%$value%></li>[/$items]\n")
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("alt+t", "t")  # Tools > Translate a template
        await settle(pilot)
        dialog = app.screen.dialog
        assert isinstance(dialog, TranslateDialog)
        await until(pilot, lambda: dialog.text is not None)
        # the active template, and the dialect its @_DIALECT names (resolved by Div)
        assert dialog.fields() == ("views/page.tpl", "erb.dialect", "")
        assert "@_DIALECT = ../erb.dialect" in str(dialog.source_note.render())
        assert "Hi {$name}" in dialog.text and "@_DIALECT" not in dialog.text  # to Div's default
        dialog.target_input.data = "mustache.dialect"
        await pilot.click("#preview")
        await until(pilot, lambda: "{{$name}}" in (dialog.text or ""))
        assert dialog.text.startswith("@_DIALECT = ../mustache.dialect\n")
        assert dialog.preview.dialect["DIV_TAG_REPLACEMENT_PREFIX"] == "{{"
        await pilot.click("#save")
        await settle(pilot)
        await pilot.press("enter")  # the proposed name: page.mustache.tpl
        await settle(pilot)
        out = tmp_path / "views" / "page.mustache.tpl"
        assert out.read_text() == "@_DIALECT = ../mustache.dialect\nHi {{$name}}\n[$items]<li>{{$value}}</li>[/$items]\n"
        opened = app.active_editor()
        assert opened.path == out.resolve() and opened.editor.dialect.name == "mustache"
        assert page.read_text().startswith("@_DIALECT = ../erb.dialect")  # the original is untouched


@needs_div
async def test_dialector_imports_php_defines(tmp_path):
    (tmp_path / "x.dialect").write_text("{}")
    (tmp_path / "old.php").write_text("<?php define('DIV_TAG_EMPTY', '@none@'); define('DIV_TAG_ELSE', '@or@');")
    app = Divide(tmp_path, [tmp_path / "x.dialect"])
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        await pilot.press("alt+t", "d")
        await settle(pilot)
        win = app.active_window()
        await pilot.press("alt+f10", "i")
        await settle(pilot)
        app.screen.dialog.input.data = "old.php"
        await pilot.click("#ok")
        await settle(pilot)
        assert "Take 2 tags from old.php" in app.screen.dialog._text
        await pilot.press("y")
        await settle(pilot)
        assert json.loads(win.source.editor.text) == {"DIV_TAG_EMPTY": "@none@", "DIV_TAG_ELSE": "@or@"}


@needs_div
async def test_translate_suggests_the_default_dialect_and_respects_a_choice(tmp_path):
    (tmp_path / "erb.dialect").write_text(json.dumps(ERB))
    plain = tmp_path / "plain.tpl"
    plain.write_text("Hi {$name}\n")
    erb = tmp_path / "erb.tpl"
    erb.write_text("Hi <%$name%>\n")  # in ERB, but it does not say so
    app = Divide(tmp_path, [plain])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("alt+t", "t")
        await settle(pilot)
        dialog = app.screen.dialog
        await until(pilot, lambda: dialog.text is not None)
        assert dialog.fields()[1] == "" and "Div's default" in str(dialog.source_note.render())
        dialog.template_input.data = ""
        await pilot.click(dialog.template_input)
        await pilot.press(*"erb.tpl")  # another template: suggested again (no @_DIALECT: default)
        await settle(pilot)
        await until(pilot, lambda: dialog._last[0] == "erb.tpl" and "Div's default" in str(dialog.source_note.render()))
        await pilot.click(dialog.source_input)
        await pilot.press(*"erb.dialect")  # the user knows better
        await settle(pilot)
        assert dialog.fields()[:2] == ("erb.tpl", "erb.dialect"), dialog.fields()
        assert "Your choice" in str(dialog.source_note.render())
        await pilot.press("enter")  # Preview
        await until(pilot, lambda: "Hi {$name}" in (dialog.text or "") and dialog._asked and dialog._asked[0] == "erb.tpl")
        assert dialog.fields()[1] == "erb.dialect"


async def test_div_tags_in_texts_are_not_markup(tmp_path):
    # "[/]" and "[/$x]" are Div tags, not Textual markup: shown as they are
    (tmp_path / "x.dialect").write_text('{"DIV_TAG_EMPTY": "[/$none]"}')
    app = Divide(tmp_path, [tmp_path / "x.dialect"])
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        await pilot.press("alt+t", "d")
        await settle(pilot)
        for _ in range(4):
            await pilot.press("down")
        await pilot.press("enter")  # Loops and iterations: its defaults include [/]
        await settle(pilot)
        assert isinstance(app.screen.dialog, SectionDialog)
        assert any("default: [/]" in str(w.render()) for w in app.screen.dialog.query(".tr-default"))


@needs_div
async def test_translate_browse_puts_absolute_paths(tmp_path):
    (tmp_path / "dialects").mkdir()
    (tmp_path / "dialects" / "erb.dialect").write_text(json.dumps(ERB))
    page = tmp_path / "page.tpl"
    page.write_text("Hi {$name}\n")
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("alt+t", "t")
        await settle(pilot)
        dialog = app.screen.dialog
        await until(pilot, lambda: dialog.text is not None)
        await pilot.click("#browse-2")  # the target dialect's "..."
        await settle(pilot)
        chooser = app.screen.dialog
        assert chooser.title == "Target dialect" and chooser.pattern == "*.dialect"
        chooser.input.data = "dialects/erb.dialect"
        await pilot.click("#ok")
        await settle(pilot)
        assert app.screen.dialog is dialog
        chosen = (tmp_path / "dialects" / "erb.dialect").resolve()
        assert dialog.target_input.data == str(chosen)  # absolute; the user may shorten it
        await until(pilot, lambda: "<%$name%>" in (dialog.text or ""))
        assert dialog.text.startswith("@_DIALECT = dialects/erb.dialect\n")


async def test_new_dialect_name_can_be_browsed(tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "old.dialect").write_text('{"DIV_TAG_EMPTY": "@none@"}')
    app = Divide(tmp_path, [])
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        await pilot.press("alt+t", "d")
        await settle(pilot)
        await pilot.click("#browse")
        await settle(pilot)
        chooser = app.screen.dialog
        assert chooser.pattern == "*.dialect"
        chooser.input.data = "d/old.dialect"
        await pilot.click("#ok")
        await settle(pilot)
        name = app.screen.dialog
        assert name.input.data == str((tmp_path / "d" / "old.dialect").resolve())
        await pilot.click("#ok")
        await settle(pilot)
        win = app.active_window()
        assert isinstance(win, DialectorWindow) and win.tags["DIV_TAG_EMPTY"] == "@none@"


@needs_div
async def test_editor_dialect_is_the_one_div_loads(tmp_path):
    # single quotes and unquoted keys: decoded by Div's jsonDecode()
    (tmp_path / "erb.dialect").write_text("{ 'DIV_TAG_REPLACEMENT_PREFIX': '<%', DIV_TAG_REPLACEMENT_SUFFIX: '%>' }")
    (tmp_path / "views").mkdir()
    (tmp_path / "views" / "bad.dialect").write_text('{"DIV_TAG_EMPTY": ')
    page = tmp_path / "views" / "page.tpl"
    page.write_text("@_DIALECT = ../erb.dialect\nHi <%$name%>\n")
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        ed = app.window_for(page.resolve()).editor
        await until(pilot, lambda: "../erb.dialect" in ed.engine_dialects)
        assert ed.dialect.source == (tmp_path / "erb.dialect").resolve()
        assert ed.dialect["DIV_TAG_REPLACEMENT_SUFFIX"] == "%>" and not ed.diagnostics

        ed.load_text("@_DIALECT = nope.dialect\nHi\n")
        await until(pilot, lambda: "nope.dialect" in ed.engine_dialects)
        await settle(pilot)
        assert [d.message for d in ed.diagnostics] == ["dialect: Div cannot find the dialect file nope.dialect"]

        ed.load_text("@_DIALECT = bad.dialect\nHi\n")  # relative to the template, as Div looks
        await until(pilot, lambda: "bad.dialect" in ed.engine_dialects)
        await settle(pilot)
        assert [d.message for d in ed.diagnostics] == ["dialect: Div cannot decode it as a JSON object: views/bad.dialect"]


async def test_editor_dialect_without_div_only_colours(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_ENGINE, str(tmp_path / "missing.php"))
    (tmp_path / "erb.dialect").write_text(json.dumps(ERB))
    page = tmp_path / "page.tpl"
    page.write_text("@_DIALECT = erb.dialect\n@_X = 1\nHi <%$name%>\n")
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        ed = app.window_for(page.resolve()).editor
        assert ed.dialect["DIV_TAG_REPLACEMENT_PREFIX"] == "<%"  # divide's guess, to colour
        ed.load_text("@_DIALECT = nope.dialect\nHi\n")
        await settle(pilot)
        assert not ed.engine_dialects and not ed.diagnostics  # not found? only Div can say
