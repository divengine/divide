"""The help window: the manual inside divide, in the colours of Borland's help.

Black on cyan, cross references in yellow, the selected one yellow on blue,
as in Turbo Pascal and Borland Pascal. Tab and Shift+Tab move between the
cross references, Enter (or a click) follows one, Alt+F1 goes back,
Esc closes the window.
"""

from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.geometry import Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual_vision.constants import OptionFlag
from textual_vision.group import TVViewMixin

from divide import manual
from divide.editor.theme import CGA
from divide.ui.windows import _TVWindow

_CYAN = CGA["cyan"]
STYLES = {
    "text": Style(color=CGA["black"], bgcolor=_CYAN),
    "bold": Style(color=CGA["white"], bgcolor=_CYAN, bold=True),
    "code": Style(color=CGA["blue"], bgcolor=_CYAN),
    "link": Style(color=CGA["yellow"], bgcolor=_CYAN, bold=True),
    "url": Style(color=CGA["black"], bgcolor=_CYAN, underline=True),
    "title": Style(color=CGA["white"], bgcolor=_CYAN, bold=True),
    "heading": Style(color=CGA["white"], bgcolor=_CYAN, bold=True),
    "head": Style(color=CGA["white"], bgcolor=_CYAN, bold=True),
    "rule": Style(color=CGA["lightgray"], bgcolor=_CYAN),
    "selected": Style(color=CGA["yellow"], bgcolor=CGA["blue"], bold=True),
}

HINT = "Tab next link · Enter go · Alt+F1 back · Shift+F1 index · Esc close"


class HelpView(ScrollView, TVViewMixin):
    """A help topic, scrollable, with its cross references."""

    DEFAULT_CSS = """
    HelpView {
        width: 1fr; height: 1fr;
        scrollbar-size: 1 1;
        scrollbar-background: $secondary;
        scrollbar-background-hover: $secondary;
        scrollbar-background-active: $secondary;
        scrollbar-color: $background;
        scrollbar-color-hover: $primary;
        scrollbar-color-active: $primary;
        scrollbar-corner-color: $secondary;
    }
    """
    can_focus = True

    BINDINGS = [
        Binding("up", "scroll_up", show=False),
        Binding("down", "scroll_down", show=False),
        Binding("pageup", "page_up", show=False),
        Binding("pagedown", "page_down", show=False),
        Binding("home", "scroll_home", show=False),
        Binding("end", "scroll_end", show=False),
    ]

    class Follow(Message):
        def __init__(self, target: str) -> None:
            super().__init__()
            self.target = target

    def __init__(self) -> None:
        super().__init__()
        self.tv_options = OptionFlag.SELECTABLE
        self.topic: manual.Topic | None = None
        self.name_ = manual.CONTENTS
        self.selected: int | None = None  # index into topic.links
        self._width = 0

    # ------------------------------------------------------------ content
    def show(self, name: str, anchor: str | None = None, selected: int | None = None, top: int | None = None) -> bool:
        width = self._text_width()
        topic = manual.layout(name, width)
        if topic is None:
            return False
        self.name_, self.topic, self._width = name, topic, width
        self.virtual_size = Size(width, len(topic.lines))
        links = self._links()
        self.selected = selected if selected is not None and selected in links else (links[0] if links else None)
        y = top if top is not None else topic.anchors.get(anchor or "", 0)
        if anchor and anchor in topic.anchors:
            # select the first link at or below the heading
            after = [i for i in links if topic.links[i].places[0][0] >= y]
            if after:
                self.selected = after[0]
        self.call_after_refresh(lambda: self.scroll_to(y=y, animate=False))
        self.refresh()
        return True

    def _view_width(self) -> int:
        """Columns for text: the scrollbar is not one of them."""
        return self.scrollable_content_region.width or self.size.width or 80

    def _text_width(self) -> int:
        # a margin each side and the scrollbar's column, there or not yet
        return max(20, (self.size.width or 80) - 3)

    def _links(self) -> list[int]:
        """Followable links in reading order."""
        if self.topic is None:
            return []
        return sorted((i for i, link in enumerate(self.topic.links) if link.places), key=lambda i: self.topic.links[i].places[0][:2])

    def on_resize(self, event: events.Resize) -> None:
        if self.topic is not None and self._text_width() != self._width:
            first = self.scroll_offset.y
            self.show(self.name_, selected=self.selected, top=first)

    # ------------------------------------------------------------ drawing
    def render_line(self, y: int) -> Strip:
        width = self._view_width()
        row = self.scroll_offset.y + y
        base = STYLES["text"]
        if self.topic is None or not 0 <= row < len(self.topic.lines):
            return Strip([Segment(" " * width, base)])
        segments = [Segment(" ", base)]
        used = 1
        for span in self.topic.lines[row]:
            style = STYLES.get(span.style, base)
            if span.link is not None and span.link == self.selected:
                style = STYLES["selected"]
            segments.append(Segment(span.text, style))
            used += len(span.text)
        if used < width:
            segments.append(Segment(" " * (width - used), base))
        return Strip(segments).crop(0, width)

    # ------------------------------------------------------------ links
    def _move(self, step: int) -> None:
        links = self._links()
        if not links:
            return
        if self.selected not in links:
            self.selected = links[0]
        else:
            self.selected = links[(links.index(self.selected) + step) % len(links)]
        self._reveal()
        self.refresh()

    def _reveal(self) -> None:
        if self.topic is None or self.selected is None:
            return
        line = self.topic.links[self.selected].places[0][0]
        top, height = self.scroll_offset.y, self.size.height
        if not top <= line < top + height:
            self.scroll_to(y=max(0, line - height // 3), animate=False)

    def action_next_link(self) -> None:
        self._move(1)

    def action_prev_link(self) -> None:
        self._move(-1)

    def action_follow(self) -> None:
        if self.topic is not None and self.selected is not None:
            self.post_message(self.Follow(self.topic.links[self.selected].target))

    def action_scroll_up(self) -> None:
        self.scroll_relative(y=-1, animate=False)

    def action_scroll_down(self) -> None:
        self.scroll_relative(y=1, animate=False)

    def action_page_up(self) -> None:
        self.scroll_relative(y=-max(1, self.size.height - 1), animate=False)

    def action_page_down(self) -> None:
        self.scroll_relative(y=max(1, self.size.height - 1), animate=False)

    def action_scroll_home(self) -> None:
        self.scroll_to(y=0, animate=False)

    def action_scroll_end(self) -> None:
        self.scroll_to(y=self.virtual_size.height, animate=False)

    def on_key(self, event: events.Key) -> None:
        # before the window's Group, which takes Tab to cycle its views
        action = {"tab": self.action_next_link, "shift+tab": self.action_prev_link, "enter": self.action_follow}.get(event.key)
        if action is not None:
            event.stop()
            event.prevent_default()
            action()

    def link_at(self, x: int, y: int) -> int | None:
        if self.topic is None:
            return None
        row, col = self.scroll_offset.y + y, x - 1
        for i, link in enumerate(self.topic.links):
            for line, x0, x1 in link.places:
                if line == row and x0 <= col < x1:
                    return i
        return None

    def on_click(self, event: events.Click) -> None:
        self.focus()
        hit = self.link_at(event.x, event.y)
        if hit is not None:
            self.selected = hit
            self.refresh()
            self.action_follow()


class HelpWindow(_TVWindow):
    """The manual: topics with cross references, a history to go back."""

    HINT = HINT
    DEFAULT_CSS = f"""
    HelpWindow {{ background: {_CYAN}; }}
    HelpWindow IndicatorFrame .frame--active {{ color: {CGA["white"]}; }}
    HelpWindow IndicatorFrame .frame--passive {{ color: {CGA["lightgray"]}; }}
    """
    BINDINGS = [
        Binding("alt+f1,backspace", "back", show=False),
        Binding("escape", "close", show=False),
    ]

    def __init__(self, target: str = manual.CONTENTS, number: int = 0) -> None:
        super().__init__("Help", number=number)
        self.view = HelpView()
        self._first = target
        self.history: list[tuple[str, int | None, int]] = []  # (topic, selected link, top line)

    def compose_content(self) -> ComposeResult:
        yield self.view

    def on_mount(self) -> None:
        self.call_after_refresh(self.open, self._first, False)
        self.call_after_refresh(self.view.focus)

    def open(self, target: str, remember: bool = True) -> bool:
        """Show ``Page`` or ``Page#anchor``; the current topic goes to the history."""
        name, _, anchor = target.partition("#")
        name = name or self.view.name_
        if remember and self.view.topic is not None:
            self.history.append((self.view.name_, self.view.selected, self.view.scroll_offset.y))
        if not self.view.show(name, anchor or None):
            if remember and self.history:
                self.history.pop()
            return False
        self.title = f"Help: {manual.title_of(name)}"
        return True

    def on_help_view_follow(self, message: HelpView.Follow) -> None:
        message.stop()
        self.open(message.target)

    def action_back(self) -> None:
        if not self.history:
            return
        name, selected, top = self.history.pop()
        self.view.show(name, selected=selected, top=top)
        self.title = f"Help: {manual.title_of(name)}"

    def action_close(self) -> None:
        self.app.close_window(self)  # type: ignore[attr-defined]
