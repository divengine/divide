"""Search > Outline: the parts of the active file as a tree, to jump to.

A window at the right of the desktop shows what the file is made of (see
``divide.outline``): for PHP its namespaces, classes and their members (UML's
marks: + public, # protected, - private) and functions; for a Div template its
constructs, each one below the block that holds it; and so on for every
language divide colours. Each row has an icon (a letter, coloured by kind) and
its label in the editor's colours. ► / ▼ fold and unfold (Space, ← →, a
click on them); Enter or a double click goes there. The tree follows the
active editor and its edits, keeping what was folded and where the bar was.
"""

from __future__ import annotations

from divide.i18n import _

from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Tree
from textual.widgets.tree import TreeNode
from textual_vision.constants import OptionFlag
from textual_vision.group import TVViewMixin

from divide import outline as outline_mod
from divide import themes
from divide.outline import Node
from divide.ui.runner import _ListWindow
from divide.ui.windows import EditorWindow, LocationsWindow, ProjectWindow, _TVWindow

WIDTH = 36
NO_OUTLINE = _('(no outline for this kind of file)')
HINTS = {
    "php": _('Enter go to the declaration · Space fold · + public  # protected  - private'),
    "div": _('Enter go to the tag · Space fold · below a block, what it holds'),
}
HINT = _('Enter go there · Space fold · Left Right fold, unfold')


def _path(node: TreeNode) -> tuple[str, ...]:
    keys = []
    while node is not None and node.data is not None:
        keys.append(node.data.key)
        node = node.parent
    return tuple(reversed(keys))


class OutlineTree(Tree[Node], TVViewMixin):
    """The outline's rows: a letter for the kind, the label in the editor's colours."""

    ICON_NODE = "► "  # Turbo Vision's own (CP437), like the project window's
    ICON_NODE_EXPANDED = "▼ "
    BINDINGS = [
        Binding("right", "unfold", "Unfold", show=False),
        Binding("left", "fold", "Fold", show=False),
    ]
    DEFAULT_CSS = """
    OutlineTree {
        background: $divide-editor-bg;
        color: $divide-editor-text;
        scrollbar-size: 0 0;
        padding: 0;
    }
    OutlineTree > .tree--guides, OutlineTree > .tree--guides-hover, OutlineTree > .tree--guides-selected {
        color: $divide-editor-gutter;
    }
    OutlineTree > .tree--cursor, OutlineTree:focus > .tree--cursor {
        color: $divide-editor-selection; background: $divide-editor-selection-bg; text-style: none;
    }
    OutlineTree > .tree--highlight, OutlineTree > .tree--highlight-line { background: $divide-editor-bg; }
    """

    def __init__(self) -> None:
        super().__init__("outline")
        self.show_root = False
        self.auto_expand = False  # Enter goes to the node; Space and the arrows fold
        self.guide_depth = 2
        self.tv_options = OptionFlag.SELECTABLE

    def on_mount(self) -> None:
        self.app.theme_changed_signal.subscribe(self, lambda _theme: self.repaint())

    def repaint(self) -> None:
        self._invalidate()
        self.refresh()

    def render_label(self, node, base_style, style):
        if node.data is None:  # a note: (no declarations)
            return Text.assemble(("  ", base_style), (str(node.label), base_style + style))
        label = outline_mod.rich_label(node.data, themes.current())
        if self.cursor_node is node:
            label.stylize(style)  # the bar: one colour from end to end
        if node.allow_expand:
            prefix = (self.ICON_NODE_EXPANDED if node.is_expanded else self.ICON_NODE, base_style)
        else:
            prefix = ("  ", base_style)
        return Text.assemble(prefix, label)

    def action_unfold(self) -> None:
        node = self.cursor_node
        if node is not None and node.allow_expand:
            if node.is_expanded and node.children:
                self.move_cursor(node.children[0])
            else:
                node.expand()

    def action_fold(self) -> None:
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand and node.is_expanded:
            node.collapse()
        elif node.parent is not None and node.parent is not self.root:
            self.move_cursor(node.parent)

    async def _on_click(self, event: events.Click) -> None:
        # a click puts the bar on a row, a double click goes there; ► ▼ fold
        meta = event.style.meta
        if event.button == 1 and "line" in meta and not meta.get("toggle", False):
            event.prevent_default()
            self.cursor_line = meta["line"]
            if event.chain >= 2:
                self.action_select_cursor()


class OutlineWindow(_TVWindow):
    """The parts of ``source``; Enter goes to the one under the bar."""

    def __init__(self, number: int = 0) -> None:
        super().__init__(_('Outline'), number=number)
        self.outline_tree = OutlineTree()
        self.source: EditorWindow | None = None
        self.nodes: list[Node] = []
        self.text: str | None = None  # the source's text the tree was made from
        self.hint = HINT
        self.folded: set[tuple[str, ...]] = set()  # the paths of the nodes folded, kept across edits

    def compose_content(self) -> ComposeResult:
        yield self.outline_tree

    # ------------------------------------------------------------ the rows
    @property
    def rows(self) -> list[tuple[int, Node | None]]:
        """The rows shown, top to bottom: (depth, node); a note has no node."""
        out = []
        for line in self.outline_tree._tree_lines:
            out.append((len(line.path) - 1, line.path[-1].data))
        return out

    @property
    def lines(self) -> list[str]:
        """The rows as plain text: ``  m add(...)`` (for tests and the status line)."""
        out = []
        for line in self.outline_tree._tree_lines:
            node = line.path[-1]
            depth = len(line.path) - 1
            text = outline_mod.rich_label(node.data, plain=True).plain if node.data is not None else str(node.label)
            out.append("  " * depth + text)
        return out

    def focus_row(self, index: int) -> None:
        tree = self.outline_tree
        tree.cursor_line = index
        tree.scroll_to_line(tree.cursor_line, animate=False)

    # ------------------------------------------------------------ loading
    def load(self, source: EditorWindow | None) -> None:
        keep = _path(self.outline_tree.cursor_node) if self.outline_tree.cursor_node is not None else ()
        keep_line = self.outline_tree.cursor_line
        self.source = source
        editor = source.editor if source is not None else None
        self.text = editor.text if editor is not None else None
        lang = editor.lang if editor is not None else None
        nodes = None
        if editor is not None:
            context = {"tokens": editor.tokens, "blocks": editor.div_blocks()} if lang == "div" else {}
            nodes = outline_mod.outline(lang, editor.text, **context)
        self.hint = HINTS.get(lang or "", HINT)
        name = source.path.name if source is not None and source.path is not None else ""
        self.title = _('Outline: {name}').format(name=name) if name else _('Outline')
        self.nodes = nodes or []
        tree = self.outline_tree
        tree.clear()
        if nodes is None:
            tree.root.add_leaf(NO_OUTLINE if editor is None or lang not in outline_mod.languages()
                               else _('(no grammar for this language: pip install its tree-sitter package)'))
        elif not nodes:
            tree.root.add_leaf(_('(nothing to list)'))
        else:
            self._add(tree.root, nodes, ())
        tree._tree_lines  # noqa: B018 - the lines are rebuilt lazily: node.line is -1 until then
        found = self._find(keep) if keep else None
        if found is not None:
            tree.move_cursor(found, animate=False)
        else:
            tree.cursor_line = min(max(keep_line, 0), max(tree.last_line, 0))
        tree.call_after_refresh(tree.scroll_to_line, tree.cursor_line, animate=False)

    def _add(self, parent: TreeNode, nodes: list[Node], path: tuple[str, ...]) -> None:
        for node in nodes:
            here = path + (node.key,)
            if node.children:
                branch = parent.add(node.text, node, expand=here not in self.folded)
                self._add(branch, node.children, here)
            else:
                parent.add_leaf(node.text, node)

    def _find(self, path: tuple[str, ...]) -> TreeNode | None:
        """The node at ``path``, or the deepest one shown on the way to it."""
        node = self.outline_tree.root
        for key in path:
            if node is not self.outline_tree.root and not node.is_expanded:
                break
            child = next((c for c in node.children if c.data is not None and c.data.key == key), None)
            if child is None:
                break
            node = child
        return None if node is self.outline_tree.root else node

    def on_tree_node_collapsed(self, event: Tree.NodeCollapsed) -> None:
        self.folded.add(_path(event.node))

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        self.folded.discard(_path(event.node))

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        event.stop()
        node = event.node.data
        if self.source is not None and node is not None:
            self.app._select_in(self.source, node.start, node.end)  # type: ignore[attr-defined]

    def go(self) -> None:
        """Enter: to the node under the bar."""
        self.outline_tree.action_select_cursor()


class OutlineMixin:
    """Search > Outline (mixed into the Divide app)."""

    def outline_window(self) -> OutlineWindow | None:
        return next((w for w in self.windows() if isinstance(w, OutlineWindow)), None)

    def show_outline(self) -> None:
        window = self.outline_window()
        if window is None:
            window = OutlineWindow(number=self._free_number())
            self._right_window(window)
        window.load(self.active_editor() or self._outline_editor())
        self.raise_window(window)
        window.outline_tree.focus()

    def _outline_editor(self) -> EditorWindow | None:
        """The editor on top of the others with an outline (the outline is opened from a non-editor)."""
        langs = outline_mod.languages()
        return next((w for w in reversed(self.windows()) if isinstance(w, EditorWindow) and w.editor.lang in langs), None)

    def _right_window(self, window: OutlineWindow) -> None:
        """Along the right edge; the windows under it end where it starts."""
        width = self.desktop.size.width or 80
        left = max(20, width - WIDTH)
        window.styles.width = width - left
        window.styles.height = "100%"
        window.styles.offset = (left, 0)
        for other in self.windows():
            if other.zoomed or isinstance(other, (_ListWindow, ProjectWindow, LocationsWindow, OutlineWindow)):
                continue
            x = int(other.styles.offset.x.value) if other.styles.offset.x else 0
            if x < left and x + (other.size.width or width) > left and left - x >= 20:
                other.styles.width = left - x
        self.insert_window(window)

    def follow_outline(self, editor: EditorWindow | None = None) -> None:
        """The active editor changed, or its text did: the outline follows."""
        window = self.outline_window()
        if window is None:
            return
        editor = editor or self.active_editor()
        if editor is None or editor.editor.lang not in outline_mod.languages():
            return
        if editor is not window.source or window.text != editor.editor.text:
            window.load(editor)
