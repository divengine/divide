"""Turbo Vision windows of the IDE: editor windows and the project tree."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.message import Message
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import DirectoryTree
from textual_vision.constants import Command, OptionFlag, WindowFlag
from textual_vision.events import CommandMessage
from textual_vision.frame import Frame
from textual_vision.group import TVViewMixin
from textual_vision.list_box import ListBox
from textual_vision.window import Window

from divide.editor.div_editor import DivEditor
from divide.lang.div.complete import CARET, CompletionResult, complete
from divide.ui.completion import CompletionPopup, InfoPopup
from divide.ui import icons as icons_mod

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


class IndicatorFrame(RuleFrame):
    """Frame with the window number on the top border and a Borland-style
    ``* 12:5`` indicator (modified flag, line:column) on the bottom border."""

    def __init__(self, *args, number: int = 0, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.number = number
        self.indicator = ""

    def set_indicator(self, text: str) -> None:
        if text != self.indicator:
            self.indicator = text
            self.refresh()

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
        return node.query_one(Frame) if node is not None else None

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


class _TVWindow(Window):
    """Window whose frame is an IndicatorFrame and whose content is composed."""

    def __init__(self, title: str = "", *, number: int = 0, **kwargs) -> None:
        super().__init__(title=title, **kwargs)
        self.number = number
        self.tv_options |= OptionFlag.TILEABLE  # Window > Tile only arranges tileable windows

    def compose_content(self) -> ComposeResult:
        yield from ()

    def compose(self) -> ComposeResult:
        yield IndicatorFrame(title=self._title, flags=self._window_flags, active=True, number=self.number)
        with Container(classes="tv-window-content"):
            yield from self.compose_content()


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

    BINDINGS = [Binding("ctrl+space,ctrl+@", "complete", "Complete", show=False)]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.tv_options = OptionFlag.SELECTABLE
        self._popup: CompletionPopup | None = None
        self._signature: InfoPopup | None = None  # the call's signature, over the line
        self._doc: InfoPopup | None = None  # the documentation of the selected completion
        self._typed = False  # the last change came from a key typed here
        self._completion_pending = False

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
        return complete(
            self.text, offset, self.tokens, self.dialect,
            data=data, template=self.path, roots=self.roots, explicit=explicit,
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
        frame = self.frame
        if frame is None or not isinstance(frame, IndicatorFrame):
            return
        row, col = self.editor.cursor_location
        frame.set_indicator(f"{'*' if self.dirty else ' '} {row + 1}:{col + 1}")

    def on_command_message(self, message: CommandMessage) -> None:
        # The close icon must go through the app, which asks about unsaved changes.
        if message.command == Command.CLOSE:
            message.stop()
            message.prevent_default()  # Window.close() would skip the unsaved-changes check
            self.app.close_window(self)  # type: ignore[attr-defined]


# Folders that are never worth browsing in the project window.
HIDDEN_NAMES = {".git", ".hg", ".svn", "__pycache__", ".venv", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".idea"}


class ProjectTree(DirectoryTree, TVViewMixin):
    """Project explorer: Ins new file, F7 new folder, F2 rename, Del delete,
    Ctrl+R refresh, Alt+F10 (or a right click) the local menu."""

    # Single-width glyphs: the default emoji icons are double width and not in the TV style.
    ICON_NODE = "▸ "
    ICON_NODE_EXPANDED = "▾ "
    ICON_FILE = "  "
    BINDINGS = [
        Binding("insert", "request('new_file')", "New file", show=False),
        Binding("f7", "request('new_folder')", "New folder", show=False),
        Binding("f2", "request('rename')", "Rename", show=False),
        Binding("delete", "request('delete')", "Delete", show=False),
        Binding("ctrl+r", "request('refresh')", "Refresh", show=False),
        Binding("alt+f10,shift+f10", "request('menu')", "Local menu", show=False),
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

    def __init__(self, *args, icons: str = icons_mod.PLAIN, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.tv_options = OptionFlag.SELECTABLE
        self.icons = icons

    def set_icons(self, mode: str) -> None:
        if mode != self.icons:
            self.icons = mode
            self._invalidate()
            self.refresh()

    def render_label(self, node, base_style, style):
        text = super().render_label(node, base_style, style)
        if self.icons != icons_mod.NERD or node.data is None or not self.is_mounted:
            return text
        folder = node._allow_expand
        glyph, colour = icons_mod.icon_for(node.data.path, folder=folder, expanded=node.is_expanded)
        if folder:
            look = base_style + self.get_component_rich_style("directory-tree--folder", partial=True)
        else:
            look = base_style + (Style(color=colour) if colour else self.get_component_rich_style("directory-tree--file", partial=True))
        prefix = len(self.ICON_NODE)
        return Text.assemble(text[:prefix], (glyph + " ", look + style), text[prefix:])

    def filter_paths(self, paths):
        return [p for p in paths if p.name not in HIDDEN_NAMES and not p.name.endswith(".egg-info")]

    def action_request(self, action: str) -> None:
        self.post_message(self.Request(self, action, self.cursor_screen_at() if action == "menu" else None))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button == 3:
            event.stop()
            line = event.y + self.scroll_offset.y
            if 0 <= line < self.last_line + 1:
                self.cursor_line = line
            self.post_message(self.Request(self, "menu", (event.screen_x, event.screen_y)))

    async def _on_click(self, event: events.Click) -> None:
        if event.button == 3:  # the right button opens the local menu (on mouse down), not the file
            event.stop()
            event.prevent_default()

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

    async def reveal(self, path: Path) -> None:
        """Reload the folders on the way to ``path`` and put the cursor on it."""
        root = Path(self.path).resolve()
        path = path.resolve()
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            return
        node = self.root
        await self.reload_node(node)
        current = root
        for part in parts:
            current = current / part
            child = next((c for c in node.children if c.data is not None and c.data.path == current), None)
            if child is None:
                return
            node = child
            if current != path and node.allow_expand:
                await self.reload_node(node)
        _ = self._tree_lines  # lines are rebuilt lazily: node.line is -1 until then
        self.move_cursor(node, animate=False)


class ProjectWindow(_TVWindow):
    WIDTH = 32

    def __init__(self, root: Path, icons: str = icons_mod.PLAIN) -> None:
        self.root = root
        super().__init__(root.name or str(root), flags=WindowFlag.MOVE | WindowFlag.CLOSE | WindowFlag.GROW)
        self.project_tree = ProjectTree(root, icons=icons)

    def compose_content(self) -> ComposeResult:
        yield self.project_tree

    def on_command_message(self, message: CommandMessage) -> None:
        if message.command == Command.CLOSE:
            message.stop()
            message.prevent_default()  # Window.close() would skip the unsaved-changes check
            self.app.close_window(self)  # type: ignore[attr-defined]


class OutputWindow(_TVWindow):
    """Rendered output of a template (read only; leftover Div tags stay highlighted)."""

    def __init__(self, number: int = 0) -> None:
        super().__init__("Output", number=number)
        self.view = EditorView("", read_only=True)
        self.template: Path | None = None
        self.summary = ""

    def compose_content(self) -> ComposeResult:
        yield self.view

    def show(self, template: Path, output: str, summary: str) -> None:
        self.template = template
        self.summary = summary
        self.title = f"Output: {template.name}"
        self.view.load_text(output)



@dataclass(frozen=True)
class MessageItem:
    """One line of the Messages window; with a location it jumps to the editor."""

    text: str
    path: Path | None = None
    start: int | None = None
    end: int | None = None


class MessageList(ListBox):
    DEFAULT_CSS = """
    MessageList { background: $panel; }
    MessageList > .list-viewer--normal { color: $text; background: $panel; }
    MessageList > .list-viewer--focused { color: $foreground; background: $background; }
    """
    can_focus = True  # textual-vision's ListViewer does not set it: keys would go to the editor

    def select_item(self, item: int) -> None:
        super().select_item(item)
        window = self.parent.parent if self.parent is not None else None
        if isinstance(window, MessagesWindow):
            window.activate(item)

    def on_click(self, event) -> None:
        if event.chain >= 2:
            self.select_item(self.focused)


class MessagesWindow(_TVWindow):
    """Turbo Pascal style message window: Div checks of the template and render messages.

    Enter (or a double click) on a located message jumps to it in the editor.
    """

    def __init__(self, number: int = 0) -> None:
        super().__init__("Messages", number=number)
        self.list = MessageList([])
        self.items: list[MessageItem] = []

    def compose_content(self) -> ComposeResult:
        yield self.list

    def show(self, items: list[MessageItem]) -> None:
        if items == self.items:
            return
        keep = self.list.focused if self.items and len(items) == len(self.items) else 0
        self.items = items or [MessageItem("(no messages)")]
        self.list.set_list([item.text for item in self.items])
        if keep:
            self.list.focus_item(min(keep, len(self.items) - 1))

    def activate(self, index: int) -> None:
        if 0 <= index < len(self.items):
            item = self.items[index]
            if item.path is not None and item.start is not None:
                # After the key (Enter) is done, or the editor would receive it.
                self.app.call_later(self.app.goto_location, item.path, item.start, item.end)  # type: ignore[attr-defined]
