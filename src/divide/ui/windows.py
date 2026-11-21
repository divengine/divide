"""Turbo Vision windows of the IDE: editor windows and the project tree."""

from __future__ import annotations

from divide.i18n import _

import asyncio
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.await_complete import AwaitComplete
from textual.binding import Binding
from textual.containers import Container
from textual.message import Message
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import DirectoryTree
from textual.widgets._directory_tree import DirEntry
from textual.widgets._tree import TOGGLE_STYLE
from textual_vision.constants import Command, OptionFlag, WindowFlag
from textual_vision.events import CommandMessage
from textual_vision.frame import Frame
from textual_vision.group import TVViewMixin
from textual_vision.list_box import ListBox
from textual_vision.list_viewer import ListViewer
from textual_vision.scroll_bar import ScrollBar as TVScrollBar
from textual_vision.window import Window

from divide.editor.div_editor import DivEditor
from divide import themes
from divide import outline as outline_mod
from divide.lang import language_of
from divide.editor.theme import OUTPUT
from divide.lang.div.complete import CARET, CompletionResult, complete
from divide.ui.completion import CompletionPopup, InfoPopup
from divide.ui import icons as icons_mod
from divide.ui.filter import Filtered, FilteredList, FilteredTree

UNTITLED = "NONAME{:02d}.TPL"


def _overlay(strip: Strip, x: int, text: str, style: Style) -> Strip:
    """Write ``text`` over ``strip`` starting at cell ``x``."""
    width = strip.cell_length
    if x < 0 or x + len(text) > width:
        return strip
    return Strip.join([strip.crop(0, x), Strip([Segment(text, style)]), strip.crop(x + len(text), width)])


# Textual runs the handler of every class in the MRO unless prevent_default()
# is called, so handlers here never call super(): they prevent_default() when
# they replace the base behaviour and simply return when they extend it.


class RuleFrame(Frame):
    """A frame that joins the inner rules of its window (VRule / HRule) in Ts."""

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        width, height = self.size
        if width < 2 or height < 2:
            return strip
        style = self.get_component_rich_style("frame--active" if self.active else "frame--passive")
        return self._junctions(strip, y, width, height, style)

    # Inner rules (VRule / HRule) meet the border in a T: ╤ ╧ ╟ ╢ (┬ ┴ ├ ┤ when passive).
    def _junctions(self, strip: Strip, y: int, width: int, height: int, style: Style) -> Strip:
        window = self.parent
        if window is None or not self.region.width:
            return strip
        ox, oy = self.region.x, self.region.y
        h, v = self._chars["h"], self._chars["v"]
        top, bottom, left, right = ("╤", "╧", "╟", "╢") if self.active else ("┬", "┴", "├", "┤")
        for rule in window.query(Rule):
            r = rule.region
            if not r.width or not r.height:
                continue
            if isinstance(rule, VRule):
                x = r.x - ox
                if y == 0 and r.y - oy == 1:
                    strip = _put(strip, x, top, h, style)
                elif y == height - 1 and r.bottom - oy == height - 1:
                    strip = _put(strip, x, bottom, h, style)
            elif r.y - oy == y:
                if r.x - ox == 1:
                    strip = _put(strip, 0, left, v, style)
                if r.right - ox == width - 1:
                    strip = _put(strip, width - 1, right, v, style)
        return strip

    def watch_active(self, active: bool) -> None:
        if self.parent is not None:
            for rule in self.parent.query(Rule):
                rule.refresh()
            update = getattr(self.parent, "update_scroll_bars", None)
            if update is not None:
                update()  # only the active window shows its scroll bars


class IndicatorFrame(RuleFrame):
    """Frame with the window number on the top border and a Borland-style
    ``* 12:5`` indicator (modified flag, line:column) on the bottom border."""

    def __init__(self, *args, number: int = 0, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.number = number
        self.indicator = ""

    def set_indicator(self, text: str) -> None:
        if text != self.indicator:
            longer = len(text) != len(self.indicator)
            self.indicator = text
            self.refresh()
            update = getattr(self.parent, "update_scroll_bars", None)
            if longer and update is not None:
                update()  # the horizontal bar starts after the indicator

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        width, height = self.size
        if width < 12 or height < 2:
            return strip
        style = self.get_component_rich_style("frame--active" if self.active else "frame--passive")
        if y == 0 and 0 < self.number < 10:
            zoom = self._zoom_icon_range(width)
            x = (zoom[0] if zoom else width - 1) - 2
            strip = _overlay(strip, x, str(self.number), style)
        elif y == height - 1 and self.indicator:
            strip = _overlay(strip, 2, f" {self.indicator} ", style)
        return strip


def _put(strip: Strip, x: int, char: str, over: str, style: Style) -> Strip:
    """``char`` at ``x`` only where the border shows its plain line (not a title or icon)."""
    if 0 <= x < strip.cell_length and strip.crop(x, x + 1).text == over:
        return _overlay(strip, x, char, style)
    return strip


class Rule(Widget):
    """An inner dividing line of a window, drawn like its frame (single line).

    Where a rule meets the frame, the frame draws the T (see IndicatorFrame);
    where an HRule meets a VRule, the VRule draws it."""

    def _frame(self) -> Frame | None:
        node = self.parent
        while node is not None and not isinstance(node, Window):
            node = node.parent
        if node is None:
            return None
        frames = node.query(Frame)  # none while its window is being taken off the desktop
        return frames.first() if frames else None

    def _line_style(self) -> Style:
        frame = self._frame()
        base = self.rich_style
        if frame is None:
            return base
        color = frame.get_component_rich_style("frame--active" if frame.active else "frame--passive").color
        return base + Style(color=color)

    def on_resize(self) -> None:
        # the regions settle after this event: redraw the Ts once they have
        self.call_after_refresh(self._refresh_joins)

    def _refresh_joins(self) -> None:
        frame = self._frame()
        if frame is not None:
            frame.refresh()
            frame.parent.query(VRule).refresh()


class VRule(Rule):
    DEFAULT_CSS = "VRule { width: 1; height: 1fr; }"

    def render_line(self, y: int) -> Strip:
        r = self.region
        row = r.y + y
        left = right = False
        node = self.parent
        while node is not None and not isinstance(node, Window):
            node = node.parent
        for rule in node.query(HRule) if node is not None else ():
            hr = rule.region
            if hr.height and hr.y == row:
                left |= hr.right == r.x
                right |= hr.x == r.right
        char = "┼" if left and right else "┤" if left else "├" if right else "│"
        return Strip([Segment(char, self._line_style())])


class HRule(Rule):
    DEFAULT_CSS = "HRule { height: 1; width: 1fr; }"

    def render_line(self, y: int) -> Strip:
        return Strip([Segment("─" * self.size.width, self._line_style())])


class WheelList:
    """The mouse wheel on a Turbo Vision list (a ListViewer, which draws its own rows and is not one of
    Textual's scrolling views): a notch moves the bar three rows, as the list's scroll bar moves it."""

    WHEEL_ROWS = 3

    def _wheel(self, event, rows: int) -> None:
        event.stop()
        event.prevent_default()
        count = self.range  # type: ignore[attr-defined]
        if count:
            self.focus_item(max(0, min(count - 1, self.focused + rows)))  # type: ignore[attr-defined]
            self.refresh()  # type: ignore[attr-defined]

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self._wheel(event, self.WHEEL_ROWS)

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self._wheel(event, -self.WHEEL_ROWS)


class PassiveScrollBar(TVScrollBar):
    """textual-vision's TScrollBar (▲ ▒ ■ ▼, ◄ ►) that never takes the focus:
    a click on it scrolls its view and leaves the focus where it was."""

    # as Textual's own scroll bars: a click on one does not move the focus (to the window)
    DEFAULT_CLASSES = "-textual-system"

    def __init__(self, horizontal: bool = False, **kwargs) -> None:
        super().__init__(horizontal=horizontal, **kwargs)
        self.tv_options = OptionFlag(0)
        self.can_focus = False

    def tv_select_self(self) -> None:
        pass


class FrameScrollBar(PassiveScrollBar):
    """Turbo Vision's standard scroll bar: drawn over the window's border.

    As ``TWindow::standardScrollBar`` does, the vertical bar takes the right
    border and the horizontal one the bottom border (after the indicator, up to
    the resize corner), so the text keeps the column and the row a bar inside
    the window would take. Only the active window shows them, and only on an
    axis there is something to scroll. The bar is textual-vision's port of
    TScrollBar (▲ ▒ ■ ▼, ◄ ►): arrows a line, the track a page, the ■ dragged.
    """

    DEFAULT_CSS = """
    FrameScrollBar { layer: bars; position: absolute; display: none; width: 1; height: 1; }
    """

    def __init__(self, horizontal: bool = False) -> None:
        super().__init__(horizontal=horizontal)
        self.view: Widget | None = None
        self.shown = False  # the window wants the bar (active, on the border)

    def get_component_rich_style(self, *names: str, partial: bool = False) -> Style:
        # the border's colours, whatever the window's palette
        frame = self.parent.frame if isinstance(self.parent, Window) else None
        if frame is None:
            return super().get_component_rich_style(*names, partial=partial)
        return frame.get_component_rich_style("frame--active")

    def sync(self, max_val: int, page: int, value: int) -> None:
        """The view's state, without scrolling it back."""
        self._min_val, self._max_val = 0, max(0, max_val)
        self._page_step, self._arrow_step = max(1, page), 1
        self.set_reactive(TVScrollBar.value, max(0, min(value, self._max_val)))
        self.update_display()
        self.refresh()

    def set_params(self, min_val: int, max_val: int, page_step: int = 1, arrow_step: int = 1) -> None:
        super().set_params(min_val, max_val, page_step, arrow_step)  # a list keeps its bar up to date itself
        self.update_display()
        self.refresh()

    def update_display(self) -> None:
        self.display = self.shown and self._max_val > self._min_val

    def scroll_to_value(self, value: int) -> None:
        view = self.view
        if isinstance(view, ListViewer):
            view.scroll_to_value(value)
        elif view is not None:
            if self.horizontal:
                view.scroll_to(x=value, animate=False)
            else:
                view.scroll_to(y=value, animate=False)


HBAR_AFTER_INDICATOR = 18  # TEditWindow's: the line:column indicator is before it


class _TVWindow(Window):
    """Window whose frame is an IndicatorFrame and whose content is composed.

    Its scrolling view (the largest one) gets the standard scroll bars on the
    border where the view reaches it; the view's own bars go away there."""

    DEFAULT_CSS = "_TVWindow { layers: frame content bars; }"

    def __init__(self, title: str = "", *, number: int = 0, **kwargs) -> None:
        super().__init__(title=title, **kwargs)
        self.number = number
        self.tv_options |= OptionFlag.TILEABLE  # Window > Tile only arranges tileable windows
        self.v_bar = FrameScrollBar()
        self.h_bar = FrameScrollBar(horizontal=True)
        self._scrolled: Widget | None = None  # the view the bars are bound to

    def compose_content(self) -> ComposeResult:
        yield from ()

    # The frame and the content as textual_vision gives them, or None while the window opens or
    # closes: a window being closed loses its children before it goes, and work still under way
    # (a worker, a timer, a repaint) may ask for them then.
    @property
    def frame(self) -> Frame | None:
        found = list(self.query(Frame)) if self.is_mounted else []
        return found[0] if found else None

    @property
    def content(self) -> Container | None:
        found = list(self.query(".tv-window-content")) if self.is_mounted else []
        return found[0] if found else None  # type: ignore[return-value]

    @property
    def closing(self) -> bool:
        """Being taken off (Textual marks it and all it holds before its children go) or gone:
        work that ends then (a check with Div, a theme change) has nothing left to paint."""
        return self._pruning or (self.is_mounted and not self.is_attached)

    def compose(self) -> ComposeResult:
        yield IndicatorFrame(title=self._title, flags=self._window_flags, active=True, number=self.number)
        with Container(classes="tv-window-content"):
            yield from self.compose_content()
        yield self.v_bar
        yield self.h_bar

    # ------------------------------------------------------------ scroll bars
    def scroll_view(self) -> Widget | None:
        """The view the border's bars scroll: the largest scrolling one."""
        content = self.content
        if content is None:
            return None
        views = [
            w for w in content.query("*")
            if w.display and w.region.area and (isinstance(w, ListViewer) or w.styles.overflow_y in ("auto", "scroll") or w.styles.overflow_x in ("auto", "scroll"))
        ]
        return max(views, key=lambda w: w.region.area, default=None)

    def on_mount(self) -> None:
        self.call_after_refresh(self.update_scroll_bars)

    def on_resize(self) -> None:
        self.call_after_refresh(self.update_scroll_bars)

    def on_scroll_bar_changed(self, message: TVScrollBar.Changed) -> None:
        message.stop()  # the bar has already scrolled its view

    def _bind(self, view: Widget | None) -> None:
        old = self._scrolled
        if view is old:
            return
        if old is not None and isinstance(old, ListViewer) and old.v_scroll_bar is self.v_bar:
            old.v_scroll_bar = None
        self._scrolled = view
        self.v_bar.view = self.h_bar.view = view
        if view is None:
            return
        if isinstance(view, ListViewer):
            view.v_scroll_bar = self.v_bar  # the list sets its bar's range and value itself
            self.v_bar.scroll_target = view
        else:
            self.v_bar.scroll_target = self.v_bar  # its scroll_to_value scrolls the view
            self.h_bar.scroll_target = self.h_bar
            for name in ("scroll_x", "scroll_y", "virtual_size"):
                self.watch(view, name, lambda *_: self.sync_scroll_bars(), init=False)

    def update_scroll_bars(self) -> None:
        """Bind, place and show the bars (after a layout change, or the window's activation)."""
        if not self.is_mounted:
            return
        frames = self.query(Frame)
        if not frames:  # the window is being taken off the desktop (File > Open folder closes them all)
            return
        frame = frames.first()
        view = self.scroll_view()
        self._bind(view)
        active = bool(frame is not None and frame.active)
        right = bottom = False
        if view is not None and view.region.area:
            wr, vr = self.region, view.region
            right = vr.right == wr.right - 1 and wr.width > 4
            bottom = vr.bottom == wr.bottom - 1 and wr.height > 3
            if right:
                self.v_bar.styles.offset = (wr.width - 1, vr.y - wr.y)
                self.v_bar.styles.height = vr.height
            if bottom:
                start = vr.x - wr.x
                if isinstance(frame, IndicatorFrame) and frame.indicator:
                    start = max(start, HBAR_AFTER_INDICATOR, 2 + len(frame.indicator) + 3)
                end = min(vr.right - wr.x, wr.width - 2)  # the ─┘ of the resize corner stays
                bottom = end - start >= 4
                if bottom:
                    self.h_bar.styles.offset = (start, wr.height - 1)
                    self.h_bar.styles.width = end - start
            if not isinstance(view, ListViewer):
                view.styles.scrollbar_size_vertical = 0 if right else 1
                view.styles.scrollbar_size_horizontal = 0 if bottom else 1
        self.v_bar.shown = active and right
        self.h_bar.shown = active and bottom and not isinstance(view, ListViewer)
        self.sync_scroll_bars()

    def sync_scroll_bars(self) -> None:
        view = self._scrolled
        if view is None:
            self.v_bar.update_display()
            self.h_bar.update_display()
            return
        if isinstance(view, ListViewer):
            self.v_bar.update_display()
            self.h_bar.update_display()
            return
        region = view.scrollable_content_region
        self.v_bar.sync(view.max_scroll_y, region.height, round(view.scroll_y))
        self.h_bar.sync(view.max_scroll_x, region.width, round(view.scroll_x))


class EditorView(DivEditor, TVViewMixin):
    """The Div editor as a selectable Turbo Vision view."""

    DEFAULT_CSS = """
    EditorView, EditorView:focus {
        border: none; padding: 0; width: 1fr; height: 1fr;
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

    BINDINGS = [
        Binding("ctrl+space,ctrl+@", "complete", "Complete", show=False),
        Binding("ctrl+a", "select_all", "Select all", show=False),  # TextArea's ctrl+a is Home
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.tv_options = OptionFlag.SELECTABLE
        self._popup: CompletionPopup | None = None
        self._signature: InfoPopup | None = None  # the call's signature, over the line
        self._doc: InfoPopup | None = None  # the documentation of the selected completion
        self._typed = False  # the last change came from a key typed here
        self._completion_pending = False
        self.breakpoint_rows: set[int] = set()  # debugger marks, 0-based rows
        self.execution_row: int | None = None
        self.change_rows: dict[int, str] = {}  # git: the rows changed since the last commit (add, mod, del)

    # ------------------------------------------------------------ debugger
    # Turbo Pascal's bars: breakpoints in red, the line about to run in cyan.

    def set_debug_marks(self, breakpoints: set[int], execution: int | None) -> None:
        if breakpoints != self.breakpoint_rows or execution != self.execution_row:
            self.breakpoint_rows = set(breakpoints)
            self.execution_row = execution
            self.refresh()

    def set_change_marks(self, rows: dict[int, str]) -> None:
        """git's marks in the gutter: the line number on green (added), brown (changed) or
        red (lines removed just above)."""
        if rows != self.change_rows:
            self.change_rows = rows
            self.refresh()

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        if not self.breakpoint_rows and self.execution_row is None and not self.change_rows:
            return strip
        try:
            row, section = self.wrapped_document._offset_to_line_info[y + self.scroll_offset.y]
        except (IndexError, TypeError, ValueError):
            return strip
        change = self.change_rows.get(row) if section == 0 and self.show_line_numbers else None
        if change is not None and self.gutter_width:
            gutter = self.gutter_width
            mark = themes.current().style(f"diff-{change}", f"diff-{change}-bg")
            number = strip.crop(0, gutter - 1)
            number = Strip(list(Segment.apply_style(list(number), post_style=mark)), number.cell_length)
            strip = Strip.join([number, strip.crop(gutter - 1, strip.cell_length)])
        if row == self.execution_row:
            style = themes.current().style("execution", "execution-bg")
        elif row in self.breakpoint_rows:
            style = themes.current().style("breakpoint", "breakpoint-bg")
        else:
            return strip
        gutter = self.gutter_width
        code = strip.crop(gutter, strip.cell_length)
        code = Strip(list(Segment.apply_style(list(code), post_style=style)), code.cell_length)
        return Strip.join([strip.crop(0, gutter), code])

    # ------------------------------------------------------------ completion
    @property
    def completing(self) -> bool:
        return self._popup is not None and self._popup.display and self._popup.result is not None

    def action_complete(self) -> None:
        self.update_completion(explicit=True)

    def _caret_index(self) -> int | None:
        sel = self.selection
        if sel.start != sel.end:
            return None
        return self.document.get_index_from_location(sel.end)

    def _complete_at_cursor(self, explicit: bool) -> CompletionResult | None:
        if not self.div_enabled or self.read_only:
            return None
        offset = self._caret_index()
        if offset is None:
            return None
        provider = getattr(self.app, "completion_data_for", None)
        data = provider(self) if provider is not None else None
        setup = getattr(self.app, "div_setup", None)
        return complete(
            self.text, offset, self.tokens, self.dialect,
            data=data, template=self.path, roots=self.roots, explicit=explicit,
            template_ext=setup().template_ext if setup is not None else ".tpl",
        )

    def update_completion(self, explicit: bool = False) -> None:
        if self.lang == "php":
            # asked to the language server; the answer comes back in show_completion
            provider = getattr(self.app, "lsp_complete", None)
            if provider is None or self.read_only or self._caret_index() is None:
                self.hide_completion()
            else:
                provider(self, explicit)
            return
        self.show_completion(self._complete_at_cursor(explicit), explicit)

    def show_completion(self, result: CompletionResult | None, explicit: bool) -> None:
        if result is None or not result.items:
            self.hide_completion()
            return
        if self._popup is None or not self._popup.is_attached:
            self._popup = CompletionPopup(self)
            self.screen.mount(self._popup)
        x, y = self.cursor_screen_offset
        self._popup.show(result, explicit=explicit, at=(x - len(result.prefix), y), screen_size=tuple(self.screen.size))
        self._ask_doc()

    def hide_completion(self) -> None:
        if self._popup is not None:
            self._popup.result = None
            self._popup.display = False
        self.hide_doc()

    # ------------------------------------------------------------ signature and documentation
    def _info(self, which: str) -> InfoPopup:
        popup = getattr(self, "_" + which)
        if popup is None or not popup.is_attached:
            popup = InfoPopup(which)
            setattr(self, "_" + which, popup)
            self.screen.mount(popup)
        return popup

    @property
    def signature_shown(self) -> bool:
        return self._signature is not None and self._signature.display and bool(self._signature.lines)

    def show_signature(self, lines: list[str], mark: tuple[int, int, int] | None) -> None:
        """Over the cursor's line (under it when there is no room above)."""
        popup = self._info("signature")
        x, y = self.cursor_screen_offset
        width, height = len(max(lines, key=len)) + 4, len(lines) + 2
        sw, sh = self.screen.size
        top = y - height if y - height >= 1 else y + 1
        popup.show(lines, x=min(max(0, x - 2), max(0, sw - width - 2)), y=min(top, max(0, sh - height - 1)), mark=mark)

    def hide_signature(self) -> None:
        if self._signature is not None:
            self._signature.hide()

    def show_doc(self, lines: list[str]) -> None:
        """Beside the completion list (on its left when there is no room on its right)."""
        if not self.completing or not lines:
            self.hide_doc()
            return
        popup = self._info("doc")
        assert self._popup is not None
        px, py = int(self._popup.styles.offset.x.value), int(self._popup.styles.offset.y.value)
        pw = int(self._popup.styles.width.value)
        width = len(max(lines, key=len)) + 4
        sw, sh = self.screen.size
        x = px + pw + 2
        if x + width > sw:
            x = px - width - 1
        if x < 0:
            x = max(0, sw - width - 2)
        popup.show(lines, x=x, y=min(py, max(0, sh - len(lines) - 3)))

    def hide_doc(self) -> None:
        if self._doc is not None:
            self._doc.hide()

    def _ask_doc(self) -> None:
        """The selected completion changed: its documentation, when someone knows it."""
        item = self._popup.selected if self._popup is not None and self.completing else None
        provider = getattr(self.app, "lsp_document", None)
        if item is None or item.data is None or provider is None:
            self.hide_doc()
            return
        provider(self, item)

    def accept_completion(self) -> None:
        popup = self._popup
        item = popup.selected if popup is not None else None
        result = popup.result if popup is not None else None
        self.hide_completion()
        offset = self._caret_index()
        if item is None or result is None or offset is None or result.start > offset:
            return
        insert = item.insert
        caret = insert.find(CARET)
        insert = insert.replace(CARET, "")
        after = item.after if item.after and not self.text.startswith(item.after, offset) else ""
        doc = self.document
        self.replace(insert + after, doc.get_location_from_index(result.start), doc.get_location_from_index(offset))
        cursor = result.start + (caret if caret >= 0 else len(insert))
        # other edits that come with the item (a language server's `use` line): before the
        # word only, from the last to the first, inserts at one place in the server's order
        extra = [(i, e) for i, e in enumerate(item.extra) if e[1] <= result.start]
        for _, (start, end, text) in sorted(extra, key=lambda pair: (-pair[1][0], -pair[0])):
            self.replace(text, doc.get_location_from_index(start), doc.get_location_from_index(end))
            cursor += len(text) - (end - start)
        self.move_cursor(doc.get_location_from_index(cursor))
        self._typed = False
        if item.retrigger:
            self.call_after_refresh(self.update_completion, True)

    def _refresh_completion(self) -> None:
        self._completion_pending = False
        typed, self._typed = self._typed, False
        if self.lang == "php":
            if self.completing:
                self.update_completion(self._popup.explicit)  # type: ignore[union-attr]
            elif typed:
                self.update_completion(explicit=False)
            return
        if self.completing:
            assert self._popup is not None and self._popup.result is not None
            start = self._popup.result.start
            result = self._complete_at_cursor(self._popup.explicit)
            if result is None or not result.items or (result.start != start and not typed):
                self.hide_completion()
            else:
                self.update_completion(self._popup.explicit)
        elif typed:
            self.update_completion(explicit=False)

    def _schedule_completion(self) -> None:
        if not self._completion_pending and (self._typed or self.completing):
            self._completion_pending = True
            self.call_after_refresh(self._refresh_completion)

    async def _on_key(self, event: events.Key) -> None:
        if self.completing:
            assert self._popup is not None
            key = event.key
            handled = True
            if key == "up":
                self._popup.move(-1)
                self._ask_doc()
            elif key == "down":
                self._popup.move(1)
                self._ask_doc()
            elif key == "pageup":
                self._popup.page(-1)
                self._ask_doc()
            elif key == "pagedown":
                self._popup.page(1)
                self._ask_doc()
            elif key in ("enter", "tab"):
                self.accept_completion()
            elif key == "escape":
                self.hide_completion()
            else:
                handled = False
            if handled:
                event.stop()
                event.prevent_default()
                return
        if event.key == "escape" and self.signature_shown:
            self.hide_signature()
            event.stop()
            event.prevent_default()
            return
        if event.is_printable or event.key == "backspace":
            self._typed = True

    def on_text_area_changed(self) -> None:
        self._schedule_completion()
        self._signature_follow()

    def on_text_area_selection_changed(self) -> None:
        self._schedule_completion()
        if self.signature_shown:
            self._signature_follow()

    def _signature_follow(self) -> None:
        hook = getattr(self.app, "lsp_signature_changed", None)
        if hook is not None and self.lang == "php":
            hook(self)

    def on_blur(self) -> None:
        self.hide_completion()
        self.hide_signature()

    def on_click(self, event: events.Click) -> None:
        # Ctrl+click on an include opens it (after the click has placed the cursor).
        if event.ctrl and (self.div_enabled or self.lang == "php") and hasattr(self.app, "action_command"):
            self.call_after_refresh(self.app.action_command, "GOTO_INCLUDE")


class EditorWindow(_TVWindow):

    def __init__(self, path: Path | None, text: str, *, roots: list[Path], untitled: int = 0, number: int = 0) -> None:
        self.path = path
        self.untitled = untitled
        self.editor = EditorView(text, path=path, roots=roots)
        self.saved_text = text
        super().__init__(self.display_name, number=number)

    @property
    def display_name(self) -> str:
        return self.path.name if self.path else UNTITLED.format(self.untitled)

    @property
    def dirty(self) -> bool:
        return self.editor.text != self.saved_text

    def compose_content(self) -> ComposeResult:
        yield self.editor

    def on_mount(self) -> None:
        self.call_after_refresh(self.refresh_indicator)

    def refresh_indicator(self) -> None:
        frame = self.frame  # (not there while the window opens or closes)
        if not isinstance(frame, IndicatorFrame):
            return
        row, col = self.editor.cursor_location
        frame.set_indicator(f"{'*' if self.dirty else ' '} {row + 1}:{col + 1}")

    def on_command_message(self, message: CommandMessage) -> None:
        # The close icon must go through the app, which asks about unsaved changes.
        if message.command == Command.CLOSE:
            message.stop()
            message.prevent_default()  # Window.close() would skip the unsaved-changes check
            self.app.close_window(self)  # type: ignore[attr-defined]


@dataclass
class FileEntry(DirEntry):
    """A file the project window can unfold into its members (its outline)."""


@dataclass
class MemberEntry(DirEntry):
    """A part of a file (a class, a method, a heading...): ``path`` is the file."""

    member: outline_mod.Node | None = None


MEMBERS_MAX_BYTES = 2_000_000  # a bigger file unfolds into nothing (open it: Search > Outline)


# Folders that are never worth browsing in the project window.
def shown_entries(node) -> frozenset[tuple[str, bool]]:
    """What a folder's node shows, as (name, is a folder) pairs: read on the UI thread, a snapshot."""
    return frozenset((c.data.path.name, bool(c.allow_expand) and type(c.data) is DirEntry)
                     for c in list(node.children) if c.data is not None)


def disk_entries(folder: Path) -> frozenset[tuple[str, bool]] | None:
    """What ``folder`` holds as the project window would show it (None: gone or unreadable). Disk only,
    nothing of the UI: it runs in a worker thread."""
    try:
        entries = list(folder.iterdir())
    except OSError:
        return None
    out = set()
    for path in entries:
        if not shown_in_project(path):
            continue
        try:
            folder_ = path.is_dir()
        except OSError:
            folder_ = False
        out.add((path.name, folder_))
    return frozenset(out)


HIDDEN_NAMES = {".git", ".hg", ".svn", "__pycache__", ".venv", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".idea"}


class ProjectTree(FilteredTree, DirectoryTree, TVViewMixin):
    """Project explorer: Ins new file, F7 new folder, F2 rename, Del delete,
    Ctrl+R refresh, Alt+F10 (or a right click) the local menu.

    Moving: Ctrl+X cuts, Ctrl+C copies, Ctrl+V pastes in the folder under the bar;
    Esc forgets what was cut. With the mouse, drag a file or a folder onto a folder
    (the app asks before moving it)."""

    # Single-width glyphs: the default emoji icons are double width and not in the TV style.
    ICON_NODE = "► "  # Turbo Vision's own (CP437), like every glyph divide draws
    ICON_NODE_EXPANDED = "▼ "
    ICON_FILE = "  "
    BINDINGS = [
        Binding("insert", "request('new_file')", "New file", show=False),
        Binding("f7", "request('new_folder')", "New folder", show=False),
        Binding("f2", "request('rename')", "Rename", show=False),
        Binding("delete", "request('delete')", "Delete", show=False),
        Binding("ctrl+r", "request('refresh')", "Refresh", show=False),
        Binding("ctrl+x", "request('cut')", "Cut", show=False),
        Binding("ctrl+c", "request('copy')", "Copy", show=False),
        Binding("ctrl+v", "request('paste')", "Paste", show=False),
        Binding("alt+f10,shift+f10", "request('menu')", "Local menu", show=False),
        Binding("right", "unfold", "Unfold", show=False),
        Binding("left", "fold", "Fold", show=False),
    ]
    DEFAULT_CSS = """
    ProjectTree {
        background: $window-content-background;
        color: $foreground;
        scrollbar-size: 1 1;
        scrollbar-background: $secondary;
        scrollbar-color: $background;
        scrollbar-corner-color: $secondary;
        padding: 0;
    }
    ProjectTree > .directory-tree--folder { color: $warning; text-style: none; }
    ProjectTree > .directory-tree--extension { text-style: none; }
    ProjectTree > .directory-tree--hidden { color: $secondary; }
    ProjectTree > .tree--guides, ProjectTree > .tree--guides-hover, ProjectTree > .tree--guides-selected {
        color: $secondary;
    }
    ProjectTree > .tree--cursor, ProjectTree:focus > .tree--cursor {
        color: $text; background: $secondary; text-style: none;
    }
    ProjectTree > .tree--highlight, ProjectTree > .tree--highlight-line { background: $window-content-background; }
    """

    class Request(Message):
        """The user asked for a file operation (handled by the app)."""

        def __init__(self, tree: "ProjectTree", action: str, screen_at: tuple[int, int] | None = None) -> None:
            super().__init__()
            self.tree = tree
            self.action = action
            self.screen_at = screen_at

    class Drop(Message):
        """A file or a folder dragged onto a folder (the app asks, then moves it)."""

        def __init__(self, tree: "ProjectTree", source: Path, folder: Path) -> None:
            super().__init__()
            self.tree, self.source, self.folder = tree, source, folder

    def __init__(self, *args, icons: str = icons_mod.PLAIN, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.tv_options = OptionFlag.SELECTABLE
        self.icons = icons
        self.auto_expand = False  # folders toggle on Enter themselves; a file that unfolds opens
        self.clipboard: tuple[Path, bool] | None = None  # (path, cut): what Ctrl+V pastes
        self._press = None  # (node, y) of a button-1 press: a drag once the mouse moves a row
        self._drag = None  # the node dragged
        self._drop = None  # the folder node it would go into
        self._swallow_click = False  # the click that ends a drag opens nothing
        self._renewed: dict[int, tuple] = {}  # id(old node) -> (old, new): the last folder filled again
        # git (divide.ui.git): a changed file's letter, the folders holding changes, what git ignores
        self.git_files: dict[Path, str] = {}
        self.git_folders: set[Path] = set()
        self.git_ignored: set[Path] = set()
        # changes made outside divide (divide.run.fswatch): the open folders are watched
        self.watcher = None
        self.watch_problem: str | None = None  # why a folder is not watched (said once)
        self._watch_update_due = False

    # ---------------------------------------------------------- outside changes
    def on_mount(self) -> None:
        from divide.run.fswatch import FolderWatcher

        if os.environ.get("DIVIDE_NO_WATCH"):
            return
        self.watcher = FolderWatcher(self._changed_elsewhere, self._watch_refused)
        self.watch_update()

    def on_unmount(self) -> None:
        self.stop_watching()

    def stop_watching(self) -> None:
        watcher, self.watcher = self.watcher, None
        if watcher is not None:
            watcher.stop()

    def watched_folders(self) -> list[Path]:
        """The project's folder and each folder shown open, shallow ones first (they come first under
        the limit): what is watched, each alone. Closed folders are read when they open."""
        out = [Path(self.path)]
        queue = list(self.root.children)
        while queue:
            node = queue.pop(0)
            if type(node.data) is DirEntry and node.allow_expand and node.is_expanded and node.data.loaded:
                out.append(node.data.path)
                queue.extend(node.children)
        return out

    def watch_update(self) -> None:
        """The watched folders follow the open ones (after the tree changed: once per refresh)."""
        if self.watcher is None or self._watch_update_due:
            return
        self._watch_update_due = True

        def update() -> None:
            self._watch_update_due = False
            if self.watcher is not None and self.is_attached:
                self.watcher.set_folders(self.watched_folders())

        self.call_after_refresh(update)

    def _changed_elsewhere(self, batch) -> None:  # watchdog's or the timer's thread: nothing of the UI here
        try:
            self.app.call_from_thread(self._apply_changes, batch)
        except RuntimeError:  # the app has stopped
            pass

    def _watch_refused(self, folder: Path, why: str) -> None:  # watchdog's or the caller's thread
        def say() -> None:
            self.watch_problem = f"{folder}: {why}"
            if self.is_attached:
                self.app.notify(_("Not watched for outside changes: {name} ({why}). Ctrl+R refreshes.").format(
                    name=folder.name or str(folder), why=why), severity="warning", timeout=6)
        try:
            if threading.current_thread() is threading.main_thread():
                say()
            else:
                self.app.call_from_thread(say)
        except RuntimeError:
            pass

    def _apply_changes(self, batch) -> None:
        """The UI thread: the folders that changed outside divide, read again (only those, and only
        when what they hold is not what is shown)."""
        watcher = self.watcher
        if watcher is None or not watcher.is_current(batch) or not self.is_attached:
            return  # a stale batch: another project, folders changed since, the window closed
        self.run_worker(self._refresh_folders(batch.folders), group="project-watch")

    async def _refresh_folders(self, folders) -> None:
        root = Path(self.path)
        kept: list[Path] = []
        for folder in sorted(folders, key=lambda p: len(p.parts)):
            if not any(k == folder or k in folder.parents for k in kept):
                kept.append(folder)  # an ancestor read again reads its open folders too
        for folder in kept:
            if not self.is_attached or self.watcher is None:
                return
            node = self._open_node(folder, root)
            if node is None:
                continue
            on_disk = await asyncio.to_thread(disk_entries, folder)  # the disk, read off the UI thread
            node = self._open_node(folder, root)  # the tree as it is now: it may have changed meanwhile
            if node is None or (on_disk is not None and on_disk == shown_entries(node)):
                continue  # gone or closed since, or already showing what the folder holds
            y = self.scroll_offset.y
            await self.reload_node(node)
            if self.is_attached:
                self._keep_scroll(y)
        self.watch_update()

    def _open_node(self, folder: Path, root: Path):
        """The node of ``folder`` if it is in the tree and open (the UI thread), else None."""
        if not self.is_attached:
            return None
        node = self.root if folder == root else self._node_for(folder)
        if node is None or (node is not self.root and not (node.is_expanded and type(node.data) is DirEntry)):
            return None
        return node

    def _keep_scroll(self, y: float) -> None:
        """No jump: the rows stay where they were (once the tree has its new size), unless the bar
        would leave the view."""
        def back() -> None:
            if not self.is_attached:
                return
            cursor = self.cursor_line
            height = self.scrollable_content_region.height or self.size.height
            if cursor < 0 or y <= cursor < y + height:
                self.scroll_to(y=y, animate=False, immediate=True)

        back()
        self.call_after_refresh(back)

    def set_clipboard(self, path: Path | None, cut: bool = False) -> None:
        """What Ctrl+V pastes (None: nothing); a cut one is drawn dim."""
        self.clipboard = (path, cut) if path is not None else None
        self._invalidate()
        self.refresh()

    def set_icons(self, mode: str) -> None:
        if mode != self.icons:
            self.icons = mode
            self._invalidate()
            self.refresh()

    def set_git(self, files: dict[Path, str], folders: set[Path], ignored: set[Path]) -> None:
        """What git says of the files (``divide.run.git.marks``): drawn beside their names."""
        if (files, folders, ignored) != (self.git_files, self.git_folders, self.git_ignored):
            self.git_files, self.git_folders, self.git_ignored = files, folders, ignored
            self._invalidate()
            self.refresh()

    def render_label(self, node, base_style, style):
        text = self._label(node, base_style, style)
        data = node.data
        if data is not None and not isinstance(data, MemberEntry):
            if self.clipboard is not None and self.clipboard[1] and data.path == self.clipboard[0]:
                text.stylize(Style(dim=True))  # cut: it goes where Ctrl+V says
            if node is self._drop:
                text.stylize(Style(reverse=True))  # where a drag would drop it
            if self.git_files or self.git_folders or self.git_ignored:
                self._git_mark(text, node, data.path, style)
        return text

    def _git_mark(self, text: Text, node, path: Path, style: Style) -> None:
        """M, A, ?... after a changed file's name, • after a folder that holds changes;
        what git ignores, dimmed."""
        from divide.ui.git import CODES

        bar = style if self.cursor_node is node else Style()
        palette = themes.current()
        code = self.git_files.get(path)
        if code is not None:
            text.append(f" {code}", Style(color=palette.hex(CODES.get(code, "white")), bold=True) + bar)
        elif path in self.git_folders:
            text.append(" •", Style(color=palette.hex(CODES["M"]), bold=True) + bar)
        elif path in self.git_ignored or any(p in self.git_ignored for p in path.parents):
            text.stylize(Style(dim=True))

    def _label(self, node, base_style, style):
        data = node.data
        if isinstance(data, MemberEntry) and data.member is not None:
            label = outline_mod.rich_label(data.member, themes.current())
            if self.cursor_node is node:
                label.stylize(style)  # the bar: one colour from end to end
            prefix = (self.ICON_NODE_EXPANDED if node.is_expanded else self.ICON_NODE) if node._allow_expand else "  "
            return Text.assemble((prefix, base_style), label)
        if isinstance(data, FileEntry):
            # a file that unfolds: drawn as a file, its ► / ▼ where files have their mark
            node._allow_expand = False
            try:
                text = super().render_label(node, base_style, style)
            finally:
                node._allow_expand = True
            if not self.is_mounted:
                return text
            arrow = (self.ICON_NODE_EXPANDED if node.is_expanded else self.ICON_NODE)[0]
            colour = None
            if self.icons == icons_mod.MARKS:  # folded, its mark (a click on it unfolds); unfolded, ▼ in its colour
                mark, colour = icons_mod.mark_for(data.path)
                arrow = arrow if node.is_expanded else mark
            return Text.assemble((arrow, base_style + TOGGLE_STYLE + Style(color=colour) + style), text[1:])
        text = super().render_label(node, base_style, style)
        if self.icons != icons_mod.MARKS or data is None or node._allow_expand or not self.is_mounted:
            return text
        # the file's mark in the blank cell where a folder has its ►: the same width
        mark, colour = icons_mod.mark_for(data.path)
        return Text.assemble((mark, base_style + Style(color=colour) + style), text[1:])

    # ---------------------------------------------------------- members
    def _populate_node(self, node, content) -> None:
        if isinstance(node.data, FileEntry):  # reloaded while unfolded: its members again
            self.fill_members(node)
            return
        if isinstance(node.data, MemberEntry):  # a reload reopens it as if it were a folder: it keeps its own
            node.expand()
            return
        # the bar on one of its entries stays on it: the loader may fill a folder again
        # after the bar was put there (a reveal, a move), and its nodes are new ones
        selected = self.selected_path
        here = node.data.path if node.data is not None else Path(self.path)
        keep = selected is not None and selected.parent == here
        old = {c.data.path: c for c in node.children if c.data is not None}
        node.remove_children()
        again = None
        renewed: dict[int, tuple] = {}
        for path in content:
            folder = self._safe_is_dir(path)
            unfolds = not folder and outline_mod.has_outline(language_of(path))
            child = node.add(path.name, data=FileEntry(path) if unfolds else DirEntry(path), allow_expand=folder or unfolds)
            if path in old:  # the bar was elsewhere: the loader's late move back is not followed
                renewed[id(old[path])] = (old[path], child if keep else None)
            if keep and path == selected:
                again = child
        self._renewed = renewed
        node.expand()
        self.watch_update()
        if again is not None:
            self._clear_line_cache()
            _ = self._tree_lines
            if again._line >= 0:
                self.move_cursor(again, animate=False)

    def move_cursor(self, node, animate: bool = False) -> None:
        # Textual's loader puts the bar back on the node it was on before it filled the
        # folder again; that node is gone then: its new one takes the bar instead
        if node is not None and self._tree_nodes.get(node.id) is not node:  # a node no longer in the tree
            pair = getattr(self, "_renewed", {}).get(id(node))
            if pair is None or pair[0] is not node or pair[1] is None:
                return  # gone, or the bar has gone to another folder since: it stays where it is
            node = pair[1]
            self._clear_line_cache()
            _ = self._tree_lines
        super().move_cursor(node, animate=animate)

    def fill_members(self, node) -> None:
        """The members of the file of ``node``, from its open editor if it has one
        (unsaved changes too), else from the disk."""
        path = node.data.path
        opened: set[tuple[str, ...]] = set()  # the members unfolded now stay so
        stack = [(child, ()) for child in node.children]
        while stack:
            child, above = stack.pop()
            if isinstance(child.data, MemberEntry) and child.data.member is not None:
                here = above + (child.data.member.key,)
                if child.is_expanded:
                    opened.add(here)
                    stack.extend((c, here) for c in child.children)
        node.remove_children()
        text, context = None, {"path": path}
        window = self.app.window_for(path) if hasattr(self.app, "window_for") else None  # type: ignore[attr-defined]
        if window is not None:
            text = window.editor.text
            if window.editor.lang == "div":
                context.update(tokens=window.editor.tokens, blocks=window.editor.div_blocks())
        else:
            try:
                if path.stat().st_size <= MEMBERS_MAX_BYTES:
                    text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = None
        members = outline_mod.outline(language_of(path), text, **context) if text is not None else None
        node.data.loaded = True
        self._add_members(node, members or [], path, opened, ())

    def _add_members(self, parent, members, path, opened, above) -> None:
        for member in members:
            here = above + (member.key,)
            child = parent.add(member.text, data=MemberEntry(path, member=member), allow_expand=bool(member.children),
                               expand=here in opened or len(members) == 1)  # a lone namespace or class opens at once
            self._add_members(child, member.children, path, opened, here)

    def refresh_members(self, path: Path) -> None:
        """``path`` changed (saved): the unfolded file shows its members as they are now."""
        node = self._node_for(path)
        if node is not None and isinstance(node.data, FileEntry) and node.is_expanded:
            self.fill_members(node)

    def on_tree_node_collapsed(self, event) -> None:
        self.watch_update()

    async def _on_tree_node_expanded(self, event) -> None:
        data = event.node.data
        if (type(data) is DirEntry and data.loaded and self.watcher is not None
                and data.path not in self.watcher.folders):  # closed while things changed in it: read again if so
            self.run_worker(self._refresh_folders([data.path]), group="project-watch")
        self.watch_update()
        if isinstance(data, (FileEntry, MemberEntry)):
            event.stop()
            event.prevent_default()  # not DirectoryTree's: it would open the file
            if isinstance(data, FileEntry):
                self.fill_members(event.node)

    async def _on_tree_node_selected(self, event) -> None:
        data = event.node.data
        if isinstance(data, MemberEntry) and data.member is not None:
            event.stop()
            event.prevent_default()
            self.post_message(self.MemberSelected(self, data.path, data.member.start, data.member.end))
        elif data is not None and not isinstance(data, FileEntry) and event.node.allow_expand:
            event.node.toggle()  # a folder opens and closes (Enter on a file opens the file only)

    def action_unfold(self) -> None:
        """→: a folder or a file opens (its files, its members); on an open one, to its first."""
        node = self.cursor_node
        if node is not None and node.allow_expand:
            if node.is_expanded and node.children:
                self.move_cursor(node.children[0])
            else:
                node.expand()

    def action_fold(self) -> None:
        """←: an open folder or file closes; on anything else, to what holds it."""
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand and node.is_expanded:
            node.collapse()
        elif node.parent is not None and node.parent is not self.root:
            self.move_cursor(node.parent)

    class MemberSelected(Message):
        """Enter on a member: open its file there."""

        def __init__(self, tree: "ProjectTree", path: Path, start: int, end: int) -> None:
            super().__init__()
            self.tree, self.path, self.start, self.end = tree, path, start, end

    @property
    def member(self):
        """The member under the bar, if the bar is on one."""
        node = self.cursor_node
        return node.data.member if node is not None and isinstance(node.data, MemberEntry) else None

    def filter_paths(self, paths):
        return [p for p in paths if shown_in_project(p)]

    def apply_filter(self) -> None:
        super().apply_filter()
        if self.filter_text:
            self._load_matches(self.filter_text)

    @work(exclusive=True, group="project-filter")
    async def _load_matches(self, query: str) -> None:
        """The folders that hold a match, loaded (a folder loads when it opens: the
        filter looks in the whole project, not only in what was opened)."""
        await asyncio.sleep(0.2)  # the next key is likely on its way
        root = Path(self.path)
        found = await asyncio.to_thread(find_in_project, root, query)
        if query != self.filter_text:
            return
        for path in found:
            node = self.root
            for part in path.relative_to(root).parts[:-1]:
                if node.data is not None and not node.data.loaded:
                    await self._add_to_load_queue(node)
                node = next((c for c in node.children if c.data is not None and c.data.path.name == part), None)
                if node is None:
                    break
            else:
                if node.data is not None and not node.data.loaded:
                    await self._add_to_load_queue(node)
        if query == self.filter_text:
            super().apply_filter()
            if self.filter_line is not None:
                self.filter_line.show()

    def action_request(self, action: str) -> None:
        self.post_message(self.Request(self, action, self.cursor_screen_at() if action == "menu" else None))

    def on_key(self, event: events.Key) -> None:
        # before the filter's own (FilteredTree.on_key): Esc there empties the filter first
        if event.key != "escape" or self.filter_text:
            return
        if self._drag is not None:
            self._end_drag()
        elif self.clipboard is not None and self.clipboard[1]:
            self.set_clipboard(None)
        else:
            return
        event.stop()
        event.prevent_default()

    def on_paste(self, event: events.Paste) -> None:
        # Ctrl+V is taken by some terminals themselves, which send what their clipboard
        # holds as a paste instead of the key: that is Ctrl+V too
        if self.clipboard is not None:
            event.stop()
            event.prevent_default()
            self.action_request("paste")

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._swallow_click = False
        self._press = None
        if event.button == 3:
            event.stop()
            line = event.y + self.scroll_offset.y
            if 0 <= line < self.last_line + 1:
                self.cursor_line = line
            self.post_message(self.Request(self, "menu", (event.screen_x, event.screen_y)))
        elif event.button == 1:
            node = self._node_under(event.x, event.y)
            if node is not None and node is not self.root and node.data is not None \
                    and not isinstance(node.data, MemberEntry):
                self._press = (node, event.y)

    # ---------------------------------------------------------- drag and drop
    def _node_under(self, x: float, y: float):
        if not (0 <= x < self.size.width and 0 <= y < self.size.height):
            return None
        line = int(y) + self.scroll_offset.y
        return self.get_node_at_line(line) if 0 <= line <= self.last_line else None

    def _folder_node(self, node):
        """The folder node a drop on ``node`` goes into (a file's: its folder)."""
        while node is not None and not (node is self.root or (
                node.allow_expand and type(node.data) is DirEntry)):
            node = node.parent
        return node

    def drop_target(self, x: float, y: float):
        """The folder node a drag let go at (x, y) would go into, or None (outside,
        where it already is, or inside the folder dragged)."""
        if self._drag is None or not (0 <= x < self.size.width and 0 <= y < self.size.height):
            return None
        node = self._node_under(x, y)
        folder = self._folder_node(node) if node is not None else self.root  # below the last row: the project
        if folder is None or folder.data is None:
            return None
        source, into = self._drag.data.path, folder.data.path
        if into == source.parent or into == source or source in into.parents:
            return None
        return folder

    def _set_drop(self, node) -> None:
        if node is not self._drop:
            self._drop = node
            self._invalidate()
            self.refresh()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._press is None:
            return
        if event.button != 1:  # let go somewhere we did not hear of
            self._end_drag()
            self._press = None
            return
        node, y0 = self._press
        if self._drag is None:
            if int(event.y) == int(y0):
                return
            self._drag = node
            self.capture_mouse()
        if event.y < 1:  # at the edges, the tree scrolls
            self.scroll_relative(y=-1, animate=False, immediate=True)
        elif event.y >= self.size.height - 1:
            self.scroll_relative(y=1, animate=False, immediate=True)
        self._set_drop(self.drop_target(event.x, event.y))

    def on_mouse_up(self, event: events.MouseUp) -> None:
        drag, folder = self._drag, self._drop
        self._press = None
        if drag is None:
            return
        self._end_drag()
        self._swallow_click = True
        event.stop()
        if folder is not None:
            self.post_message(self.Drop(self, drag.data.path, folder.data.path))

    def _end_drag(self) -> None:
        if self._drag is not None:
            self._drag = None
            self.release_mouse()
        self._set_drop(None)

    async def _on_click(self, event: events.Click) -> None:
        if self._swallow_click:  # the end of a drag
            self._swallow_click = False
            event.stop()
            event.prevent_default()
            return
        if event.button == 3:  # the right button opens the local menu (on mouse down), not the file
            event.stop()
            event.prevent_default()
            return
        # a click puts the bar on a file, a double click opens it (a folder opens with one)
        meta = event.style.meta
        if event.button == 1 and event.chain < 2 and "line" in meta and not meta.get("toggle", False):
            node = self.get_node_at_line(meta["line"])
            if node is not None and (not node.allow_expand or isinstance(node.data, (FileEntry, MemberEntry))):
                event.prevent_default()
                self.cursor_line = meta["line"]

    def cursor_screen_at(self) -> tuple[int, int]:
        region = self.content_region
        y = region.y + max(0, self.cursor_line - self.scroll_offset.y)
        return region.x + 2, min(y, region.bottom - 1)

    @property
    def selected_path(self) -> Path | None:
        node = self.cursor_node
        return node.data.path if node is not None and node.data is not None and node is not self.root else None

    @property
    def target_folder(self) -> Path:
        """Where new files go: the folder under the cursor, or the folder of the file under it."""
        path = self.selected_path
        if path is None:
            return Path(self.path)
        return path if path.is_dir() else path.parent

    def _node_for(self, path: Path):
        stack = [self.root]
        while stack:
            node = stack.pop()
            if node.data is not None and node.data.path == path:
                return node
            stack.extend(node.children)
        return None

    def reload_node(self, node) -> AwaitComplete:
        """Textual's, unless the tree has gone (its folder closed, divide quitting) before or while
        it reloads: a move, a paste or a rename still at work then has nothing left to show."""
        return AwaitComplete(self._reload_if_here(node))

    async def _reload_if_here(self, node) -> None:
        if not self.is_attached:
            return
        try:
            await self._reload(node)
        except Exception:
            if self.is_attached:  # not the tree going: a real error
                raise

    async def reveal(self, path: Path) -> None:
        """Reload the folders on the way to ``path`` and put the cursor on it.

        A reload that just ended may still have its folders queued for the tree's
        loader, which fills them again (new nodes): the node found then hangs from
        nothing. It is looked for again once the loader is done; and once it is
        done, the bar must still be there (the loader may fill a folder again after
        the bar was put in it). For a few seconds: a busy machine takes its time."""
        loop = asyncio.get_running_loop()
        give_up = loop.time() + 3.0
        attempt = 0
        target = path.resolve()
        self._reveals = turn = getattr(self, "_reveals", 0) + 1  # a later reveal takes over from this one
        while True:
            if self._reveals != turn or not self.is_attached:  # (the tree may go meanwhile: see reload_node)
                return
            # the first time the folders on the way are reloaded; after that only looked
            # at: reloading them again makes the loader fill them anew, and on a slow
            # machine that never settles
            found = await self._reveal_once(path, reload=attempt == 0)
            while not self._load_queue.empty() and loop.time() < give_up:
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.05)  # (the loader's last folder, after the queue emptied)
            if not self.is_attached:
                return
            if self._reveals != turn:  # another reveal started meanwhile: the bar is its own now
                return
            if found and (self.selected_path == target or not self._can_show(target)):
                return
            if loop.time() >= give_up:
                return
            attempt += 1
            await asyncio.sleep(min(0.05 * attempt, 0.25))

    def _can_show(self, path: Path) -> bool:
        """``path`` is a file or a folder in the project (not the project itself: no bar there)."""
        return path.exists() and Path(self.path).resolve() in path.parents

    async def _reveal_once(self, path: Path, reload: bool = True) -> bool:
        root = Path(self.path).resolve()
        path = path.resolve()
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            return True
        node = self.root
        if reload:
            await self.reload_node(node)
            if not self.is_attached:
                return True
        current = root
        for part in parts:
            current = current / part
            child = next((c for c in node.children if c.data is not None and c.data.path == current), None)
            if child is None:
                if not current.exists():
                    return True  # not there (any more): nothing to show
                if not reload:
                    await self.reload_node(node)  # this folder alone: it does not have it yet
                return False  # else filled again meanwhile
            node = child
            if current != path and node.allow_expand:
                if reload:
                    await self.reload_node(node)
                    if not self.is_attached:
                        return True
                elif not node.is_expanded:
                    node.expand()  # the loader fills it: looked at again next time
                    return False
        self._clear_line_cache()  # lines are rebuilt lazily (on idle): node.line may be stale or -1 until then
        _ = self._tree_lines
        if node._line < 0 and node is not self.root:
            return False
        self.move_cursor(node, animate=False)
        return True

def shown_in_project(path: Path) -> bool:
    return path.name not in HIDDEN_NAMES and not path.name.endswith(".egg-info")


def find_in_project(root: Path, query: str, limit: int = 300, budget: int = 50000) -> list[Path]:
    """The files and folders whose name holds ``query`` (case ignored), as the project
    window shows them: at most ``limit``, after looking at ``budget`` entries at most."""
    query = query.lower()
    found: list[Path] = []
    seen = 0
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if shown_in_project(Path(d)))
        for name in (*dirs, *sorted(files)):
            seen += 1
            if query in name.lower() and shown_in_project(Path(name)):
                found.append(Path(folder) / name)
                if len(found) >= limit:
                    return found
        if seen >= budget:
            break
    return found


class ProjectWindow(_TVWindow):
    WIDTH = 32

    def __init__(self, root: Path, icons: str = icons_mod.PLAIN) -> None:
        self.root = root
        super().__init__(root.name or str(root), flags=WindowFlag.MOVE | WindowFlag.CLOSE | WindowFlag.GROW)
        self.project_tree = ProjectTree(root, icons=icons)

    def compose_content(self) -> ComposeResult:
        yield Filtered(self.project_tree)

    def on_command_message(self, message: CommandMessage) -> None:
        if message.command == Command.CLOSE:
            message.stop()
            message.prevent_default()  # Window.close() would skip the unsaved-changes check
            self.app.close_window(self)  # type: ignore[attr-defined]


# Turbo Pascal's Output window: white on black in the Borland palettes.
OUTPUT_CSS = """
    {name} { background: $divide-output-bg; }
    {name} IndicatorFrame .frame--active { color: $divide-output-frame; }
    {name} IndicatorFrame .frame--passive { color: $divide-output-frame-passive; }
    {name} IndicatorFrame .frame--title { color: $divide-output-frame; }
"""


class OutputWindow(_TVWindow):
    """Rendered output of a template, or what a script printed (read only;
    leftover Div tags stay highlighted). White on black."""

    DEFAULT_CSS = OUTPUT_CSS.replace("{name}", "OutputWindow")

    def __init__(self, number: int = 0) -> None:
        super().__init__("Output", number=number)
        self.view = EditorView("", read_only=True, kind=OUTPUT)
        self.template: Path | None = None
        self.summary = ""

    def compose_content(self) -> ComposeResult:
        yield self.view

    def show(self, template: Path, output: str, summary: str) -> None:
        self.template = template
        self.summary = summary
        self.title = _('Output: {name}').format(name=template.name)
        self.view.load_text(output)



@dataclass(frozen=True)
class MessageItem:
    """One line of the Messages window; with a location it jumps to the editor."""

    text: str
    path: Path | None = None
    start: int | None = None
    end: int | None = None


class MessageList(WheelList, FilteredList, ListBox):
    DEFAULT_CSS = """
    MessageList { background: $panel; }
    MessageList > .list-viewer--normal { color: $text; background: $panel; }
    MessageList > .list-viewer--focused { color: $foreground; background: $background; }
    """
    can_focus = True  # textual-vision's ListViewer does not set it: keys would go to the editor

    def select_item(self, item: int) -> None:
        super().select_item(item)
        window = next((a for a in self.ancestors if isinstance(a, LocationsWindow)), None)
        if window is not None:
            window.activate(self.original(item))

    def on_click(self, event) -> None:
        if event.chain >= 2:
            self.select_item(self.focused)


class LocationsWindow(_TVWindow):
    """A list of lines, each one maybe a place in a file: Enter (or a double click)
    on a located line jumps to it in the editor."""

    EMPTY = "(empty)"

    def __init__(self, title: str, number: int = 0) -> None:
        super().__init__(title, number=number)
        self.list = MessageList([])
        self.items: list[MessageItem] = []

    def compose_content(self) -> ComposeResult:
        yield Filtered(self.list)

    def show(self, items: list[MessageItem]) -> None:
        if items == self.items:
            return
        keep = self.list.current if self.items and len(items) == len(self.items) else 0
        self.items = items or [MessageItem(self.EMPTY)]
        self.list.set_list([item.text for item in self.items])
        if keep > 0:
            self.list.focus_original(min(keep, len(self.items) - 1))

    def activate(self, index: int) -> None:
        if 0 <= index < len(self.items):
            item = self.items[index]
            if item.path is not None and item.start is not None:
                # After the key (Enter) is done, or the editor would receive it.
                self.app.call_later(self.app.goto_location, item.path, item.start, item.end)  # type: ignore[attr-defined]


class MessagesWindow(LocationsWindow):
    """Turbo Pascal style message window: Div checks of the template and render messages."""

    EMPTY = _('(no messages)')

    def __init__(self, number: int = 0) -> None:
        super().__init__("Messages", number=number)
