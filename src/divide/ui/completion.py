"""The completion list shown under the cursor (Turbo Vision menu look).

It never takes the focus: the editor keeps it and forwards Up/Down, PgUp/PgDn,
Enter/Tab and Esc while the list is open; everything else is typed into the
editor, and the list follows what is typed.
"""

from __future__ import annotations

from rich.segment import Segment
from textual.events import Click
from textual.strip import Strip
from textual.widget import Widget

from divide.lang.div.complete import Completion, CompletionResult


class CompletionPopup(Widget):
    MAX_ROWS = 10
    MAX_WIDTH = 60
    tv_shadow = True  # drawn with a Turbo Vision shadow (see ui.shadow)
    can_focus = False

    COMPONENT_CLASSES = {"completion--item", "completion--selected", "completion--detail", "completion--border"}
    DEFAULT_CSS = """
    CompletionPopup {
        overlay: screen;
        position: absolute;
        width: auto; height: auto;
        background: $surface;
    }
    CompletionPopup .completion--border { color: $text; }
    CompletionPopup .completion--item { color: $text; }
    CompletionPopup .completion--detail { color: $text-muted; }
    CompletionPopup .completion--selected { color: $text; background: $accent; }
    """

    def __init__(self, owner) -> None:
        super().__init__()
        self.owner = owner  # the editor that opened it
        self.result: CompletionResult | None = None
        self.explicit = False
        self.index = 0
        self.top = 0

    # ------------------------------------------------------------- content
    @property
    def items(self) -> list[Completion]:
        return self.result.items if self.result else []

    def show(self, result: CompletionResult, *, explicit: bool, at: tuple[int, int], screen_size: tuple[int, int]) -> None:
        same = self.result is not None and self.result.start == result.start
        current = self.items[self.index].label if same and self.items else None
        self.result = result
        self.explicit = explicit
        labels = [c.label for c in result.items]
        self.index = labels.index(current) if current in labels else 0
        self.top = 0
        self._scroll()
        width, height = self._box_size()
        x, y = at
        sw, sh = screen_size
        x = max(0, min(x - 1, sw - width - 2))
        y = y + 1 if y + 1 + height <= sh - 1 else max(1, y - height)
        self.styles.width = width
        self.styles.height = height
        self.styles.offset = (x, y)
        self.display = True
        self.refresh(layout=True)

    def _label_width(self) -> int:
        return max((len(c.label) for c in self.items), default=0)

    def _box_size(self) -> tuple[int, int]:
        detail = max((len(c.detail) for c in self.items), default=0)
        inner = self._label_width() + (detail + 2 if detail else 0) + 2
        return min(self.MAX_WIDTH, max(16, inner)) + 2, min(self.MAX_ROWS, len(self.items)) + 2

    # ------------------------------------------------------------ movement
    def move(self, delta: int) -> None:
        if not self.items:
            return
        self.index = max(0, min(len(self.items) - 1, self.index + delta))
        self._scroll()
        self.refresh()

    def page(self, direction: int) -> None:
        self.move(direction * (self.MAX_ROWS - 1))

    def _scroll(self) -> None:
        rows = self.MAX_ROWS
        if self.index < self.top:
            self.top = self.index
        elif self.index >= self.top + rows:
            self.top = self.index - rows + 1

    @property
    def selected(self) -> Completion | None:
        return self.items[self.index] if 0 <= self.index < len(self.items) else None

    # ------------------------------------------------------------- drawing
    def render_line(self, y: int) -> Strip:
        width, height = self.size
        if width < 4:
            return Strip.blank(width)
        border = self.get_component_rich_style("completion--border")
        inner = width - 2
        if y == 0:
            return Strip([Segment("┌" + "─" * inner + "┐", border)])
        if y == height - 1:
            more = len(self.items) > self.MAX_ROWS
            info = f" {self.index + 1}/{len(self.items)} " if more else ""
            line = "─" * max(0, inner - len(info) - 1) + info + "─" if info else "─" * inner
            return Strip([Segment("└" + line[:inner] + "┘", border)])
        row = self.top + y - 1
        if row >= len(self.items):
            return Strip([Segment("│", border), Segment(" " * inner, self.get_component_rich_style("completion--item")), Segment("│", border)])
        item = self.items[row]
        selected = row == self.index
        style = self.get_component_rich_style("completion--selected" if selected else "completion--item")
        dstyle = style if selected else self.get_component_rich_style("completion--detail")
        label_w = min(self._label_width(), inner - 2)
        label = item.label[:label_w].ljust(label_w)
        detail_room = inner - label_w - 4
        detail = item.detail[: max(0, detail_room)] if detail_room > 0 else ""
        gap = inner - 1 - len(label) - len(detail) - 1
        segments = [Segment("│", border), Segment(" " + label, style)]
        if detail:
            segments += [Segment(" " * gap, style), Segment(detail, dstyle), Segment(" ", style)]
        else:
            segments.append(Segment(" " * (inner - 1 - len(label)), style))
        segments.append(Segment("│", border))
        return Strip(segments)

    def on_click(self, event: Click) -> None:
        event.stop()
        row = self.top + event.y - 1
        if 0 <= row < len(self.items):
            self.index = row
            self.owner.accept_completion()
