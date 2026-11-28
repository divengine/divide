"""The project window unfolds a file into its members (its outline), like Eclipse."""

import time
from collections import deque
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
def isolated_config(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("config")))  # not in the project: divide writes there


async def settle(pilot, n=10):
    for _ in range(n):
        await pilot.pause()


async def until(pilot, check, tries=100, state=None):
    for _ in range(tries):
        if check():
            return
        await pilot.pause(0.05)
    raise AssertionError("timed out" + (f"\n{state()}" if state is not None else ""))


def trace_tree(monkeypatch) -> deque:
    """The project tree's work, in the order it ran (the last 80 steps, timed): its reloads, the folders
    read again after a change outside divide, every fill of a file's members (and whether that node was
    still in the tree) and the expansions handled. Shown only when the test fails (#16)."""
    from divide.ui.windows import ProjectTree
    log: deque = deque(maxlen=80)
    start = time.monotonic()

    def note(what: str) -> None:
        log.append(f"{time.monotonic() - start:7.3f} {what}")

    def name(node) -> str:
        data = node.data
        if isinstance(data, MemberEntry) and data.member is not None:
            return f"{data.path.name}:{data.member.text}"
        return data.path.name if data is not None else "?"

    reload_, refresh, fill, expanded = (ProjectTree._reload, ProjectTree._refresh_folders, ProjectTree.fill_members,
                                        ProjectTree._on_tree_node_expanded)

    async def _reload(self, node):
        note(f"reload {name(node)} start (lock {'held' if self.lock.is_locked else 'free'})")
        try:
            await reload_(self, node)
        finally:
            note(f"reload {name(node)} end")

    async def _refresh_folders(self, folders):
        note(f"watch: read again {sorted(Path(f).name for f in folders)}")
        await refresh(self, folders)
        note("watch: done")

    def fill_members(self, node):
        note(f"fill {name(node)} (in the tree: {self._tree_nodes.get(node.id) is node}, "
             f"{len(node.children)} children before)")
        fill(self, node)

    async def on_expanded(self, event):
        note(f"expanded {name(event.node)} (in the tree: {self._tree_nodes.get(event.node.id) is event.node})")
        await expanded(self, event)

    monkeypatch.setattr(ProjectTree, "_reload", _reload)
    monkeypatch.setattr(ProjectTree, "_refresh_folders", _refresh_folders)
    monkeypatch.setattr(ProjectTree, "fill_members", fill_members)
    monkeypatch.setattr(ProjectTree, "_on_tree_node_expanded", on_expanded)
    return log


def tree_state(tree, log) -> str:
    """Every row with its kind, whether it is unfolded and whether its node is in the tree, then the log."""
    rows = []
    stack = [(c, 0) for c in reversed(tree.root.children)]
    while stack:
        node, depth = stack.pop()
        data = node.data
        text = data.member.text if isinstance(data, MemberEntry) else node.label.plain
        rows.append(f"{'  ' * depth}{text} [{type(data).__name__}, {'open' if node.is_expanded else 'folded'}, "
                    f"{len(node.children)} children{'' if tree._tree_nodes.get(node.id) is node else ', NOT IN THE TREE'}]")
        stack.extend((c, depth + 1) for c in reversed(node.children))
    return ("the tree now:\n  " + "\n  ".join(rows) + f"\nlock {'held' if tree.lock.is_locked else 'free'}"
            + "\nwhat it did:\n  " + "\n  ".join(log))


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
    (root / "cart.php").write_text(CART, encoding="utf-8")
    (root / "notes.txt").write_text("plain\n", encoding="utf-8")
    (root / "README.md").write_text("# Shop\n\n## Install\n", encoding="utf-8")
    return root.resolve()


async def test_a_file_unfolds_into_its_members_and_enter_goes_there(tmp_path, monkeypatch):
    root = project(tmp_path)
    log = trace_tree(monkeypatch)
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
        # unfolded again once read (the save's own notice may reload the folder meanwhile, later on macOS)
        await until(pilot, lambda: "    + add(string $name): self" in labels(tree.root), tries=200,
                    state=lambda: tree_state(tree, log))
        cart = next(c for c in tree.root.children if c.label.plain == "cart.php")

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
