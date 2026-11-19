"""The Welcome window: what divide shows when it starts with nothing to open.

Three groups in a tree with its filter, as the Git windows have: Start (a new file, open a file, open a
folder, the help), the folders opened lately and the files opened lately. Enter does it; Del takes a
recent one off its list. Help > Welcome shows it again.
"""

from __future__ import annotations

from pathlib import Path

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static, Tree

from divide import __version__, recent, themes
from divide.i18n import _
from divide.ui.dialogs import shown_path
from divide.ui.filter import Filtered
from divide.ui.git import AREA, HASH, PATH, WHEN, GitTree, Row, _paint
from divide.ui.windows import EditorView, HRule, _TVWindow

# What a Start row does (the app does it): new, file, folder, help
START = (
    ("new", lambda: _('New file'), ""),
    ("file", lambda: _('Open a file...'), "F3"),
    ("folder", lambda: _('Open a folder...'), ""),
    ("help", lambda: _('Help'), "F1"),
)


class WelcomeWindow(_TVWindow):
    """Start, the recent folders and the recent files."""

    HINT = _('Enter open · Del forget a recent one · type to filter')
    BINDINGS = [Binding("delete", "forget", show=False)]
    DEFAULT_CSS = """
    WelcomeWindow .welcome-head { height: 3; padding: 0 1; }
    WelcomeWindow .welcome-list { height: 1fr; }
    WelcomeWindow .welcome-info { height: 2; padding: 0 1; }
    """

    def __init__(self, number: int = 0) -> None:
        super().__init__(_('Welcome'), number=number)
        self.git_tree = GitTree(self, "welcome")
        self.head = Static("", classes="welcome-head")
        self.info = Static("", classes="welcome-info", markup=False)
        self.palette_view = EditorView("", read_only=True)  # only lends its colours

    def compose_content(self) -> ComposeResult:
        with Vertical():
            yield self.head
            with Vertical(classes="welcome-list"):
                yield Filtered(self.git_tree)
            yield HRule()
            yield self.info

    def on_mount(self) -> None:
        super().on_mount()
        self.call_after_refresh(self.paint)
        self.call_after_refresh(self.reload)
        self.call_after_refresh(self.git_tree.focus)
        self.app.theme_changed_signal.subscribe(self, lambda _theme: self.call_after_refresh(self.paint))

    def paint(self) -> None:
        _paint(self, self.head, self.info, *self.query(".welcome-list"))
        palette = themes.current()
        self.head.update(Text.assemble(
            (f"divide {__version__}", Style(color=palette.hex(HASH), bold=True)), "\n",
            (_('Terminal IDE for the Divengine projects'), Style(color=palette.hex(PATH))), "\n",
            (_('Open a folder to work on a project, or a file on its own.'), Style(color=palette.hex(WHEN)))))
        self.git_tree.repaint()

    def reload(self) -> None:
        tree = self.git_tree
        keep = self.row.key if self.row is not None else None
        tree.clear()
        start = tree.root.add(_('Start'), Row("group", "start"), expand=True)
        for key, title, _keys in START:
            start.add_leaf(title(), Row("start", f"start:{key}", key))
        for kind, title, empty in (("folders", _('Recent folders'), _('No folder opened yet')),
                                   ("files", _('Recent files'), _('No file opened yet'))):
            paths = recent.entries(kind)
            group = tree.root.add(f"{title}  {len(paths)}", Row("group", kind), expand=True)
            for path in paths:
                group.add_leaf(path.name or str(path), Row(kind[:-1], f"{kind}:{path}", path))
            if not paths:
                group.add_leaf(empty, Row("none", f"none:{kind}"))
        if not tree.put_bar(keep):
            tree.put_bar("start:folder")

    @property
    def row(self) -> Row | None:
        node = self.git_tree.cursor_node
        return node.data if node is not None else None

    def label_of(self, row: Row) -> Text:
        palette = themes.current()
        if row.kind == "start":
            keys = next(k for key, _t, k in START if key == row.item)
            title = next(t() for key, t, _k in START if key == row.item)
            return Text.assemble((title, Style(color=palette.hex(PATH))),
                                 (f"  {keys}" if keys else "", Style(color=palette.hex(WHEN))))
        path: Path = row.item  # type: ignore[assignment]
        return Text.assemble((path.name or str(path), Style(color=palette.hex(PATH))),
                             (f"  {shown_path(path.parent)}", Style(color=palette.hex(WHEN))))

    def filter_text_of(self, node) -> str:
        row: Row | None = node.data
        if row is not None and row.kind in ("folder", "file"):
            return str(row.item)
        return str(node.label)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        event.stop()
        row = event.node.data
        if row is not None and row.kind in ("folder", "file"):
            self.info.update(shown_path(row.item))
        elif row is not None and row.kind == "group" and row.key == "start":
            self.info.update(_('divide works on one folder at a time, its project; files can be opened on their own.'))
        else:
            self.info.update("")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        event.stop()
        row = event.node.data
        if row is None or row.kind == "none":
            return
        if row.kind == "group":
            event.node.toggle()
        else:
            self.app.welcome_chosen(row.kind, row.item)  # type: ignore[attr-defined]

    def on_tree_node_collapsed(self, event: Tree.NodeCollapsed) -> None:
        event.stop()

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        event.stop()

    def action_forget(self) -> None:
        row = self.row
        if row is not None and row.kind in ("folder", "file"):
            recent.forget(row.kind + "s", row.item)
            self.reload()
