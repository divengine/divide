"""A filter over a list or a tree: one line above it, typed into from the list itself.

With the list (or tree) focused, a letter, a digit or a sign goes to the filter,
Backspace takes one back, Escape empties it; only the items that hold the filter
(a substring, case ignored) stay. Space keeps its job (fold, choose).

- ``FilteredList``: a ListBox mixin. ``focused``, ``focus_item()`` and
  ``select_item()`` stay the ListBox's own (the rows shown); ``current`` is the
  focused row as an index of the whole list, ``original()`` turns a shown row
  into one, and ``focus_original()`` puts the bar on an item (emptying the
  filter when it hides it).
- ``FilteredTree``: a Tree mixin. Shown: what matches, the nodes above it, and
  what hangs from a node that matches. ``filter_text_of(node)`` is what is
  matched (the label by default).
- ``Filtered(widget)``: the filter line above ``widget``, in a container.
"""

from __future__ import annotations

from divide.i18n import _

from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

PROMPT = "» "


def matches(text: str, query: str) -> bool:
    return not query or query.lower() in text.lower()


def _typed(event: events.Key) -> str | None:
    """The character a key types into the filter (None: not one of ours)."""
    char = event.character
    if char and len(char) == 1 and char.isprintable() and char != " " and event.key not in ("enter", "tab"):
        return char
    return None


class FilterLine(Static):
    """``» filter (3/40)``, or a dim ``» type to filter`` when empty, in the list's colours."""

    DEFAULT_CSS = "FilterLine { height: 1; width: 1fr; padding: 0 1; }"

    def __init__(self, target: Widget) -> None:
        super().__init__("", markup=False)
        self.target = target

    def on_mount(self) -> None:
        self.call_after_refresh(self.show)
        theme = getattr(self.app, "theme_changed_signal", None)
        if theme is not None:
            theme.subscribe(self, lambda _theme: self.call_after_refresh(self.show))

    def _base(self) -> Style:
        target = self.target
        if hasattr(target, "get_component_rich_style"):
            try:
                return target.get_component_rich_style("list-viewer--normal")
            except KeyError:
                pass
        bg, fg = target.styles.background, target.styles.color
        return Style(bgcolor=bg.rich_color if bg.a else None, color=fg.rich_color if fg.a else None)

    def show(self) -> None:
        base = self._base()
        if base.bgcolor is not None:
            self.styles.background = base.bgcolor.name if base.bgcolor.name.startswith("#") else base.bgcolor.triplet.hex
        query = getattr(self.target, "filter_text", "")
        if not query:
            self.update(Text(PROMPT + _("type to filter"), Style(color=base.color, dim=True)))
            return
        shown, total = self.target.filter_counts()  # type: ignore[attr-defined]
        self.update(Text.assemble((PROMPT, Style(color=base.color, dim=True)), (query, Style(color=base.color, bold=True)),
                                  (f"  {shown}/{total}", Style(color=base.color, dim=True))))


class Filtered(Vertical):
    """The filter line, then ``widget``; ``fill``: take the room left (1fr), else as tall as the widget."""

    DEFAULT_CSS = """
    Filtered { width: 1fr; height: auto; }
    Filtered.-fill { height: 1fr; }
    """

    def __init__(self, widget: Widget, fill: bool = True, **kwargs) -> None:
        super().__init__(**kwargs)
        self.widget = widget
        self.line = FilterLine(widget)
        widget.filter_line = self.line  # type: ignore[attr-defined]
        self.set_class(fill, "-fill")

    def compose(self) -> ComposeResult:
        yield self.line
        yield self.widget


class _Filter:
    """What both mixins share: the text, the keys, the line."""

    filter_text: str = ""
    filter_line: FilterLine | None = None

    def set_filter(self, text: str) -> None:
        if text == self.filter_text:
            return
        self.filter_text = text
        self.apply_filter()
        self.filter_changed()

    def filter_changed(self) -> None:
        """Show the filter (on its line; a list without one can show it elsewhere)."""
        if self.filter_line is not None:
            self.filter_line.show()

    def apply_filter(self) -> None:
        raise NotImplementedError

    def filter_counts(self) -> tuple[int, int]:
        raise NotImplementedError

    def filter_key(self, event: events.Key) -> bool:
        """The key edits the filter (and is done with)."""
        char = _typed(event)
        if char is not None:
            self.set_filter(self.filter_text + char)
        elif event.key == "backspace" and self.filter_text:
            self.set_filter(self.filter_text[:-1])
        elif event.key == "escape" and self.filter_text:
            self.set_filter("")
        else:
            return False
        event.stop()
        event.prevent_default()
        return True


class FilteredList(_Filter):
    """ListBox mixin (before ListBox in the bases): the items that hold the filter."""

    _all: list[str]
    _shown: list[int]

    def set_list(self, items: list[str]) -> None:
        self._all = list(items)
        self._refilter(keep=None)

    def _refilter(self, keep: int | None) -> None:
        self._shown = [i for i, text in enumerate(self._all) if matches(text, self.filter_text)]
        super().set_list([self._all[i] for i in self._shown])  # type: ignore[misc]
        if keep is not None and keep in self._shown:
            super().focus_item(self._shown.index(keep))  # type: ignore[misc]
        self.filter_changed()

    def apply_filter(self) -> None:
        self._refilter(keep=self.current if getattr(self, "_shown", None) else None)

    def filter_counts(self) -> tuple[int, int]:
        return len(self._shown), len(self._all)

    @property
    def all_items(self) -> list[str]:
        return list(getattr(self, "_all", []))

    def original(self, shown: int) -> int:
        """The index in the whole list of a row shown (-1: none)."""
        rows = getattr(self, "_shown", None)
        if rows is None:
            return shown
        return rows[shown] if 0 <= shown < len(rows) else -1

    @property
    def current(self) -> int:
        """The focused item, as an index of the whole list (-1: nothing shown)."""
        return self.original(self.focused)  # type: ignore[attr-defined]

    def focus_original(self, index: int) -> None:
        """The bar on an item of the whole list (the filter is emptied if it hides it)."""
        rows = getattr(self, "_shown", None)
        if rows is None:
            self.focus_item(index)  # type: ignore[attr-defined]
            return
        if index not in rows and self.filter_text:
            self.filter_text = ""
            self._refilter(keep=None)
            rows = self._shown
        if index in rows:
            self.focus_item(rows.index(index))  # type: ignore[attr-defined]

    def tv_handle_key(self, event: events.Key) -> bool:
        if self.filter_key(event):
            return True
        return super().tv_handle_key(event)  # type: ignore[misc]


class FilteredTree(_Filter):
    """Tree mixin (before Tree in the bases): what matches, what is above it, and
    what hangs from a node that matches (folds still fold, below a match)."""

    def filter_text_of(self, node) -> str:
        label = node.label
        return label.plain if isinstance(label, Text) else str(label)

    def apply_filter(self) -> None:
        self._invalidate()  # type: ignore[attr-defined]
        self.refresh()  # type: ignore[attr-defined]
        if self.filter_text:
            self.call_after_refresh(self._cursor_on_a_match)  # type: ignore[attr-defined]

    def _cursor_on_a_match(self) -> None:
        node = self.cursor_node  # type: ignore[attr-defined]
        if node is not None and node._line >= 0 and matches(self.filter_text_of(node), self.filter_text):
            return
        for line in range(self.last_line + 1):  # type: ignore[attr-defined]
            candidate = self.get_node_at_line(line)  # type: ignore[attr-defined]
            if candidate is not None and matches(self.filter_text_of(candidate), self.filter_text):
                self.move_cursor(candidate, animate=False)  # type: ignore[attr-defined]
                return

    def _all_nodes(self):
        stack = list(self.root._children)  # type: ignore[attr-defined]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(node._children)

    def filter_counts(self) -> tuple[int, int]:
        nodes = list(self._all_nodes())
        return sum(matches(self.filter_text_of(n), self.filter_text) for n in nodes), len(nodes)

    def _build(self) -> None:
        if not self.filter_text:
            super()._build()  # type: ignore[misc]
            return
        from textual.geometry import Size
        from textual.widgets._tree import _TreeLine

        query = self.filter_text
        hit: dict[int, bool] = {}

        def holds(node) -> bool:  # it, or something below it, matches
            key = id(node)
            if key not in hit:
                hit[key] = matches(self.filter_text_of(node), query) or any(holds(c) for c in node._children)
            return hit[key]

        for node in self._all_nodes():
            node._line = -1
        lines: list = []

        def add(path: list, node, last: bool, inside: bool) -> None:
            child_path = [*path, node]
            node._line = len(lines)
            lines.append(_TreeLine(child_path, last))
            own = inside or matches(self.filter_text_of(node), query)
            children = [c for c in node._children if own or holds(c)]
            if node._expanded or (not own and children):
                for index, child in enumerate(children):
                    add(child_path, child, index == len(children) - 1, own)

        top = [n for n in self.root._children if holds(n)]  # type: ignore[attr-defined]
        for index, node in enumerate(top):
            add([], node, index == len(top) - 1, False)
        self._tree_lines_cached = lines
        width = max((self.get_label_width(line.node) + line._get_guide_width(self.guide_depth, self.show_root)  # type: ignore[attr-defined]
                     for line in lines), default=self.size.width)  # type: ignore[attr-defined]
        self.virtual_size = Size(width, len(lines))  # type: ignore[attr-defined]
        if self.cursor_line != -1:  # type: ignore[attr-defined]  (as Tree._build: the bar stays on its node)
            if self.cursor_node is not None:  # type: ignore[attr-defined]
                self.cursor_line = self.cursor_node._line  # type: ignore[attr-defined]
            if self.cursor_line >= len(lines):  # type: ignore[attr-defined]
                self.cursor_line = -1  # type: ignore[attr-defined]

    def on_key(self, event: events.Key) -> None:
        self.filter_key(event)
