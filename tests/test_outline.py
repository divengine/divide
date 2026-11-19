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
def isolated_config(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("config")))  # not in the project: divide writes there


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


async def until(pilot, ready, seconds: float = 10.0) -> None:
    """Until ``ready()``: what the app does after a while (a slow machine takes longer)."""
    for _ in range(int(seconds / 0.05)):
        if ready():
            return
        await pilot.pause(0.05)
    raise AssertionError("timed out")


async def test_outline_window_folds_follows_and_jumps(tmp_path):
    script = tmp_path / "cart.php"
    script.write_text(SOURCE, encoding="utf-8")
    page = tmp_path / "page.tpl"
    page.write_text("hello\nworld\n", encoding="utf-8")
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
        app.update_status()
        assert "f extra()" not in window.lines  # not while typing: once the keys stop
        await until(pilot, lambda: "f extra()" in window.lines)
        await settle(pilot)
        assert len(window.lines) == 9
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
    notes.write_text("plain\n", encoding="utf-8")
    app = Divide(tmp_path, [notes])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+o")
        await settle(pilot)
        assert app.outline_window().lines == [NO_OUTLINE]


async def test_outline_window_of_a_template(tmp_path):
    page = tmp_path / "page.tpl"
    page.write_text(TEMPLATE, encoding="utf-8")
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
        app.update_status()
        await until(pilot, lambda: "i {% extra %}" in window.lines)


# ---------------------------------------------------------------- the other languages
def outlined(lang: str, text: str) -> list[str]:
    return tree(outline(lang, text))


def test_outline_of_html():
    assert outlined("html", '<html><body><main id="m" class="page wide"><h1>Hi</h1></main>'
                            '<script src="a.js"></script></body></html>') == [
        "< html", "  < body", "    < main#m.page.wide", "      < h1", "    < script a.js"]


def test_outline_of_xml():
    assert outlined("xml", '<?xml version="1.0"?><phpunit bootstrap="b.php"><testsuites>'
                           '<testsuite name="unit"><directory>tests</directory></testsuite></testsuites></phpunit>') == [
        '< phpunit bootstrap="b.php"', "  < testsuites", '    < testsuite name="unit"', "      < directory"]


def test_outline_of_markdown():
    assert outlined("markdown", "# Title\n\ntext\n\n## One\n\n### Deep\n\n## Two\n") == [
        "# Title", "  # One", "    # Deep", "  # Two"]


def test_outline_of_css():
    assert outlined("css", '@import "x.css";\nbody, .a > p { color: red; }\n'
                           "@media (max-width: 600px) { .card { margin: 0; } }\n") == [
        '@ @import "x.css"', "s body, .a > p", "@ @media (max-width: 600px)", "  s .card"]


def test_outline_of_javascript():
    assert outlined("javascript", 'import x from "y";\nconst A = 1, b = () => 2;\nlet c;\n'
                                  "function f(a, b = 1) {}\n"
                                  "class Cart extends Base { #items = []; add(name, qty = 1) {} }\n"
                                  "export function g() {}\n") == [
        'u import x from "y"', "k A", "f b()", "v c", "f f(a, b = 1)",
        "C Cart extends Base", "  p - #items", "  m + add(name, qty = 1)", "f g()"]


def test_outline_of_sql():
    assert outlined("sql", "CREATE TABLE products (id INT PRIMARY KEY, name VARCHAR(80) NOT NULL);\n"
                           "CREATE VIEW v AS SELECT * FROM products;\nCREATE INDEX idx ON products (name);\n"
                           "SELECT 1;\n") == [
        "t products", "  c id INT", "  c name VARCHAR(80)", "w v", "x idx on products"]


def test_outline_of_shell_and_env():
    assert outlined("shell", "#!/bin/sh\nX=1\nexport Y=2\nfunction a() { echo; }\nb() { :; }\n") == [
        "v X=1", "v Y=2", "f a()", "f b()"]


def test_outline_of_json():
    assert outlined("json", '{"name": "shop", // the shop\n "items": [{"title": "Apple", "price": 1.5}],'
                            ' "tags": ["a", "b"], "cart": {"total": 3}}') == [
        'k "name": "shop"', 'a "items" [1]', '  o [0] "title": "Apple"', '    k "title": "Apple"',
        '    k "price": 1.5', 'a "tags" [2]', 'o "cart"', '  k "total": 3']


def test_outline_of_yaml():
    assert outlined("yaml", "name: shop\nservices:\n  web:\n    image: php\n    ports:\n      - \"80:80\"\n"
                            "list:\n  - a: 1\n") == [
        "k name: shop", "o services", "  o web", "    k image: php", "    a ports [1]",
        "a list [1]", "  o - a: 1", "    k a: 1"]


def test_outline_of_toml():
    assert outlined("toml", 'title = "x"\n[owner]\nname = "T"\n[[products]]\nname = "a"\n') == [
        'k title = "x"', "t [owner]", '  k name = "T"', "a [[products]]", '  k name = "a"']


def test_outline_of_ini_and_csv():
    assert outlined("ini", "; c\n[PHP]\nmemory_limit = 128M\n[xdebug]\nxdebug.mode = debug\n") == [
        "[ [PHP]", "  k memory_limit = 128M", "[ [xdebug]", "  k xdebug.mode = debug"]
    assert outlined("csv", "id,name,price\n1,Apple,1.5\n") == ["c id", "c name", "c price"]


def test_every_language_divide_colours_has_an_outline():
    from divide import lang
    from divide.outline import languages

    coloured = {language.name for language in lang.LANGUAGES}
    assert coloured <= languages() | {"text"}, coloured - languages()


async def test_outline_window_of_markdown(tmp_path):
    notes = tmp_path / "README.md"
    notes.write_text("# Shop\n\n## Install\n\n## Use\n", encoding="utf-8")
    app = Divide(tmp_path, [notes])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+o")
        await settle(pilot)
        window = app.outline_window()
        assert window.lines == ["# Shop", "  # Install", "  # Use"]
        window.focus_row(2)
        await pilot.press("enter")
        await settle(pilot)
        assert app.active_editor().editor.selected_text == "Use"
