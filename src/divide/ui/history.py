"""Turbo Vision's THistory: an input line remembers what was written in it.

``HistoryInput`` is the input line with its ``▐↓▌`` at the right. Down (or a
click on the arrow) opens a small list under the line with what was accepted
there before, newest first; Enter (or a click) puts one back in the line, Esc
closes the list. Each kind of line has its own history (``history_id``: file
names, texts to find, line numbers...), kept in the config so it outlives the
session. What a dialog's lines hold is remembered when it ends with anything
but Cancel (``_Dialog.end_modal``).
"""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.strip import Strip
from textual.widget import Widget
from textual_vision.constants import OptionFlag
from textual_vision.group import Group
from textual_vision.input_line import InputLine
from textual_vision.list_box import ListBox

from divide.ui.windows import WheelList

from divide import config
from divide.ui.filter import PROMPT, FilteredList

MAX_ENTRIES = 20  # per history
MAX_SHOWN = 8  # rows of the list before it scrolls


def entries(history_id: str) -> list[str]:
    data = config.load().get("history")
    found = data.get(history_id) if isinstance(data, dict) else None
    return [e for e in found if isinstance(e, str)] if isinstance(found, list) else []


def add(history_id: str, text: str) -> None:
    """``text`` at the head of the history (once: an earlier copy goes)."""
    text = text.strip()
    if not text:
        return
    data = config.load()
    histories = data.get("history") if isinstance(data.get("history"), dict) else {}
    old = [e for e in histories.get(history_id, []) if isinstance(e, str) and e != text]
    histories[history_id] = [text, *old][:MAX_ENTRIES]
    data["history"] = histories
    config.save(data)


class HistoryArrow(Widget):
    """The ``▐↓▌`` at the right of the line: black on green, its sides green on the dialog."""

    COMPONENT_CLASSES = {"history--arrow", "history--sides"}
    DEFAULT_CSS = """
    HistoryArrow { width: 3; height: 1; }
    HistoryArrow .history--arrow { color: $combo-arrow-fg; background: $combo-arrow-bg; }
    HistoryArrow .history--sides { color: $combo-sides-fg; background: $combo-sides-bg; }
    """

    def render_line(self, y: int) -> Strip:
        if y:
            return Strip.blank(self.size.width)
        sides = self.get_component_rich_style("history--sides")
        arrow = self.get_component_rich_style("history--arrow")
        return Strip(Text.assemble(("▐", sides), ("↓", arrow), ("▌", sides)).render(self.app.console))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button == 1 and isinstance(self.parent, HistoryInput):
            event.stop()
            self.parent.toggle()


class HistoryList(WheelList, FilteredList, ListBox):
    """The earlier entries, in a small blue window under the line."""

    DEFAULT_CSS = """
    HistoryList {
        position: absolute;
        border: double $divide-history-frame;
        background: $divide-history-bg;
    }
    HistoryList > .list-viewer--normal { color: $divide-history-text; background: $divide-history-bg; }
    HistoryList > .list-viewer--focused { color: $divide-history-focused; background: $divide-history-focused-bg; }
    """

    def __init__(self, items: list[str], owner: HistoryInput) -> None:
        super().__init__(items=items)
        self._all, self._shown = list(items), list(range(len(items)))
        self.owner = owner
        self.can_focus = True

    def filter_changed(self) -> None:
        """The filter in the frame's title: the popup has no room for a line."""
        self.border_title = f"{PROMPT}{self.filter_text}" if self.filter_text else ""

    def on_mount(self) -> None:
        self.focus()

    def on_blur(self) -> None:
        self.owner.close()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape" and not self.filter_text:
            event.stop()
            event.prevent_default()
            self.owner.close()
        elif self.tv_handle_key(event):
            event.stop()
            event.prevent_default()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        event.stop()
        item = self.top_item + event.y
        if event.button == 1 and 0 <= item < self.range:
            self.select_item(item)

    def select_item(self, item: int) -> None:
        self.owner.pick(self._items[item] if 0 <= item < len(self._items) else None)


class HistoryInput(Group):
    """``line`` with its history: ``▐↓▌`` at the right, Down to open it."""

    can_focus = False
    DEFAULT_CSS = """
    HistoryInput { width: 1fr; height: 1; layout: horizontal; }
    HistoryInput > InputLine { width: 1fr; }
    """

    def __init__(self, line: InputLine, history_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.line = line
        self.history_id = history_id
        self.popup: HistoryList | None = None
        self.tv_options = OptionFlag.SELECTABLE  # Tab stops here (at its line), as at any input line

    def compose(self) -> ComposeResult:
        yield self.line
        yield HistoryArrow()

    def on_key(self, event: events.Key) -> None:
        if event.key == "down" and self.popup is None:
            event.stop()
            event.prevent_default()
            self.open()

    def remember(self) -> None:
        add(self.history_id, self.line.data)

    def toggle(self) -> None:
        self.close() if self.popup is not None else self.open()

    def open(self) -> None:
        items = entries(self.history_id)
        if self.popup is not None or not items:
            return
        region = self.region
        popup = HistoryList(items, self)
        popup.styles.offset = (region.x, region.y + 1)
        popup.styles.width = region.width
        popup.styles.height = min(len(items), MAX_SHOWN) + 2
        self.popup = popup
        self.screen.mount(popup)

    def close(self) -> None:
        popup, self.popup = self.popup, None
        if popup is not None and popup.is_mounted:
            popup.remove()
        if self.is_mounted:
            self.line.tv_select_self()
            self.line.focus()

    def pick(self, text: str | None) -> None:
        if text is not None:
            self.line.data = text
            self.line.select_all()
        self.close()
