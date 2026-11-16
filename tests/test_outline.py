"""Search > Outline: the parts of a file as a tree, and Ctrl+A."""

from divide.app import Divide
from divide.outline import outline, rich_label, walk
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

TEMPLATE = """@_DIALECT = default
{= title: "Shop" =}
{% layout/header %}
[$products] product =>
  ?$product.offer
    {%% components/card %%}
  $product.offer?
  {?( {$product.price} > 10 )?}<b>dear</b>{/?}
[/$products]
[[cart  {$total}  cart]]
{{side <aside/> side}}
(( side ))
"""


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


def tree(nodes) -> list[str]:
    return ["  " * level + rich_label(node, plain=True).plain for level, node in walk(nodes)]


def test_outline_of_php():
    nodes = outline("php", SOURCE)
    assert tree(nodes) == [
        "n App\\Shop",  # what follows `namespace X;` is the namespace's
        "  k MAX",
        "  I Priced",
        "    m + price(): float",
        "  E Size",
        "    k Small",
        "  C Cart extends Base implements Priced",
        "    k + TAX",
        "    p - $items: array",
        "    m # add(string $name, int $qty = 1): self",
        "    m + price(): float",
        "  f total(array $items): float",
    ]
    assert all(SOURCE[n.start:n.end] in n.text for _, n in walk(nodes))
    assert outline("php", "<?php\n// ñandú\nfunction ñ() {}\n")[0].start == len("<?php\n// ñandú\nfunction ")


def test_labels_take_the_editors_colours():
    nodes = outline("php", SOURCE)
    add = next(n for _, n in walk(nodes) if n.text.startswith("# add"))
    kinds = dict(add.label)
    assert kinds["add"].startswith("php.function") and kinds["string"].startswith("php.type")
    cart = next(n for _, n in walk(nodes) if n.kind == "class")
    assert dict(cart.label)["extends"] == "php.keyword" and cart.label[0] == ("Cart ", "php.type")
    text = rich_label(add)
    assert text.plain == "m # add(string $name, int $qty = 1): self"
    assert {span.style.color for span in text.spans if span.style.color} and len(text.spans) > 4


def test_icons_are_ascii():
    from divide.outline import ICONS, MARK_COLOURS

    assert all(len(letter) == 1 and letter.isascii() and letter.isprintable() for letter, _ in ICONS.values())
    assert all(mark.isascii() for mark in MARK_COLOURS)


def test_outline_of_a_template():
    nodes = outline("div", TEMPLATE)
    assert tree(nodes) == [
        "p @_DIALECT = default",
        'v {= title: "Shop" =}',
        "i {% layout/header %}",
        "l [$products] product =>",
        "  ? ?$product.offer",
        "    i {%% components/card %%}",
        "  ? {?( {$product.price} > 10 )?}",
        "c [[cart",
        "o {{side",
        "o (( side ))",
    ]
    loop = nodes[3]
    assert TEMPLATE[loop.start:loop.end] == "[$products] product =>"
    assert dict(loop.label).get("product") is not None  # coloured by the lexer


async def settle(pilot, times: int = 6) -> None:
    for _ in range(times):
        await pilot.pause()


async def test_outline_window_folds_follows_and_jumps(tmp_path):
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
        assert window.lines[6] == "  C Cart extends Base implements Priced"
        assert int(window.styles.offset.x.value) + window.size.width == app.desktop.size.width

        # Enter goes to the declaration, its name selected
        window.focus_row(9)
        await pilot.press("enter")
        await settle(pilot)
        assert app.active_editor() is editor and editor.editor.selected_text == "add"

        # ← folds the class (from a member: first to the class), → unfolds it
        app.raise_window(window)
        window.focus_row(9)
        await pilot.press("left", "left")
        await settle(pilot)
        assert window.lines[6].startswith("  C Cart") and len(window.lines) == 8
        assert window.outline_tree.cursor_line == 6

        # it follows the edits, keeping the fold and the bar
        app.raise_window(editor)
        editor.editor.insert("function extra() {}\n", (1, 0))
        await settle(pilot)
        app.update_status()
        assert "f extra()" in window.lines and len(window.lines) == 9
        assert window.lines[window.outline_tree.cursor_line].startswith("  C Cart")
        app.raise_window(window)
        await pilot.press("right")
        await settle(pilot)
        assert len(window.lines) == 13

        # a template: Ctrl+A selects all; the outline follows it
        app.raise_window(app.window_for(page))
        await settle(pilot)
        await pilot.press("ctrl+a")
        assert app.active_editor().editor.selected_text == "hello\nworld\n"
        app.update_status()
        assert window.source.path == page and window.lines == ["(nothing to list)"]

    notes = tmp_path / "notes.txt"
    notes.write_text("plain\n")
    app = Divide(tmp_path, [notes])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+o")
        await settle(pilot)
        assert app.outline_window().lines == [NO_OUTLINE]


async def test_outline_window_of_a_template(tmp_path):
    page = tmp_path / "page.tpl"
    page.write_text(TEMPLATE)
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+o")
        await settle(pilot)
        window = app.outline_window()
        assert window.lines[3] == "l [$products] product =>" and "Enter go to the tag" in window.hint
        window.focus_row(5)
        await pilot.press("enter")
        await settle(pilot)
        assert app.active_editor().editor.selected_text == "{%% components/card %%}"
        app.active_editor().editor.insert("{% extra %}\n", (1, 0))
        await settle(pilot)
        app.update_status()
        assert "i {% extra %}" in window.lines
