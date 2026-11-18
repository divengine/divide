"""The Git menu: what changed, the history, the branches, and git run for them.

``GitMixin`` is part of the app. A project inside a git repository gets:

- **Git > Changes**: the files that changed, in their areas (conflicts, staged,
  changes, untracked), the diff of the focused one beside them. Space stages or
  unstages it (on an area: all of it), Enter opens it, Del throws its changes
  away, Ctrl+K commits;
- **Git > History**: the commits with the graph of their branches; beside the
  list, the focused commit (its message, who, when, the files); Enter shows its
  diff. **File history**: only the commits of the file being edited;
- **Git > Branches**: local and remote; Enter switches to one, Ins makes a new
  one, Del deletes one;
- **Commit**, **Pull**, **Push**, **Fetch**: git does them under the progress
  box, its output in the "Git" window; **Diff of the file**: the file being
  edited against the last commit.

The project window says, on its bottom border, the branch and how far it is
from its upstream (``main ↑1 ↓2``) and how many files changed.
"""

from __future__ import annotations

from divide.i18n import _, ngettext

import time
from dataclasses import dataclass
from pathlib import Path

from rich.style import Style
from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, Tree
from textual_vision.button import Button
from textual_vision.cluster import CheckBoxes
from textual_vision.constants import Command, OptionFlag
from textual_vision.group import TVViewMixin
from textual_vision.label import Label

from divide import themes
from divide.editor.theme import OUTPUT
from divide.run import git
from divide.ui.dialogs import _Dialog, confirm, information, InputDialog
from divide.ui.filter import Filtered, FilteredTree
from divide.ui.progress import ProgressDialog, run_with_progress
from divide.ui.windows import OUTPUT_CSS, EditorView, HRule, IndicatorFrame, VRule, _TVWindow

LOG_LINES = 2000
REFRESH = 5.0  # seconds between two looks at the repository (the project window's border)

CM_GIT_CHANGES = Command.USER + 160
CM_GIT_HISTORY = Command.USER + 161
CM_GIT_BRANCHES = Command.USER + 162
CM_GIT_COMMIT = Command.USER + 163
CM_GIT_PULL = Command.USER + 164
CM_GIT_PUSH = Command.USER + 165
CM_GIT_FETCH = Command.USER + 166
CM_GIT_DIFF_FILE = Command.USER + 167
CM_GIT_FILE_HISTORY = Command.USER + 168
CM_GIT_BLAME = Command.USER + 169
# the windows' local menus (Alt+F10)
CM_GIT_STAGE = Command.USER + 170
CM_GIT_STAGE_ALL = Command.USER + 171
CM_GIT_UNSTAGE_ALL = Command.USER + 172
CM_GIT_DISCARD = Command.USER + 173
CM_GIT_OPEN = Command.USER + 174
CM_GIT_AMEND = Command.USER + 175
CM_GIT_SWITCH = Command.USER + 176
CM_GIT_NEW_BRANCH = Command.USER + 177
CM_GIT_DELETE_BRANCH = Command.USER + 178
CM_GIT_DIFF = Command.USER + 179
CM_GIT_COPY = Command.USER + 180
CM_GIT_MERGE = Command.USER + 181
CM_GIT_ABORT_MERGE = Command.USER + 182
CM_GIT_STASH = Command.USER + 183
CM_GIT_UNSTASH = Command.USER + 184
CM_GIT_APPLY_STASH = Command.USER + 185

# Colour slots (every palette gives each a colour that reads on its windows).
AREA, PATH = "lightcyan", "white"
CODES = {"M": "yellow", "A": "lightgreen", "D": "lightred", "R": "lightcyan", "C": "lightcyan", "T": "yellow",
         "U": "lightmagenta", "?": "lightgray"}
GRAPH = ("lightcyan", "lightmagenta", "lightgreen", "yellow", "lightred", "lightblue")
HASH, WHEN, WHO, HEAD, LOCAL, REMOTE, TAG = (
    "yellow", "lightgray", "cyan", "lightcyan", "lightgreen", "lightred", "yellow")

AREAS = ("conflicts", "staged", "changes", "untracked")


def area_title(area: str) -> str:
    return {"conflicts": _("Conflicts"), "staged": _("Staged (the next commit)"), "changes": _("Changes"),
            "untracked": _("Untracked")}[area]


def when(seconds: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(seconds)) if seconds else ""


def where(status: git.Status) -> str:
    """``main ↑1 ↓2``: the branch, then how far it is from its upstream."""
    name = status.branch or _("detached at {oid}").format(oid=status.oid[:7] or "?")
    if status.ahead:
        name += f" ↑{status.ahead}"
    if status.behind:
        name += f" ↓{status.behind}"
    return name


def _paint(window, *boxes) -> None:
    from divide.ui.dialector import _editor_styles

    normal, _focused = _editor_styles(window.palette_view)
    bg = Color.from_rich_color(normal.bgcolor) if normal.bgcolor else None
    fg = Color.from_rich_color(normal.color) if normal.color else None
    for box in boxes:
        box.styles.background = bg
        box.styles.color = fg


# ------------------------------------------------------------------ the diff
class DiffView(EditorView):
    """A diff, read only: added lines on green, removed on red, the hunks and headers in their colours."""

    def __init__(self) -> None:
        super().__init__("", read_only=True, path=Path("git.diff"))

    def show(self, text: str, conflict: bool = False) -> None:
        """A diff; with ``conflict``, a file in conflict (git's markers, our side, theirs)."""
        if text != self.text:
            self.load_text(text)
            self.move_cursor((0, 0))
        marks = []
        offset = 0
        kinds = git.conflict_kinds(text) if conflict else git.diff_kinds(text)
        for line, kind in zip(git.lines(text), kinds):
            if kind:
                marks.append((offset, offset + max(1, len(line)), "diff." + kind))
            offset += len(line) + 1
        self.set_marks(marks)


class DiffWindow(_TVWindow):
    """A file's or a commit's diff."""

    HINT = _('Ctrl+F find · Alt+F3 close')

    def __init__(self, title: str, text: str, number: int = 0) -> None:
        super().__init__(title, number=number)
        self.view = DiffView()
        self.text = text

    def compose_content(self) -> ComposeResult:
        yield self.view

    def on_mount(self) -> None:
        super().on_mount()
        self.view.show(self.text)
        self.call_after_refresh(self.view.focus)


class BlameView(EditorView):
    """The file's lines, each after the commit that last changed it; Enter shows that commit."""

    BINDINGS = [Binding("enter", "commit", show=False)]

    def __init__(self) -> None:
        super().__init__("", read_only=True, path=Path("git.blame"))

    def action_commit(self) -> None:
        window = next((a for a in self.ancestors if isinstance(a, BlameWindow)), None)
        if window is not None:
            self.app.git_blame_commit(window)  # type: ignore[attr-defined]


class BlameWindow(_TVWindow):
    """Git > Blame: who changed each line of a file last, and in which commit."""

    HINT = _('Enter the commit of the line · Ctrl+F find · Alt+F3 close')

    def __init__(self, path: str, rows: list[git.BlameLine], line: int = 0, number: int = 0) -> None:
        super().__init__(_('Blame: {file}').format(file=path), number=number)
        self.path = path
        self.view = BlameView()
        self.rows = rows
        self.line = line

    def compose_content(self) -> ComposeResult:
        yield self.view

    def on_mount(self) -> None:
        super().on_mount()
        self.show(self.rows)
        self.view.move_cursor((min(self.line, max(0, len(self.rows) - 1)), 0))
        self.call_after_refresh(self.view.reveal_cursor)
        self.call_after_refresh(self.view.focus)

    def show(self, rows: list[git.BlameLine]) -> None:
        self.rows = rows
        width = min(14, max([6, *(len(r.author) for r in rows)]))
        text, marks, offset = [], [], 0
        previous = None
        for r in rows:
            if not r.committed:
                head = f"{'':7} {'':10} {_('not committed')[:width]:<{width}}"
            elif r.oid == previous:  # the same commit as the line above: only the bar
                head = " " * (19 + width)
            else:
                head = f"{r.oid[:7]} {when(r.time)[:10]} {r.author[:width]:<{width}}"
            previous = r.oid
            line = f"{head} │ {r.text}"
            if not r.committed:
                marks.append((offset, offset + len(head), "diff.add"))
            elif head.strip():
                marks.append((offset, offset + 7, "diff.meta"))
                marks.append((offset + 8, offset + len(head), "diff.hunk"))
            text.append(line)
            offset += len(line) + 1
        self.view.load_text("\n".join(text))
        self.view.set_marks(marks)

    def line_under_cursor(self) -> git.BlameLine | None:
        row = self.view.cursor_location[0]
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def hint(self) -> str:
        r = self.line_under_cursor()
        if r is None:
            return self.HINT
        if not r.committed:
            return _('Not committed yet · ') + self.HINT
        return f"{r.oid[:7]} {r.author}: {r.summary} · {self.HINT}"


class GitLogWindow(_TVWindow):
    """What git said (read only; white on black, like Output)."""

    DEFAULT_CSS = OUTPUT_CSS.replace("{name}", "GitLogWindow")

    def __init__(self, number: int = 0) -> None:
        super().__init__(_('Git'), number=number)
        self.view = EditorView("", read_only=True, kind=OUTPUT, path=Path("git.log"))
        self.lines: list[str] = []

    def compose_content(self) -> ComposeResult:
        yield self.view

    def add(self, line: str) -> None:
        self.lines.append(line)
        del self.lines[:-LOG_LINES]
        self.call_after_refresh(self._show)

    def _show(self) -> None:
        text = "\n".join(self.lines)
        if text != self.view.text:
            self.view.load_text(text)
            last = len(self.lines) - 1
            self.view.move_cursor((max(0, last), len(self.lines[last]) if self.lines else 0))


# ------------------------------------------------------------------ trees
@dataclass(frozen=True)
class Row:
    """A row of a Git window: a group (an area, Local, a remote) or an item (a change, a commit, a branch)."""

    kind: str  # "group" | "change" | "commit" | "branch" | "none"
    key: str
    item: object = None


class GitTree(FilteredTree, Tree[Row], TVViewMixin):
    """The trees of the Git windows: the editor's colours, folds with the arrows."""

    ICON_NODE = "► "  # Turbo Vision's own (CP437), like the outline's
    ICON_NODE_EXPANDED = "▼ "
    BINDINGS = [
        Binding("right", "unfold", "Unfold", show=False),
        Binding("left", "fold", "Fold", show=False),
        Binding("space", "space", "Space", show=False),  # Git > Changes: stage (Tree's own folds)
    ]
    DEFAULT_CSS = """
    GitTree {
        width: 1fr; height: 1fr;
        background: $divide-editor-bg;
        color: $divide-editor-text;
        scrollbar-size: 0 0;
        padding: 0;
    }
    GitTree > .tree--guides, GitTree > .tree--guides-hover, GitTree > .tree--guides-selected {
        color: $divide-editor-gutter;
    }
    GitTree > .tree--cursor, GitTree:focus > .tree--cursor {
        color: $divide-editor-selection; background: $divide-editor-selection-bg; text-style: none;
    }
    GitTree > .tree--highlight, GitTree > .tree--highlight-line { background: $divide-editor-bg; }
    """

    def __init__(self, window, name: str) -> None:
        super().__init__(name)
        self._window = window
        self.show_root = False
        self.auto_expand = False  # Enter opens; the arrows fold
        self.guide_depth = 2
        self.tv_options = OptionFlag.SELECTABLE

    def on_mount(self) -> None:
        self.app.theme_changed_signal.subscribe(self, lambda _theme: self.repaint())

    def repaint(self) -> None:
        self._invalidate()
        self.refresh()

    def filter_text_of(self, node) -> str:
        return self._window.filter_text_of(node)

    def render_label(self, node, base_style, style):
        row: Row | None = node.data
        if row is None or row.kind in ("group", "none"):
            label = Text(str(node.label), Style(color=themes.current().hex(AREA), bold=row is not None and row.kind == "group"))
        else:
            label = self._window.label_of(row)
        if self.cursor_node is node:
            label.stylize(style)  # the bar: one colour from end to end
        if node.allow_expand:
            prefix = (self.ICON_NODE_EXPANDED if node.is_expanded else self.ICON_NODE, base_style)
        else:
            prefix = ("  " if row is None or row.kind != "commit" else "", base_style)
        return Text.assemble(prefix, label)

    def action_space(self) -> None:
        stage = getattr(self._window, "action_stage", None)
        if stage is not None:
            stage()
        elif self.cursor_node is not None and self.cursor_node.allow_expand:
            self.cursor_node.toggle()

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
        # a click puts the bar on a row, a double click opens it; ► ▼ fold
        meta = event.style.meta
        if event.button == 1 and "line" in meta and not meta.get("toggle", False):
            event.prevent_default()
            self.cursor_line = meta["line"]
            if event.chain >= 2:
                self.action_select_cursor()

    def find(self, key: str):
        stack = list(self.root.children)
        while stack:
            node = stack.pop(0)
            if node.data is not None and node.data.key == key:
                return node
            stack.extend(node.children)
        return None

    def put_bar(self, key: str | None) -> bool:
        node = self.find(key) if key else None
        if node is None:
            return False
        self.call_after_refresh(lambda: self.move_cursor(node, animate=False))
        return True

    def first_item(self):
        stack = list(self.root.children)
        while stack:
            node = stack.pop(0)
            if node.data is not None and node.data.kind not in ("group", "none"):
                return node
            stack.extend(node.children)
        return None


class _GitWindow(_TVWindow):
    """A Git window: a tree at the left over the repository's state, a view at the right."""

    HINT = ""
    REMOTE = False  # it asks a server (the forge): not reloaded after every local change
    LEFT = 44
    BINDINGS = [
        Binding("ctrl+r", "reload", show=False),
        Binding("alt+f10,shift+f10", "local_menu", show=False),
    ]

    def __init__(self, title: str, root: Path, number: int = 0) -> None:
        self.repo = root
        super().__init__(title, number=number)
        self.git_tree = GitTree(self, "git")
        self.state = Static("", classes="git-state", markup=False)
        self.palette_view = EditorView("", read_only=True)  # only lends its colours
        self.status = git.Status()
        self.last: str | None = None  # the last command and how it ended
        self._folded: set[str] = set()

    DEFAULT_CSS = """
    _GitWindow .git-left { height: 1fr; }
    _GitWindow .git-state { height: 3; padding: 0 1; }
    _GitWindow .git-right { height: 1fr; width: 1fr; }
    _GitWindow .git-info { padding: 0 1; }
    """

    def compose_left(self) -> ComposeResult:
        with Vertical(classes="git-left") as left:
            left.styles.width = self.LEFT
            yield Filtered(self.git_tree)
            yield HRule()
            yield self.state

    def on_mount(self) -> None:
        super().on_mount()
        self.call_after_refresh(self.paint)
        self.call_after_refresh(self.reload)
        self.call_after_refresh(self.git_tree.focus)
        self.app.theme_changed_signal.subscribe(self, lambda _theme: self.call_after_refresh(self.paint))

    def paint(self) -> None:
        _paint(self, self.state, *self.query(".git-left, .git-right, .git-info"))
        self.git_tree.repaint()

    def label_of(self, row: Row) -> Text:
        return Text(row.key)

    def filter_text_of(self, node) -> str:
        return str(node.label)

    def show_state(self, *lines: str) -> None:
        text = [where(self.status) + (f" · {self.status.upstream}" if self.status.upstream else _(" · no upstream")), *lines]
        if self.last:
            text.append(self.last)
        self.state.update("\n".join(text[:3]))

    def remember_folds(self) -> None:
        stack = list(self.git_tree.root.children)
        while stack:
            node = stack.pop()
            if node.data is not None and node.allow_expand:
                (self._folded.discard if node.is_expanded else self._folded.add)(node.data.key)
            stack.extend(node.children)

    def on_tree_node_collapsed(self, event: Tree.NodeCollapsed) -> None:
        event.stop()
        if event.node.data is not None:
            self._folded.add(event.node.data.key)

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        event.stop()
        if event.node.data is not None:
            self._folded.discard(event.node.data.key)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        event.stop()
        self.focused_row(event.node.data)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        event.stop()
        row = event.node.data
        if row is None or row.kind == "none":
            return
        if row.kind == "group":
            event.node.toggle()
        else:
            self.chosen(row)

    def focused_row(self, row: Row | None) -> None:
        pass

    def chosen(self, row: Row) -> None:
        pass

    @property
    def row(self) -> Row | None:
        node = self.git_tree.cursor_node
        return node.data if node is not None else None

    def action_reload(self) -> None:
        self.reload()

    def reload(self) -> None:
        pass

    def action_local_menu(self) -> None:
        self.app.git_action(self, "menu")  # type: ignore[attr-defined]


# ------------------------------------------------------------------ changes
class GitChangesWindow(_GitWindow):
    """The files that changed, in their areas | the focused one's diff."""

    HINT = _('Space stage/unstage · Enter open · Del discard · Ctrl+K commit · Alt+F10 more')
    BINDINGS = [
        Binding("space", "stage", show=False),
        Binding("delete", "discard", show=False),
        Binding("ctrl+k", "commit", show=False),
    ]

    def __init__(self, root: Path, number: int = 0) -> None:
        super().__init__(_('Git: changes'), root, number=number)
        self.diff = DiffView()
        self.change: git.Change | None = None
        self.merging = False

    def compose_content(self) -> ComposeResult:
        with Horizontal():
            yield from self.compose_left()
            yield VRule()
            with Vertical(classes="git-right"):
                yield self.diff

    def label_of(self, row: Row) -> Text:
        change: git.Change = row.item  # type: ignore[assignment]
        palette = themes.current()
        path = f"{change.orig} -> {change.path}" if change.orig else change.path
        return Text.assemble((f"{change.code} ", Style(color=palette.hex(CODES.get(change.code, PATH)), bold=True)),
                             (path, Style(color=palette.hex(PATH))))

    def filter_text_of(self, node) -> str:
        row: Row | None = node.data
        return row.item.path if row is not None and row.kind == "change" else str(node.label)  # type: ignore[union-attr]

    @work(group="git-changes", exclusive=True)
    async def reload(self) -> None:
        try:
            self.status = await git.status(self.repo)
            self.merging = await git.merging(self.repo)
        except git.GitError as exc:
            self.state.update(f"[!] {exc}")
            return
        tree = self.git_tree
        keep = self.row.key if self.row is not None else None
        self.remember_folds()
        tree.clear()
        for area in AREAS:
            changes = self.status.area(area)
            if not changes:
                continue
            group = tree.root.add(f"{area_title(area)}  {len(changes)}", Row("group", area), expand=area not in self._folded)
            for change in changes:
                group.add_leaf(change.path, Row("change", f"{area}:{change.path}", change))
        if self.status.clean:
            tree.root.add_leaf(_('Nothing changed since the last commit'), Row("none", "none"))
        if not tree.put_bar(keep):
            first = tree.first_item()
            if first is not None:
                tree.put_bar(first.data.key)
            else:
                self.focused_row(None)
        staged = len(self.status.area("staged"))
        if self.merging:
            conflicts = len(self.status.area("conflicts"))
            self.show_state(_("Merging: solve the conflicts (Space marks one solved), then Ctrl+K") if conflicts
                            else _("Merging: no conflicts left, Ctrl+K commits the merge"))
            self.app.git_status_changed(self.status)  # type: ignore[attr-defined]
            return
        self.show_state(ngettext("{n} file staged", "{n} files staged", staged).format(n=staged) + " · "
                        + ngettext("{n} other change", "{n} other changes", len(self.status.changes) - staged).format(
                            n=len(self.status.changes) - staged))
        self.app.git_status_changed(self.status)  # type: ignore[attr-defined]

    def focused_row(self, row: Row | None) -> None:
        if row is None or row.kind != "change":
            self.change = None
            if row is not None and row.kind == "group":
                count = len(self.status.area(row.key))
                self.diff.show(area_title(row.key) + "\n\n" + {
                    "conflicts": _("Files git could not merge by itself: edit them, then Space marks them solved."),
                    "staged": _("What the next commit takes (Ctrl+K commits it). Space takes a file out."),
                    "changes": _("Files changed since the last commit, not staged yet: Space stages them."),
                    "untracked": _("Files git does not follow yet: Space stages them, Del deletes them."),
                }[row.key] + "\n\n" + ngettext("{n} file", "{n} files", count).format(n=count))
            else:
                self.diff.show(_("Nothing changed: the working tree is the last commit.") if self.status.clean else "")
            return
        self.change = row.item  # type: ignore[assignment]
        self.show_diff(row.item)  # type: ignore[arg-type]

    @work(group="git-diff", exclusive=True)
    async def show_diff(self, change: git.Change) -> None:
        if change.area == "conflicts":  # the file with git's markers: our side, theirs
            try:
                text = (self.repo / change.path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                text = str(exc)
            if self.change is change:
                self.diff.show(text, conflict=True)
            return
        try:
            text = await git.diff_of(self.repo, change)
        except git.GitError as exc:
            text = str(exc)
        if self.change is change:
            self.diff.show(text or _("(no differences in the text)"))

    def chosen(self, row: Row) -> None:
        self.app.git_action(self, "open")  # type: ignore[attr-defined]

    def action_stage(self) -> None:
        self.app.git_action(self, "stage")  # type: ignore[attr-defined]

    def action_discard(self) -> None:
        self.app.git_action(self, "discard")  # type: ignore[attr-defined]

    def action_commit(self) -> None:
        self.app.git_action(self, "commit")  # type: ignore[attr-defined]


# ------------------------------------------------------------------ history
class GitHistoryWindow(_GitWindow):
    """The commits, with the graph, over the focused one."""

    HINT = _('Enter its diff · Ctrl+R reload · Alt+F10 new branch here, copy the hash')
    LEFT = 0  # the list takes the room; the commit is at the right

    def __init__(self, root: Path, path: str | None = None, number: int = 0) -> None:
        title = _('Git: history of {file}').format(file=path) if path else _('Git: history')
        super().__init__(title, root, number=number)
        self.path = path
        self.info = Static("", classes="git-info", markup=False)
        self.commits: list[git.Commit] = []
        self.commit: git.Commit | None = None

    DEFAULT_CSS = """
    GitHistoryWindow .git-left { width: 1fr; height: 1fr; }
    GitHistoryWindow .git-state { height: 1; }
    GitHistoryWindow .git-right { width: 1fr; height: 11; }
    """

    def compose_content(self) -> ComposeResult:
        with Vertical():
            with Vertical(classes="git-left"):
                yield Filtered(self.git_tree)
            yield HRule()
            yield self.state
            with VerticalScroll(classes="git-right"):
                yield self.info

    def show_state(self, *lines: str) -> None:
        text = " · ".join([where(self.status), *lines] + ([self.last] if self.last else []))
        self.state.update(text)

    def label_of(self, row: Row) -> Text:
        c: git.Commit = row.item  # type: ignore[assignment]
        palette = themes.current()
        out = Text()
        for i, ch in enumerate(c.graph.ljust(self.graph_width)):
            out.append(ch, Style(color=palette.hex(GRAPH[(i // 2) % len(GRAPH)]), bold=ch == "*"))
        if not c.oid:
            return out
        out.append(f" {c.short} ", Style(color=palette.hex(HASH)))
        out.append(f"{when(c.time)[:10]} ", Style(color=palette.hex(WHEN)))
        out.append(f"{c.author[:12]:<12} ", Style(color=palette.hex(WHO)))
        for ref in c.refs:
            if ref.startswith("HEAD -> "):
                out.append(f"[{ref[8:]}]", Style(color=palette.hex(HEAD), bold=True))
            elif ref == "HEAD":
                out.append("[HEAD]", Style(color=palette.hex(HEAD), bold=True))
            elif ref.startswith("tag: "):
                out.append(f"<{ref[5:]}>", Style(color=palette.hex(TAG), bold=True))
            elif "/" in ref and ref.split("/", 1)[0] in self.remotes:
                out.append(f"[{ref}]", Style(color=palette.hex(REMOTE)))
            else:
                out.append(f"[{ref}]", Style(color=palette.hex(LOCAL), bold=True))
            out.append(" ")
        out.append(c.subject, Style(color=palette.hex(PATH)))
        return out

    def filter_text_of(self, node) -> str:
        row: Row | None = node.data
        if row is None or row.kind != "commit":
            return str(node.label)
        c: git.Commit = row.item  # type: ignore[assignment]
        return f"{c.short} {c.author} {' '.join(c.refs)} {c.subject}" if c.oid else ""

    @property
    def chosen_commit(self) -> git.Commit | None:
        """The commit under the bar (read from the bar: its highlight may come later)."""
        row = self.row
        c = row.item if row is not None and row.kind == "commit" else None
        return c if c is not None and c.oid else None  # type: ignore[union-attr,return-value]

    @property
    def graph_width(self) -> int:
        return max((len(c.graph) for c in self.commits), default=1)

    @work(group="git-history", exclusive=True)
    async def reload(self) -> None:
        try:
            self.status = await git.status(self.repo)
            self.remotes = set(await git.remotes(self.repo))
            self.commits = await git.log(self.repo, path=self.path)
        except git.GitError as exc:
            self.state.update(f"[!] {exc}")
            return
        tree = self.git_tree
        keep = self.row.key if self.row is not None else None
        tree.clear()
        tree.guide_depth = 0
        for i, c in enumerate(self.commits):
            tree.root.add_leaf(c.subject or c.graph, Row("commit", c.oid or f"graph:{i}", c))
        if not self.commits:
            tree.root.add_leaf(_('No commits yet'), Row("none", "none"))
        if not tree.put_bar(keep):
            first = tree.first_item()
            if first is not None:
                tree.put_bar(first.data.key)
            else:
                self.focused_row(None)
        count = sum(1 for c in self.commits if c.oid)
        self.show_state(ngettext("{n} commit", "{n} commits", count).format(n=count)
                        + (_(" (the newest)") if count >= 400 else ""))

    remotes: set[str] = set()

    def focused_row(self, row: Row | None) -> None:
        c = row.item if row is not None and row.kind == "commit" else None
        if c is None or not c.oid:  # type: ignore[union-attr]
            self.commit = None
            self.info.update("" if self.commits else _("The repository has no commits yet: Git > Commit makes the first one."))
            return
        self.commit = c  # type: ignore[assignment]
        self.info.update(f"{c.short}  {c.subject}")  # type: ignore[union-attr]
        self.show_details(c)  # type: ignore[arg-type]

    @work(group="git-details", exclusive=True)
    async def show_details(self, c: git.Commit) -> None:
        try:
            info = await git.details(self.repo, c.oid)
        except git.GitError as exc:
            self.info.update(str(exc))
            return
        if self.commit is not c:
            return
        lines = [_("Commit  {oid}").format(oid=c.oid) + "   " + _("Date  {when}").format(when=when(c.time)),
                 _("Author  {who} <{email}>").format(who=c.author, email=c.email)]
        if info.committer and not info.committer.startswith(f"{c.author} <"):
            lines.append(_("Commit by {who}").format(who=info.committer))
        if c.refs:
            lines.append(_("Refs    {refs}").format(refs=", ".join(c.refs)))
        if len(c.parents) > 1:
            lines.append(_("Merge of {parents}").format(parents=" ".join(p[:7] for p in c.parents)))
        lines += ["", *("    " + line if line else "" for line in info.message.splitlines()), ""]
        lines.append(ngettext("{n} file changed:", "{n} files changed:", len(info.files)).format(n=len(info.files)))
        lines += [f"  {code} {path}" for code, path in info.files]
        self.info.update("\n".join(lines))

    def chosen(self, row: Row) -> None:
        self.app.git_action(self, "diff")  # type: ignore[attr-defined]


# ------------------------------------------------------------------ branches
class GitBranchesWindow(_GitWindow):
    """Local and remote branches | the focused one."""

    HINT = _('Enter switch to it · Ins new branch · Del delete · Alt+F10 more')
    BINDINGS = [
        Binding("insert", "new_branch", show=False),
        Binding("delete", "delete_branch", show=False),
    ]
    LEFT = 40

    def __init__(self, root: Path, number: int = 0) -> None:
        super().__init__(_('Git: branches'), root, number=number)
        self.info = Static("", classes="git-info", markup=False)
        self.branches: list[git.Branch] = []
        self.stashes: list[git.Stash] = []

    @property
    def branch(self) -> git.Branch | None:
        """The branch under the bar (read from the bar: its highlight may come later)."""
        row = self.row
        return row.item if row is not None and row.kind == "branch" else None  # type: ignore[return-value]

    @property
    def stash(self) -> git.Stash | None:
        row = self.row
        return row.item if row is not None and row.kind == "stash" else None  # type: ignore[return-value]

    def compose_content(self) -> ComposeResult:
        with Horizontal():
            yield from self.compose_left()
            yield VRule()
            with VerticalScroll(classes="git-right"):
                yield self.info

    def label_of(self, row: Row) -> Text:
        palette = themes.current()
        if row.kind == "stash":
            st: git.Stash = row.item  # type: ignore[assignment]
            return Text.assemble((f"  {st.ref} ", Style(color=palette.hex(HASH))), (st.message, Style(color=palette.hex(PATH))))
        b: git.Branch = row.item  # type: ignore[assignment]
        name = b.name.split("/", 1)[1] if b.remote else b.name
        colour = HEAD if b.current else REMOTE if b.remote else LOCAL
        out = Text.assemble(("* " if b.current else "  ", Style(color=palette.hex(HEAD), bold=True)),
                            (name, Style(color=palette.hex(colour), bold=b.current)))
        if b.track:
            out.append(f"  [{b.track}]", Style(color=palette.hex(WHEN)))
        return out

    def filter_text_of(self, node) -> str:
        row: Row | None = node.data
        if row is not None and row.kind == "stash":
            return f"{row.item.ref} {row.item.message}"  # type: ignore[union-attr]
        return row.item.name if row is not None and row.kind == "branch" else str(node.label)  # type: ignore[union-attr]

    @work(group="git-branches", exclusive=True)
    async def reload(self) -> None:
        try:
            self.status = await git.status(self.repo)
            self.branches = await git.branches(self.repo)
            self.stashes = await git.stashes(self.repo)
        except git.GitError as exc:
            self.state.update(f"[!] {exc}")
            return
        tree = self.git_tree
        keep = self.row.key if self.row is not None else None
        self.remember_folds()
        tree.clear()
        local = [b for b in self.branches if not b.remote]
        group = tree.root.add(_("Local  {n}").format(n=len(local)), Row("group", "local"), expand="local" not in self._folded)
        for b in sorted(local, key=lambda b: (not b.current, b.name)):
            group.add_leaf(b.name, Row("branch", b.name, b))
        remotes: dict[str, list[git.Branch]] = {}
        for b in self.branches:
            if b.remote:
                remotes.setdefault(b.name.split("/", 1)[0], []).append(b)
        for remote, members in sorted(remotes.items()):
            key = f"remote:{remote}"
            node = tree.root.add(f"{remote}  {len(members)}", Row("group", key), expand=key not in self._folded)
            for b in sorted(members, key=lambda b: b.name):
                node.add_leaf(b.name, Row("branch", b.name, b))
        if self.stashes:
            node = tree.root.add(_("Stashes  {n}").format(n=len(self.stashes)), Row("group", "stashes"),
                                 expand="stashes" not in self._folded)
            for st in self.stashes:
                node.add_leaf(st.ref, Row("stash", f"stash:{st.time}:{st.message}", st))
        if not tree.put_bar(keep):
            current = next((b for b in local if b.current), None)
            tree.put_bar(current.name if current else None) or self.focused_row(None)
        self.show_state(ngettext("{n} branch", "{n} branches", len(local)).format(n=len(local)) + " · "
                        + ngettext("{n} remote", "{n} remotes", len(remotes)).format(n=len(remotes)))
        self.app.git_status_changed(self.status)  # type: ignore[attr-defined]

    def focused_row(self, row: Row | None) -> None:
        if row is not None and row.kind == "stash":
            st: git.Stash = row.item  # type: ignore[assignment]
            self.info.update("\n".join([st.ref, "─" * len(st.ref), st.message, when(st.time), "",
                                         _("Enter brings its changes back (and drops it); Del drops it.")]))
            return
        b = row.item if row is not None and row.kind == "branch" else None
        if b is None:
            self.info.update(_("Enter switches to the branch under the bar; a remote one gets its local branch."))
            return
        lines = [b.name, "─" * len(b.name)]  # type: ignore[union-attr]
        rows = [
            (_("Kind"), _("remote") if b.remote else _("local")),  # type: ignore[union-attr]
            (_("Current"), _("yes") if b.current else ""),  # type: ignore[union-attr]
            (_("Upstream"), b.upstream),  # type: ignore[union-attr]
            (_("Tracking"), b.track),  # type: ignore[union-attr]
            (_("Last commit"), b.short),  # type: ignore[union-attr]
            (_("Date"), when(b.time)),  # type: ignore[union-attr]
        ]
        width = max(len(label) for label, _value in rows)
        lines += [f"{label:<{width}}  {value}" for label, value in rows if value]
        lines += ["", b.subject]  # type: ignore[union-attr]
        self.info.update("\n".join(lines))

    def chosen(self, row: Row) -> None:
        self.app.git_action(self, "unstash" if row.kind == "stash" else "switch")  # type: ignore[attr-defined]

    def action_new_branch(self) -> None:
        self.app.git_action(self, "new_branch")  # type: ignore[attr-defined]

    def action_delete_branch(self) -> None:
        row = self.row
        self.app.git_action(self, "drop_stash" if row is not None and row.kind == "stash" else "delete_branch")  # type: ignore[attr-defined]


# ------------------------------------------------------------------ commit
class MessageView(EditorView):
    """The commit's message: Enter starts a new line, Ctrl+Enter commits."""

    COMMIT_KEYS = ("ctrl+enter", "ctrl+j")

    def __init__(self) -> None:
        super().__init__("", path=Path("COMMIT_EDITMSG"))
        self.show_line_numbers = False

    async def _on_key(self, event: events.Key) -> None:
        if event.key in self.COMMIT_KEYS:
            event.stop()
            event.prevent_default()
            dialog = next((a for a in self.ancestors if isinstance(a, _Dialog) and hasattr(a, "action_commit")), None)
            if dialog is not None:
                dialog.action_commit()
            return
        await super()._on_key(event)


class CommitDialog(_Dialog):
    """The message (its first line, the summary), amend, and what goes in. Ctrl+Enter
    commits from inside the message, where Enter starts a new line."""

    DEFAULT_CSS = """
    CommitDialog { width: 78; height: 20; }
    CommitDialog EditorView { height: 1fr; }
    CommitDialog .cm-what { height: 2; color: $text-muted; background: $surface; }
    CommitDialog .cm-what.-bad { color: $error; }
    CommitDialog CheckBoxes { width: 1fr; }
    """

    def __init__(self, status: git.Status, last_message: str = "", merging: bool = False) -> None:
        super().__init__(title=_('Commit the merge') if merging else _('Commit'))
        self.status = status
        self.merging = merging
        self.last_message = last_message
        self.message = MessageView()
        staged = len(status.area("staged"))
        self.flags = CheckBoxes([_('~A~mend the last commit (replace it)'), _('~S~tage every change first')])
        self.flags.value = 0 if staged else 2
        self.what = Static(self._what(), classes="cm-what", markup=False)
        self.text = ""
        self.amend = False
        self.stage_all = False
        self._flags = self.flags.value

    def _what(self) -> str:
        staged = len(self.status.area("staged"))
        others = len(self.status.changes) - staged
        text = ngettext("{n} file staged", "{n} files staged", staged).format(n=staged)
        if others:
            text += " · " + ngettext("{n} other change", "{n} other changes", others).format(n=others)
        return text + "\n" + _("The first line is the summary; a blank line, then the details.")

    def compose_content(self) -> ComposeResult:
        yield Label(_('~M~essage'), link=self.message)
        yield self.message
        yield self.flags
        yield self.what
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('C~o~mmit'), Command.OK, is_default=True, id="ok")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.message.focus)

    def on_cluster_changed(self, message) -> None:
        amend = bool(self.flags.value & 1)
        if amend and not self._flags & 1 and not self.message.text.strip() and self.last_message:
            self.message.load_text(self.last_message)  # amending: the last message, to change
        self._flags = self.flags.value

    def action_commit(self) -> None:
        self.end_modal(Command.OK)  # valid() still has its say

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        self.amend = bool(self.flags.value & 1)
        self.stage_all = bool(self.flags.value & 2)
        lines = [line.rstrip() for line in self.message.text.strip().splitlines()]
        self.text = "\n".join(lines)
        problem = ""
        if not self.text:
            problem = _("Write a message: what this commit does, in a line.")
        elif not self.amend and not self.stage_all and not self.merging and not self.status.area("staged"):
            problem = _("Nothing is staged: stage files (Space in Git > Changes) or tick Stage every change first.")
        elif self.status.area("conflicts"):
            problem = _("Some files are in conflict: solve them first.")
        if problem:
            self.what.set_class(True, "-bad")
            self.what.update(f"[!] {problem}")
            return False
        return True


# ------------------------------------------------------------------ the app's part
class GitMixin:
    """The Git menu, its windows, and git run under the progress box."""

    git_state: git.Status | None = None
    _git_timer = None
    _git_bases: dict  # resolved path -> (HEAD's oid, the file as HEAD has it, or None)
    _git_typing: dict  # id(editor) -> the timer that marks it again after typing

    @property
    def git_root(self) -> Path | None:
        return git.find_root(self.root)  # type: ignore[attr-defined]

    def git_windows(self) -> list[_GitWindow]:
        return [w for w in self.windows() if isinstance(w, _GitWindow)]  # type: ignore[attr-defined]

    def git_log(self) -> GitLogWindow | None:
        return next((w for w in self.windows() if isinstance(w, GitLogWindow)), None)  # type: ignore[attr-defined]

    # ------------------------------------------------------------ the project window's border
    def start_git_watch(self) -> None:
        if self._git_timer is None:
            self._git_timer = self.set_interval(REFRESH, self.refresh_git_state)  # type: ignore[attr-defined]
        self.refresh_git_state()

    @work(group="git-state", exclusive=True)
    async def refresh_git_state(self) -> None:
        root = self.git_root
        if root is None or git.program() is None:
            self.git_status_changed(None)
            return
        try:
            state = await git.status(root, ignored=True)
        except git.GitError:
            state = None
        self.git_status_changed(state, root)
        await self._git_mark_editors(root, state)

    async def _git_mark_editors(self, root: Path, state: git.Status | None) -> None:
        """The gutter marks of every editor of a file in the repository."""
        bases = self.__dict__.setdefault("_git_bases", {})
        for win in self.editor_windows():  # type: ignore[attr-defined]
            if win.path is None or state is None or not state.oid:
                win.editor.set_change_marks({})
                continue
            path = win.path.resolve()
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                win.editor.set_change_marks({})
                continue
            cached = bases.get(path)
            if cached is None or cached[0] != state.oid:
                try:
                    cached = (state.oid, await git.head_text(root, rel))
                except git.GitError:
                    cached = (state.oid, None)
                bases[path] = cached
            self._git_mark(win)

    def _git_mark(self, win) -> None:
        cached = self.__dict__.get("_git_bases", {}).get(win.path.resolve()) if win.path is not None else None
        if cached is None or cached[1] is None:  # not in the last commit (new, or not in the repository)
            win.editor.set_change_marks({})
        else:
            win.editor.set_change_marks(git.line_changes(cached[1], win.editor.text))

    def git_editor_changed(self, editor) -> None:
        """Typing: the gutter marks again, once the keys pause."""
        win = next((w for w in self.editor_windows() if w.editor is editor), None)  # type: ignore[attr-defined]
        if win is None or win.path is None or win.path.resolve() not in self.__dict__.get("_git_bases", {}):
            return
        timers = self.__dict__.setdefault("_git_typing", {})
        old = timers.pop(id(editor), None)
        if old is not None:
            old.stop()
        timers[id(editor)] = self.set_timer(0.4, lambda: self._git_mark(win))  # type: ignore[attr-defined]

    def git_status_changed(self, state: git.Status | None, root: Path | None = None) -> None:
        """The repository's state: the project window's border and its marks (``root`` given:
        the state was read with the ignored files)."""
        self.git_state = state
        project = self.project_window()  # type: ignore[attr-defined]
        if project is None:
            return
        if state is None:
            project.project_tree.set_git({}, set(), set())
        elif root is not None:
            project.project_tree.set_git(*git.marks(state, root))
        frames = list(project.query(IndicatorFrame)) if project.is_mounted else []
        if not frames:  # just opened (or closing): its border once it is there
            if project.is_attached:
                self.set_timer(0.2, lambda: self.git_status_changed(self.git_state, root))  # type: ignore[attr-defined]
            return
        frame = frames[0]
        if state is None:
            frame.set_indicator("")
            return
        count = len({c.path for c in state.changes})
        text = where(state)
        if count:
            text += " · " + ngettext("{n} changed", "{n} changed", count).format(n=count)
        frame.set_indicator(text)

    # ------------------------------------------------------------ opening
    async def _git_ready(self) -> Path | None:
        if git.program() is None:
            await self.run_dialog(information(_('Git'), _(  # type: ignore[attr-defined]
                'git was not found: install it (https://git-scm.com) and start divide again')))
            return None
        root = self.git_root
        if root is None:
            await self.run_dialog(information(_('Git'), _(  # type: ignore[attr-defined]
                'The project is not in a git repository (no .git in its folder or above it). '
                'In a terminal, git init makes one.')))
        return root

    async def open_git(self, kind: type[_GitWindow], **kwargs) -> _GitWindow | None:
        root = await self._git_ready()
        if root is None:
            return None
        view = next((w for w in self.windows() if type(w) is kind  # type: ignore[attr-defined]
                     and all(getattr(w, k, None) == v for k, v in kwargs.items())), None)
        if view is None:
            view = kind(root, number=self._free_number(), **kwargs)  # type: ignore[attr-defined,call-arg]
            self._insert(view)  # type: ignore[attr-defined]
        else:
            self.raise_window(view)  # type: ignore[attr-defined]
            view.reload()
        return view

    async def git_command(self, command: int) -> None:
        """The Git menu's commands."""
        match command:
            case _ if command == CM_GIT_CHANGES:
                await self.open_git(GitChangesWindow)
            case _ if command == CM_GIT_HISTORY:
                await self.open_git(GitHistoryWindow)
            case _ if command == CM_GIT_BRANCHES:
                await self.open_git(GitBranchesWindow)
            case _ if command == CM_GIT_FILE_HISTORY:
                path = self._git_file()
                if path is not None:
                    await self.open_git(GitHistoryWindow, path=path)
            case _ if command == CM_GIT_DIFF_FILE:
                path = self._git_file()
                if path is not None:
                    await self._git_diff_file(path)
            case _ if command == CM_GIT_BLAME:
                path = self._git_file()
                if path is not None:
                    await self._git_blame(path)
            case _ if command in (CM_GIT_COMMIT, CM_GIT_PULL, CM_GIT_PUSH, CM_GIT_FETCH):
                if await self._git_ready() is None:
                    return
                action = {CM_GIT_COMMIT: "commit", CM_GIT_PULL: "pull", CM_GIT_PUSH: "push", CM_GIT_FETCH: "fetch"}[command]
                self.git_action(None, action)

    def _git_file(self) -> str | None:
        from divide.ui.windows import EditorWindow

        root = self.git_root
        win = self.active_window()  # type: ignore[attr-defined]
        path = getattr(win, "path", None) if isinstance(win, EditorWindow) else None
        if root is None or path is None:
            self.notify(_('Open a file of the repository first'), timeout=3)  # type: ignore[attr-defined]
            return None
        try:
            return Path(path).resolve().relative_to(root).as_posix()
        except ValueError:
            self.notify(_('{file} is not in the repository').format(file=Path(path).name), timeout=3)  # type: ignore[attr-defined]
            return None

    async def _git_diff_file(self, path: str) -> None:
        root = self.git_root
        assert root is not None
        try:
            if await git.has_commits(root):
                text = await git.capture(["diff", "--no-ext-diff", "HEAD", "--", path], root)
            else:
                text = git.new_file_diff(root, path)
        except git.GitError as exc:
            await self.run_dialog(information(_('Git'), str(exc)))  # type: ignore[attr-defined]
            return
        if not text.strip():
            self.notify(_('{file}: no changes since the last commit').format(file=path), timeout=3)  # type: ignore[attr-defined]
            return
        self._show_diff(_('Diff: {file}').format(file=path), text)

    async def _git_blame(self, path: str) -> None:
        root = self.git_root
        assert root is not None
        win = self.active_window()  # type: ignore[attr-defined]
        editor = getattr(win, "editor", None)
        contents = editor.text if editor is not None and getattr(win, "dirty", False) else None
        line = editor.cursor_location[0] if editor is not None else 0
        try:
            rows = await git.blame(root, path, contents)
        except git.GitError as exc:
            await self.run_dialog(information(_('Git'), str(exc)))  # type: ignore[attr-defined]
            return
        old = next((w for w in self.windows() if isinstance(w, BlameWindow) and w.path == path), None)  # type: ignore[attr-defined]
        if old is not None:
            old.show(rows)
            old.view.move_cursor((min(line, max(0, len(rows) - 1)), 0))
            self.raise_window(old)  # type: ignore[attr-defined]
            return
        self._insert(BlameWindow(path, rows, line, number=self._free_number()))  # type: ignore[attr-defined]

    def git_blame_commit(self, win: BlameWindow) -> None:
        r = win.line_under_cursor()
        if r is None:
            return
        if not r.committed:
            self.notify(_('This line is not committed yet'), timeout=3)  # type: ignore[attr-defined]
            return
        self._git_show_commit(r.oid)

    @work(group="git-show", exclusive=True)
    async def _git_show_commit(self, oid: str) -> None:
        root = self.git_root
        if root is None:
            return
        try:
            text = await git.diff_of_commit(root, oid)
        except git.GitError as exc:
            await self.run_dialog(information(_('Git'), str(exc)))  # type: ignore[attr-defined]
            return
        self._show_diff(_('Commit {oid}').format(oid=oid[:7]), text)

    def _show_diff(self, title: str, text: str) -> None:
        old = next((w for w in self.windows() if isinstance(w, DiffWindow) and w._title == title), None)  # type: ignore[attr-defined]
        if old is not None:
            old.view.show(text)
            self.raise_window(old)  # type: ignore[attr-defined]
            return
        self._insert(DiffWindow(title, text, number=self._free_number()))  # type: ignore[attr-defined]

    # ------------------------------------------------------------ actions
    def git_action(self, win: _GitWindow | None, action: str) -> None:
        self._git_action(win, action)

    @work(group="git", exclusive=True)
    async def _git_action(self, win: _GitWindow | None, action: str) -> None:
        root = self.git_root
        if root is None:
            return
        if action == "menu" and win is not None:
            action = await self._git_menu(win)
        try:
            await self._git_do(win, action, root)
        except git.GitError as exc:
            await self.run_dialog(information(_('Git'), str(exc)))  # type: ignore[attr-defined]
        for w in self.git_windows():
            if not w.REMOTE:
                w.reload()
        self.refresh_git_state()
        if win is not None and win.is_attached:
            win.git_tree.focus()
        self.update_status()  # type: ignore[attr-defined]

    async def _git_do(self, win: _GitWindow | None, action: str, root: Path) -> None:
        row = win.row if win is not None else None
        match action:
            case "stage" if isinstance(win, GitChangesWindow) and row is not None:
                if row.kind == "change":
                    change: git.Change = row.item  # type: ignore[assignment]
                    paths = [change.path] + ([change.orig] if change.orig else [])
                    if change.area == "staged":
                        await git.unstage(root, paths)
                    else:
                        await git.stage(root, paths)
                elif row.kind == "group":
                    changes = win.status.area(row.key)
                    paths = [p for c in changes for p in [c.path] + ([c.orig] if c.orig else [])]
                    if paths:
                        await (git.unstage if row.key == "staged" else git.stage)(root, paths)
            case "stage_all":
                await git.stage(root, ["."])
            case "unstage_all":
                state = await git.status(root)
                paths = [p for c in state.area("staged") for p in [c.path] + ([c.orig] if c.orig else [])]
                if paths:
                    await git.unstage(root, paths)
            case "discard" if isinstance(win, GitChangesWindow) and row is not None and row.kind == "change":
                change = row.item  # type: ignore[assignment]
                if change.area == "staged":
                    self.notify(_('Unstage it first (Space): Del throws away what is not staged'), timeout=4)  # type: ignore[attr-defined]
                    return
                text = (_('Delete {file}? It is not in git: it cannot be brought back.') if change.area == "untracked"
                        else _('Throw away the changes to {file}? They cannot be brought back.')).format(file=change.path)
                if await self.run_dialog(confirm(_('Discard'), text)) == Command.YES:  # type: ignore[attr-defined]
                    await git.discard(root, change)
                    self._git_files_changed([root / change.path])
            case "open" if row is not None and row.kind == "change":
                file = root / row.item.path  # type: ignore[union-attr]
                if file.is_file():
                    self.open_file(file)  # type: ignore[attr-defined]
                else:
                    self.notify(_('{file} is not there (deleted)').format(file=row.item.path), timeout=3)  # type: ignore[attr-defined,union-attr]
            case "commit" | "amend":
                await self._git_commit(root, amend=action == "amend")
            case "pull":
                await self._git_remote(root, "pull")
            case "push":
                await self._git_remote(root, "push")
            case "fetch":
                await self._git_remote(root, "fetch")
            case "diff" if isinstance(win, GitHistoryWindow) and win.chosen_commit is not None:
                c = win.chosen_commit
                text = await git.diff_of_commit(root, c.oid, win.path)
                self._show_diff(_('Commit {oid}').format(oid=c.short), text)
            case "copy" if isinstance(win, GitHistoryWindow) and win.chosen_commit is not None:
                oid = win.chosen_commit.oid
                self.copy_to_clipboard(oid)  # type: ignore[attr-defined]
                self.notify(_('Copied: {oid}').format(oid=oid), timeout=3)  # type: ignore[attr-defined]
            case "new_branch":
                start = ""
                if isinstance(win, GitHistoryWindow) and win.chosen_commit is not None:
                    start = win.chosen_commit.oid
                elif isinstance(win, GitBranchesWindow) and win.branch is not None:
                    start = win.branch.name
                await self._git_new_branch(root, start)
            case "merge" if isinstance(win, GitBranchesWindow) and win.branch is not None:
                await self._git_merge(root, win.branch)
            case "abort_merge":
                if not await git.merging(root):
                    self.notify(_('No merge is halfway'), timeout=3)  # type: ignore[attr-defined]
                    return
                if await self.run_dialog(confirm(_('Abort the merge'), _(  # type: ignore[attr-defined]
                        'Abort the merge and go back to how the files were before it?'))) == Command.YES:
                    await git.abort_merge(root)
                    self._git_files_changed(None)
            case "stash":
                state = await git.status(root)
                if state.clean:
                    self.notify(_('Nothing to put aside: nothing changed'), timeout=3)  # type: ignore[attr-defined]
                    return
                dialog = InputDialog(_('Stash'), _('~W~hat it is (optional)'), allow_empty=True, history="git:stash",
                                     hint=_('The changes go aside, the files go back to the last commit'))
                if await self.run_dialog(dialog) == Command.OK:  # type: ignore[attr-defined]
                    await git.stash(root, dialog.value or "")
                    self._git_files_changed(None)
                    self.notify(_('Changes put aside: Git > Branches > Stashes brings them back'), timeout=4)  # type: ignore[attr-defined]
            case "unstash" | "apply_stash" if isinstance(win, GitBranchesWindow) and win.stash is not None:
                await git.unstash(root, win.stash.ref, keep=action == "apply_stash")
                self._git_files_changed(None)
                self.notify(_('Changes back from {ref}').format(ref=win.stash.ref), timeout=3)  # type: ignore[attr-defined]
            case "drop_stash" if isinstance(win, GitBranchesWindow) and win.stash is not None:
                text = _('Drop {ref} ({message})? Its changes are lost.').format(ref=win.stash.ref, message=win.stash.message)
                if await self.run_dialog(confirm(_('Drop the stash'), text)) == Command.YES:  # type: ignore[attr-defined]
                    await git.drop_stash(root, win.stash.ref)
            case "switch" if isinstance(win, GitBranchesWindow) and win.branch is not None:
                b = win.branch
                if b.current:
                    return
                await git.switch(root, b)
                self._git_files_changed(None)
                self.notify(_('On {branch} now').format(branch=b.name.split("/", 1)[1] if b.remote else b.name), timeout=3)  # type: ignore[attr-defined]
            case "delete_branch" if isinstance(win, GitBranchesWindow) and win.branch is not None:
                b = win.branch
                if b.remote:
                    self.notify(_('Remote branches are deleted on the remote (git push --delete)'), timeout=4)  # type: ignore[attr-defined]
                    return
                if b.current:
                    self.notify(_('This is the current branch: switch to another one first'), timeout=4)  # type: ignore[attr-defined]
                    return
                if await self.run_dialog(confirm(_('Delete branch'), _('Delete the branch {branch}?').format(branch=b.name))) != Command.YES:  # type: ignore[attr-defined]
                    return
                try:
                    await git.delete_branch(root, b.name)
                except git.GitError as exc:
                    if "not fully merged" not in str(exc):
                        raise
                    text = _('{branch} has commits that are in no other branch: delete it and lose them?').format(branch=b.name)
                    if await self.run_dialog(confirm(_('Delete branch'), text)) == Command.YES:  # type: ignore[attr-defined]
                        await git.delete_branch(root, b.name, force=True)

    async def _git_menu(self, win: _GitWindow) -> str:
        from textual_vision.menus import Menu, MenuItem as Item, Separator as Sep
        from divide.ui.explorer import LocalMenu

        if isinstance(win, GitChangesWindow):
            items = [
                Item(_('~S~tage / unstage'), CM_GIT_STAGE, _('Space')),
                Item(_('~O~pen the file'), CM_GIT_OPEN, _('Enter')),
                Item(_('~D~iscard the changes'), CM_GIT_DISCARD, _('Del')),
                Sep(),
                Item(_('Stage ~e~verything'), CM_GIT_STAGE_ALL),
                Item(_('U~n~stage everything'), CM_GIT_UNSTAGE_ALL),
                Sep(),
                Item(_('~C~ommit...'), CM_GIT_COMMIT, _('Ctrl+K')),
                Item(_('~A~mend the last commit...'), CM_GIT_AMEND),
                Item(_('S~t~ash the changes...'), CM_GIT_STASH),
                Item(_('Abort the ~m~erge'), CM_GIT_ABORT_MERGE),
            ]
        elif isinstance(win, GitHistoryWindow):
            items = [
                Item(_('~D~iff of the commit'), CM_GIT_DIFF, _('Enter')),
                Item(_('~N~ew branch here...'), CM_GIT_NEW_BRANCH),
                Item(_('~C~opy the hash'), CM_GIT_COPY),
            ]
        elif isinstance(win, GitBranchesWindow) and win.stash is not None:
            items = [
                Item(_('~B~ring it back (and drop it)'), CM_GIT_UNSTASH, _('Enter')),
                Item(_('Apply it, ~k~eeping it'), CM_GIT_APPLY_STASH),
                Item(_('~D~rop it'), CM_GIT_DELETE_BRANCH, _('Del')),
            ]
        else:
            items = [
                Item(_('~S~witch to it'), CM_GIT_SWITCH, _('Enter')),
                Item(_('~M~erge into the current branch'), CM_GIT_MERGE),
                Item(_('~N~ew branch...'), CM_GIT_NEW_BRANCH, _('Ins')),
                Item(_('~D~elete'), CM_GIT_DELETE_BRANCH, _('Del')),
            ]
        items += [Sep(), Item(_('~P~ull'), CM_GIT_PULL), Item(_('P~u~sh'), CM_GIT_PUSH), Item(_('~F~etch'), CM_GIT_FETCH)]
        tree = win.git_tree
        region = tree.content_region
        at = (region.x + 2, region.y + max(0, tree.cursor_line - tree.scroll_offset.y))
        chosen = await self.push_screen_wait(LocalMenu(Menu(items=items), at))  # type: ignore[attr-defined]
        return {
            CM_GIT_STAGE: "stage", CM_GIT_OPEN: "open", CM_GIT_DISCARD: "discard", CM_GIT_STAGE_ALL: "stage_all",
            CM_GIT_UNSTAGE_ALL: "unstage_all", CM_GIT_COMMIT: "commit", CM_GIT_AMEND: "amend", CM_GIT_DIFF: "diff",
            CM_GIT_NEW_BRANCH: "new_branch", CM_GIT_COPY: "copy", CM_GIT_SWITCH: "switch",
            CM_GIT_DELETE_BRANCH: "drop_stash" if isinstance(win, GitBranchesWindow) and win.stash is not None
            else "delete_branch", CM_GIT_PULL: "pull", CM_GIT_PUSH: "push", CM_GIT_FETCH: "fetch",
            CM_GIT_MERGE: "merge", CM_GIT_ABORT_MERGE: "abort_merge", CM_GIT_STASH: "stash",
            CM_GIT_UNSTASH: "unstash", CM_GIT_APPLY_STASH: "apply_stash",
        }.get(chosen, "")

    def _git_files_changed(self, paths: list[Path] | None) -> None:
        """Files git changed on disk (``None``: maybe any, after a switch or a pull): the project
        window, and the editors that show them, read again when they have no unsaved changes."""
        self.refresh_project()  # type: ignore[attr-defined]
        wanted = None if paths is None else {p.resolve() for p in paths}
        kept = []
        for win in self.editor_windows():  # type: ignore[attr-defined]
            if win.path is None or (wanted is not None and win.path.resolve() not in wanted):
                continue
            try:
                text = win.path.read_text(encoding="utf-8") if win.path.exists() else None
            except (OSError, UnicodeDecodeError):
                continue
            if text is None or text == win.saved_text:
                continue
            if win.dirty:
                kept.append(win.path.name)
                continue
            row, col = win.editor.cursor_location
            win.editor.load_text(text)
            win.saved_text = text
            win.editor.move_cursor((min(row, win.editor.document.line_count - 1), col))
            win.refresh_indicator()
        if kept:
            self.notify(_('Changed on disk, not read again (they have unsaved changes): {files}').format(  # type: ignore[attr-defined]
                files=", ".join(kept)), timeout=6)

    async def _git_commit(self, root: Path, amend: bool = False) -> None:
        state = await git.status(root)
        last = await git.last_message(root) if await git.has_commits(root) else ""
        merging = await git.merging(root)
        dialog = CommitDialog(state, last, merging)
        if merging:
            dialog.flags.value = dialog._flags = 0
            dialog.message.load_text(await git.merge_message(root))
        if amend:
            dialog.flags.value = 1
            dialog._flags = 1
            dialog.message.load_text(last)
        if await self.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        if dialog.stage_all:
            await git.stage(root, ["."])
        log = self._show_git_log()
        log.add(f"$ git commit{' --amend' if dialog.amend else ''}")
        result = await git.commit(root, dialog.text, amend=dialog.amend, on_line=log.add)
        log.add(_("[exit code {code}]").format(code=result.code))
        if result.ok:
            first = dialog.text.splitlines()[0]
            self.notify(_('Committed: {summary}').format(summary=first), timeout=3)  # type: ignore[attr-defined]
        else:
            self.raise_window(log)  # type: ignore[attr-defined]
            raise git.GitError(result.output.strip() or _('git commit failed'))

    async def _git_merge(self, root: Path, branch: git.Branch) -> None:
        state = await git.status(root)
        if branch.current or (not branch.remote and branch.name == state.branch):
            self.notify(_('This is the current branch: merge another one into it'), timeout=3)  # type: ignore[attr-defined]
            return
        if state.detached:
            raise git.GitError(_('No branch is checked out (detached HEAD): switch to a branch first.'))
        text = _('Merge {branch} into {current}?').format(branch=branch.name, current=state.branch)
        if await self.run_dialog(confirm(_('Merge'), text)) != Command.YES:  # type: ignore[attr-defined]
            return
        log = self._show_git_log()
        log.add(f"$ git merge {branch.name}")
        result = await git.merge(root, branch.name, on_line=log.add)
        log.add(_("[exit code {code}]").format(code=result.code))
        self._git_files_changed(None)
        if result.ok:
            self.notify(_('{branch} merged into {current}').format(branch=branch.name, current=state.branch), timeout=3)  # type: ignore[attr-defined]
            return
        if await git.merging(root):  # conflicts: Git > Changes shows them
            conflicts = len((await git.status(root)).area("conflicts"))
            await self.open_git(GitChangesWindow)
            self.notify(ngettext('{n} file in conflict: solve it, Space marks it solved, then commit',
                                 '{n} files in conflict: solve them, Space marks each solved, then commit',
                                 conflicts).format(n=conflicts), timeout=6)  # type: ignore[attr-defined]
            return
        self.raise_window(log)  # type: ignore[attr-defined]
        raise git.GitError(result.output.strip() or _('git merge failed'))

    async def _git_new_branch(self, root: Path, start: str) -> None:
        hint = _('From {start}').format(start=start[:12]) if start else _('From the current commit; it becomes the current branch')
        dialog = InputDialog(_('New branch'), _('~N~ame'), hint=hint, history="git:branch")
        while True:
            if await self.run_dialog(dialog) != Command.OK or not dialog.value:  # type: ignore[attr-defined]
                return
            if git.valid_branch_name(dialog.value):
                break
            await self.run_dialog(information(_('New branch'), _(  # type: ignore[attr-defined]
                '{name} cannot be a branch name: no spaces or symbols such as .. : ? * [ ^, and not starting with - or .').format(
                    name=dialog.value)))
            text = dialog.value
            dialog = InputDialog(_('New branch'), _('~N~ame'), text, hint=hint, history="git:branch")
        await git.create_branch(root, dialog.value, start)
        self._git_files_changed(None)
        self.notify(_('On {branch} now').format(branch=dialog.value), timeout=3)  # type: ignore[attr-defined]

    def _show_git_log(self) -> GitLogWindow:
        log = self.git_log()
        if log is None:
            log = GitLogWindow(number=self._free_number())  # type: ignore[attr-defined]
            desktop = self.desktop  # type: ignore[attr-defined]
            height = desktop.size.height if desktop is not None and desktop.size.height else 24
            log.styles.offset = (0, max(0, height - 10))
            log.styles.width = "100%"
            log.styles.height = 10
            self.insert_window(log)  # type: ignore[attr-defined]
        return log

    async def _git_remote(self, root: Path, what: str) -> None:
        """``git pull`` / ``push`` / ``fetch`` under the progress box; its output in the Git window."""
        state = await git.status(root)
        if what in ("pull", "push") and state.detached:
            raise git.GitError(_('No branch is checked out (detached HEAD): switch to a branch first.'))
        if what == "pull" and not state.upstream:
            raise git.GitError(_('{branch} has no upstream to pull from: push it first (it is set then).').format(
                branch=state.branch))
        if not await git.remotes(root):
            raise git.GitError(_('The repository has no remote: add one in a terminal (git remote add origin <url>).'))
        titles = {"pull": _('Pulling {branch}'), "push": _('Pushing {branch}'), "fetch": _('Fetching from the remotes')}
        log = self._show_git_log()
        log.add(f"$ git {what}")
        dialog = ProgressDialog(titles[what].format(branch=state.branch), [
            (_('Repository'), str(root)), (_('Branch'), where(state)), (_('Git'), "...")], width=72)

        def line(text: str) -> None:
            log.add(text)
            if text.strip():
                dialog.set(_('Git'), text.strip())

        def progress(text: str) -> None:
            dialog.set(_('Git'), text.strip())

        def verdict(result: git.Result) -> tuple[str, bool, list[tuple[str, str]]]:
            return (_("Success"), True, []) if result.ok else (_("Failed"), False, [(_('Exit code'), str(result.code))])

        job = {"pull": lambda: git.pull(root, line, progress), "push": lambda: git.push(root, state, line, progress),
               "fetch": lambda: git.fetch(root, line, progress)}[what]()
        result = await run_with_progress(self, dialog, job, verdict)
        log.add(_("[stopped]") if result is None else _("[exit code {code}]").format(code=result.code))
        if result is not None and not result.ok:
            self.raise_window(log)  # type: ignore[attr-defined]
        if what == "pull" and result is not None and result.ok:
            self._git_files_changed(None)
