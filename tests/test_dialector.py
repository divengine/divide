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
from divide.ui.dialector import DialectorWindow, SectionDialog, TransformDialog
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
