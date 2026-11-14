"""Search > Outline: the declarations of a PHP file, and Ctrl+A."""

from divide.app import Divide
from divide.lang.php import outline
from divide.ui.outline import NO_OUTLINE, OutlineWindow

import pytest

SOURCE = """<?php
namespace App\\Shop;

const MAX = 3;

interface Priced { function price(): float; }

enum Size: string { case Small = 's'; }

abstract class Cart extends Base implements Priced
{
    const TAX = 0.2;
    private array $items = [];
    protected static function add(string $name, int $qty = 1): self { $f = function () {}; return $this; }
    public function price(): float { return 0; }
}

if (!function_exists('total')) {
    function total(array $items): float { return 0; }
}
$x = new class { function hidden() {} };
"""


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


def test_outline_of_php():
    symbols = outline(SOURCE)
    assert [s.text for s in symbols] == [
        "namespace App\\Shop",
        "const MAX",
        "interface Priced",
        "  + price(): float",
        "enum Size",
        "  case Small",
        "class Cart extends Base",
        "  const TAX",
        "  - $items",
        "  # add(string $name, int $qty = 1): self",
        "  + price(): float",
        "total(array $items): float",
    ]
    assert all(SOURCE[s.start:s.end] == s.name for s in symbols)
    assert outline("<?php\n// ñandú\nfunction ñ() {}\n")[0].start == len("<?php\n// ñandú\nfunction ")


async def settle(pilot, times: int = 6) -> None:
    for _ in range(times):
        await pilot.pause()


async def test_outline_window_follows_and_jumps(tmp_path):
    script = tmp_path / "cart.php"
    script.write_text(SOURCE)
    page = tmp_path / "page.tpl"
    page.write_text("hello\nworld\n")
    app = Divide(tmp_path, [page, script])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        editor = app.active_editor()
        assert editor.path == script
        await pilot.press("ctrl+o")
        await settle(pilot)
        window = app.active_window()
        assert isinstance(window, OutlineWindow) and window.title == "Outline: cart.php"
        assert window.lines[6] == "class Cart extends Base"
        assert int(window.styles.offset.x.value) + window.size.width == app.desktop.size.width

        # Enter goes to the declaration, its name selected
        window.list.focus_item(9)
        await pilot.press("enter")
        await settle(pilot)
        assert app.active_editor() is editor and editor.editor.selected_text == "add"

        # it follows the edits
        editor.editor.insert("function extra() {}\n", (1, 0))
        await settle(pilot)
        app.update_status()
        assert "extra()" in window.lines

        # a template: Ctrl+A selects all; the outline keeps the PHP file's list
        app.raise_window(app.window_for(page))
        await settle(pilot)
        await pilot.press("ctrl+a")
        assert app.active_editor().editor.selected_text == "hello\nworld\n"
        assert window.source is editor

    app = Divide(tmp_path, [page])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+o")
        await settle(pilot)
        assert app.outline_window().lines == [NO_OUTLINE]
