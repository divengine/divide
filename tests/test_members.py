"""The project window unfolds a file into its members (its outline), like Eclipse."""

from pathlib import Path

import pytest

from divide.app import Divide
from divide.ui.windows import FileEntry, MemberEntry

CART = """<?php
class Cart
{
    private array $items = [];
    public function add(string $name): self { return $this; }
}
function total(): float { return 0; }
"""


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


async def settle(pilot, n=10):
    for _ in range(n):
        await pilot.pause()


async def until(pilot, check, tries=100):
    for _ in range(tries):
        if check():
            return
        await pilot.pause(0.05)
    raise AssertionError("timed out")


def labels(node, depth=0) -> list[str]:
    out = []
    for child in node.children:
        data = child.data
        text = data.member.text if isinstance(data, MemberEntry) else child.label.plain
        out.append("  " * depth + text)
        if child.is_expanded:
            out += labels(child, depth + 1)
    return out


def project(tmp_path: Path) -> Path:
    root = tmp_path / "shop"
    root.mkdir()
    (root / "cart.php").write_text(CART)
    (root / "notes.txt").write_text("plain\n")
    (root / "README.md").write_text("# Shop\n\n## Install\n")
    return root.resolve()


async def test_a_file_unfolds_into_its_members_and_enter_goes_there(tmp_path):
    root = project(tmp_path)
    app = Divide(root, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        tree = app.project_window().project_tree
        await until(pilot, lambda: len(tree.root.children) == 3)
        by_name = {c.label.plain: c for c in tree.root.children}
        cart = by_name["cart.php"]
        assert isinstance(cart.data, FileEntry) and cart.allow_expand  # PHP has members
        assert not by_name["notes.txt"].allow_expand  # plain text has none
        assert not cart.is_expanded and not cart.children  # read only when unfolded

        # → (or a click on ►) unfolds it into its members, a class into its own
        tree.move_cursor(cart)
        await pilot.press("right")
        await settle(pilot)
        assert labels(tree.root) == ["cart.php", "  Cart", "  total(): float", "notes.txt", "README.md"]
        cart.children[0].expand()
        await settle(pilot)
        assert labels(tree.root)[:5] == ["cart.php", "  Cart", "    - $items: array",
                                         "    + add(string $name): self", "  total(): float"]
        assert not app.editor_windows()  # unfolding does not open the file

        # Enter on a member: the file opens with the member selected
        add = next(c for c in cart.children[0].children if c.data.member.text.startswith("+ add"))
        tree.move_cursor(add)
        await pilot.press("enter")
        await settle(pilot)
        editor = app.active_editor()
        assert editor is not None and editor.path == root / "cart.php" and editor.editor.selected_text == "add"

        # the file saved with a new function: the unfolded file shows it
        editor.editor.insert("function extra() {}\n", (1, 0))
        await pilot.press("f2")
        await settle(pilot)
        assert any(c.data.member.text == "extra()" for c in cart.children)

        # Ctrl+R reloads the project window: the file and its class stay unfolded
        app.raise_window(app.project_window())
        tree.focus()
        await tree.reload()
        await settle(pilot)
        cart = next(c for c in tree.root.children if c.label.plain == "cart.php")
        assert "    + add(string $name): self" in labels(tree.root)

        # Del on a member deletes nothing
        app.raise_window(app.project_window())
        tree.focus()
        tree.move_cursor(cart.children[0])
        await pilot.press("delete")
        await settle(pilot)
        assert (root / "cart.php").exists()


async def test_enter_on_a_file_that_unfolds_opens_it(tmp_path):
    root = project(tmp_path)
    app = Divide(root, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        tree = app.project_window().project_tree
        await until(pilot, lambda: len(tree.root.children) == 3)
        readme = next(c for c in tree.root.children if c.label.plain == "README.md")
        tree.move_cursor(readme)
        await pilot.press("enter")
        await settle(pilot)
        assert [w.path for w in app.editor_windows()] == [root / "README.md"]
        assert not readme.is_expanded  # it opens, it does not unfold
