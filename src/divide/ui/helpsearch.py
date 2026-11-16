"""Help > Search: the help books by words, ranked (see divide.manual.fulltext).

A line to type in and, as you type, the sections of the books that have the
words, best first: ``Breakpoints · Debugging PHP``, the words found lit. The
pane below shows the section's book and the sentence where the words are.
Up/Down move the bar while the keys stay in the line; Enter (or a double
click) opens the help at that section, Esc closes.
"""

from __future__ import annotations

from divide.i18n import _

import re

from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from textual_vision.constants import Command
from textual_vision.input_line import InputLine

from divide import manual, themes
from divide.manual import fulltext
from divide.ui.dialogs import _Dialog
from divide.ui.palette import Item, PaletteList
from divide.ui.windows import PassiveScrollBar

TITLE = _('Search the help')
HINT = _('Type words · Enter open · Esc close')


def lit(label: str, words: list[str]) -> tuple[int, ...]:
    """The offsets in ``label`` of the words typed (each a word's start, the last one a prefix)."""
    offsets: set[int] = set()
    lower = label.lower()
    for word in words:
        for m in re.finditer(rf"\b{re.escape(word)}", lower):
            offsets.update(range(m.start(), m.end()))
    return tuple(sorted(offsets))


class HelpSearchDialog(_Dialog):
    """``chosen`` holds the topic (``book:Page#anchor``) once it ends with OK."""

    DEFAULT_CSS = """
    HelpSearchDialog { width: 76; height: 22; }
    HelpSearchDialog > .tv-window-content { margin: 1 1; }
    HelpSearchDialog InputLine { width: 1fr; margin: 0 1; }
    HelpSearchDialog .hs-body { height: 1fr; margin: 1 1 0 1; }
    HelpSearchDialog PaletteList { width: 1fr; height: 1fr; }
    HelpSearchDialog .hs-bar { width: 1; height: 1fr; background: $divide-list-bg; }
    HelpSearchDialog .hs-bar .scrollbar--arrow, HelpSearchDialog .hs-bar .scrollbar--track, HelpSearchDialog .hs-bar .scrollbar--thumb {
        color: $divide-list-scroll; background: $divide-list-bg;
    }
    HelpSearchDialog .hs-info { height: 3; margin: 0 1; padding: 0 1; color: $divide-info-text; background: $divide-info-bg; }
    """

    def __init__(self, text: str = "") -> None:
        super().__init__(title=TITLE)
        self.input = InputLine(max_len=256)
        self.input.data = text
        self.list = PaletteList(self)
        self.bar = PassiveScrollBar(classes="hs-bar")
        self.list.v_scroll_bar = self.bar
        self.info = Static("", classes="hs-info", markup=False)
        self.hits: list[fulltext.Hit] = []
        self.chosen: str | None = None
        self._shown_at = -1

    def compose_content(self) -> ComposeResult:
        yield self.input
        with Horizontal(classes="hs-body"):
            yield self.list
            yield self.bar
        yield self.info

    def on_mount(self) -> None:
        self.call_after_refresh(self._start)

    def _start(self) -> None:
        self.input._cursor_pos = len(self.input.data)
        self.input.refresh()
        self.refilter()

    def refilter(self) -> None:
        text = self.input.data
        self.hits = fulltext.search(text) if text.strip() else []
        words = fulltext.words(text)
        books = {b.id: b.title for b in manual.books()}
        rows = []
        for hit in self.hits:
            label = hit.label
            key = books.get(hit.book, hit.book) if hit.book != manual.DEFAULT else ""
            rows.append(Item(label, hit.target, key=key, name_from=0, offsets=lit(label, words)))
        self.list.show(rows)
        self._shown_at = -1
        self.show_info()

    def show_info(self) -> None:
        index = self.list.focused
        if index == self._shown_at:
            return
        self._shown_at = index
        if not self.hits:
            self.info.update(HINT if not self.input.data.strip() else _('Nothing found: fewer or other words'))
            return
        hit = self.hits[index] if 0 <= index < len(self.hits) else self.hits[0]
        lit_style = themes.current().style("list-match-focused", bold=True)
        text = Text()
        book = manual.book(hit.book)
        text.append(f"{book.title if book else hit.book}: {hit.title}\n")
        for n, part in enumerate(re.split(f"[{fulltext.MARK_START}{fulltext.MARK_END}]", hit.snippet)):
            text.append(part, style=lit_style if n % 2 else Style())
        self.info.update(text)

    def on_input_line_changed(self, message: InputLine.Changed) -> None:
        message.stop()
        self.refilter()

    def accept(self, index: int) -> None:
        if 0 <= index < len(self.hits):
            self.chosen = self.hits[index].target
            self.end_modal(Command.OK)

    def on_key(self, event: events.Key) -> None:
        if event.key in ("up", "down", "pageup", "pagedown") and self.input.has_focus:
            event.stop()
            event.prevent_default()
            self.list.tv_handle_key(event)
            self.show_info()
        elif event.key == "enter":
            event.stop()
            event.prevent_default()
            self.accept(self.list.focused)
        elif self.list.has_focus and event.character and event.character.isprintable() and len(event.character) == 1:
            event.stop()
            event.prevent_default()
            self.input.tv_select_self()
            self.input.focus()
            self.input.tv_handle_key(event)

    def on_click(self, event: events.Click) -> None:
        self.show_info()
