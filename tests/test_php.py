import shutil
from pathlib import Path

import pytest

from divide import lang
from divide.app import Divide
from divide.lang import php
from divide.ui.windows import MessagesWindow

needs_php = pytest.mark.skipif(shutil.which("php") is None, reason="php not in PATH")

SRC = """<?php
namespace App;

class Page {
    public function show(string $name): string {
        return new \\divengine\\div('page.tpl', ['name' => $name]);
    }
}
"""


async def settle(pilot, n=8):
    for _ in range(n):
        await pilot.pause()


def test_languages():
    assert lang.language_of(Path("a.php")) == "php" and lang.language_of(Path("a.PHTML")) == "php"
    assert lang.language_of(Path("a.tpl")) == "div" and lang.language_of(Path("a.dialect")) == "json"
    assert lang.language_of(Path("a.txt")) is None and lang.language_of(None) == "div"
    assert lang.language("php").help_topic == "Editing-PHP" and lang.language("php").checked


def test_lint_output_is_read():
    text = "<?php\necho 1;\n  function f( {\n"
    out = 'PHP Parse error:  syntax error, unexpected token "{", expecting variable in Standard input code on line 3\n'
    [d] = php.parse_lint(out, text)
    assert d.severity == "error" and text[d.start:d.end] == "function f( {"
    assert d.message.startswith("syntax error, unexpected token")


@needs_php
async def test_lint_asks_php():
    assert await php.lint(SRC) == []
    [d] = await php.lint(SRC + "function f( {\n")
    assert d.severity == "error" and "unexpected" in d.message


@needs_php
async def test_php_editor(tmp_path: Path):
    (tmp_path / "Page.php").write_text(SRC)
    (tmp_path / "page.tpl").write_text("Hello {$name}\n")
    app = Divide(tmp_path, [tmp_path / "Page.php"])
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        win = app.active_editor()
        ed = win.editor
        assert ed.lang == "php" and ed.language == "php" and ed.checked
        names = {name for row in ed._highlights.values() for *_, name in row}
        assert {"php.tag", "php.keyword", "php.variable", "php.string", "php.type.builtin"} <= names

        # a syntax error: PHP finds it, the editor paints it, the Messages window lists it
        ed.move_cursor((7, 1))
        ed.insert("\nfunction broken( {\n")
        for _ in range(40):
            await pilot.pause(0.05)
            if ed.diagnostics:
                break
        assert [d.severity for d in ed.diagnostics] == ["error"]
        assert any(name == "diag.error" for row in ed._highlights.values() for *_, name in row)
        await pilot.press("alt+f9")
        await settle(pilot)
        messages = app.messages_window()
        assert isinstance(messages, MessagesWindow)
        assert any("Page.php(9,1): Error: syntax error" in item.text for item in messages.items)

        # fixed: the error goes
        ed.undo()
        for _ in range(40):
            await pilot.pause(0.05)
            if not ed.diagnostics:
                break
        assert ed.diagnostics == []

        # F1: the PHP editor's topic
        app.raise_window(win)
        await settle(pilot)
        await pilot.press("f1")
        await settle(pilot)
        assert app.help_window().view.name_ == "divide:Editing-PHP"
        await pilot.press("escape")
        await settle(pilot)

        # Ctrl+Enter on a string with a file name opens it
        app.raise_window(win)
        ed.move_cursor((5, 40))
        await pilot.press("ctrl+enter")
        await settle(pilot)
        assert app.active_editor().path == tmp_path / "page.tpl"
