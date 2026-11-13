import json
import sys
from pathlib import Path

import pytest

from divide import lsp
from divide.app import Divide
from divide.lang.div.complete import CARET
from divide.ui.lsp import completion_result, clean_hover
from lsprotocol import types

FAKE = Path(__file__).with_name("fake_lsp_server.py")

SRC = """<?php
class Shop {
    public function total(): float { return 1.0; }
}
$shop = new Shop();
echo $shop->
"""


async def settle(pilot, n=8):
    for _ in range(n):
        await pilot.pause()


async def until(pilot, pred, tries=200):
    for _ in range(tries):
        if pred():
            return True
        await pilot.pause(0.05)
    return False


def test_positions_count_utf16():
    text = "añ😀b\nx"
    assert lsp.to_position(text, text.index("b")) == (0, 4)  # the emoji is two units
    assert lsp.to_offset(text, 0, 4) == text.index("b")
    assert lsp.to_offset(text, 1, 0) == text.index("x") and lsp.to_offset(text, 9, 0) == len(text)


def test_snippets_become_text():
    assert lsp.from_snippet("total($0)", CARET) == f"total({CARET})"
    assert lsp.from_snippet("f(${1:a}, ${2:b})$0", CARET) == f"f(a, b){CARET}"
    assert lsp.from_snippet("x(\\$y)", CARET) == "x($y)"


def test_completion_filtered_by_what_is_typed():
    items = [types.CompletionItem(label="total", sort_text="2"), types.CompletionItem(label="taxes", sort_text="1"),
             types.CompletionItem(label="name")]
    result = completion_result("$a->t", 5, "t", items)
    assert [c.label for c in result.items] == ["taxes", "total"] and result.start == 4
    assert clean_hover("```php\n<?php class A\n```\n\n\n\nDoc") == "class A\n\nDoc"
    # after a namespace only the name is replaced
    result = completion_result("\\divengine\\d", 12, "d", [types.CompletionItem(label="div"), types.CompletionItem(label="is_url")])
    assert [c.label for c in result.items] == ["div"] and result.start == 11


def test_find_command(tmp_path):
    server = lsp.spec("phpactor")
    assert lsp.find_command(server, tmp_path, [sys.executable, str(FAKE)]) == [sys.executable, str(FAKE)]
    (tmp_path / "vendor" / "bin").mkdir(parents=True)
    (tmp_path / "vendor" / "bin" / "phpactor").write_text("")
    assert lsp.find_command(server, tmp_path) == [str(tmp_path / "vendor/bin/phpactor"), "language-server"]
    assert lsp.find_command(server, tmp_path, ["/nowhere/phpactor"]) is None


@pytest.fixture
def fake_server(tmp_path, monkeypatch):
    home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    (home / "divide").mkdir(parents=True)
    (home / "divide" / "config.json").write_text(json.dumps({
        "lsp": {"php": "phpactor"},
        "lsp_commands": {"phpactor": [sys.executable, str(FAKE)]},
    }))


async def test_language_server_in_the_editor(tmp_path, fake_server):
    project = tmp_path / "p"
    project.mkdir()
    (project / "a.php").write_text(SRC)
    app = Divide(project, [project / "a.php"])
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        win = app.active_editor()
        ed = win.editor
        assert await until(pilot, lambda: app.lsp_session("php") is not None), app.lsp_status("php")
        assert app.lsp_status("php") == "phpactor"

        # the server's diagnostics join PHP's in the editor
        ed.move_cursor((4, 0))
        ed.insert("// BAD\n")
        assert await until(pilot, lambda: any("BAD is not allowed" in d.message for d in ed.diagnostics))
        assert [d.severity for d in ed.diagnostics if "BAD" in d.message] == ["warning"]

        # completion after ->, filtered as you type, snippets with the caret inside
        ed.move_cursor((6, len("echo $shop->")))
        await pilot.press("t")
        assert await until(pilot, lambda: ed.completing)
        assert [c.label for c in ed._popup.items] == ["total", "taxes", "Tpl (Engine)"]
        await pilot.press("o")
        assert await until(pilot, lambda: ed.completing and [c.label for c in ed._popup.items] == ["total"])
        await pilot.press("enter")
        await settle(pilot)
        assert ed.document.get_line(6) == "echo $shop->total()" and ed.cursor_location == (6, len("echo $shop->total("))

        # Ctrl+F1: the server's hover, in a dialog
        ed.move_cursor((5, 14))
        await pilot.press("ctrl+f1")
        assert await until(pilot, lambda: type(app.screen).__name__ == "DialogScreen")
        await pilot.press("enter")
        await settle(pilot)

        # Ctrl+Enter on a symbol: its definition
        ed.move_cursor((5, 14))
        await pilot.press("ctrl+enter")
        assert await until(pilot, lambda: ed.selection.start == (1, 6))
        assert ed.selection.end == (1, 10)

        # a class: inserted by its name, with the `use` line the server sends
        ed.move_cursor((7, 0))
        ed.insert("$t = new ")
        await pilot.press("T", "p")
        assert await until(pilot, lambda: ed.completing and [c.label for c in ed._popup.items] == ["Tpl (Engine)"])
        await pilot.press("enter")
        await settle(pilot)
        assert ed.text.startswith("<?php\n\nuse Engine\\Tpl;\nclass Shop {")  # the edits in the server's order
        assert ed.document.get_line(ed.cursor_location[0]) == "$t = new Tpl" and ed.cursor_location[1] == len("$t = new Tpl")

        await app.lsp_stop_all()


async def test_without_a_server_the_status_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("PATH", "/nonexistent")
    project = tmp_path / "p"
    project.mkdir()
    (project / "a.php").write_text("<?php\n")
    app = Divide(project, [project / "a.php"])
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        assert app.lsp_session("php") is None
        assert "install phpactor or intelephense" in app.lsp_status("php")
