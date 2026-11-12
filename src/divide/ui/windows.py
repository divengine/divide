"""Turbo Vision windows of the IDE: editor windows and the project tree."""

from __future__ import annotations

from pathlib import Path

from rich.segment import Segment
from rich.style import Style
from textual.app import ComposeResult
from textual.containers import Container
from textual.strip import Strip
from textual.widgets import DirectoryTree
from textual_vision.constants import Command, OptionFlag, WindowFlag
from textual_vision.events import CommandMessage
from textual_vision.frame import Frame
from textual_vision.group import TVViewMixin
from textual_vision.window import Window

from divide.editor.div_editor import DivEditor

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


class IndicatorFrame(Frame):
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


class _TVWindow(Window):
    """Window whose frame is an IndicatorFrame and whose content is composed."""

    def __init__(self, title: str = "", *, number: int = 0, **kwargs) -> None:
        super().__init__(title=title, **kwargs)
        self.number = number

    def compose_content(self) -> ComposeResult:
        yield from ()

    def compose(self) -> ComposeResult:
        yield IndicatorFrame(title=self._title, flags=self._window_flags, active=True, number=self.number)
        with Container(classes="tv-window-content"):
            yield from self.compose_content()


class EditorView(DivEditor, TVViewMixin):
    """The Div editor as a selectable Turbo Vision view."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.tv_options = OptionFlag.SELECTABLE


class EditorWindow(_TVWindow):
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


class ProjectTree(DirectoryTree, TVViewMixin):
    # Single-width glyphs: the default emoji icons are double width and not in the TV style.
    ICON_NODE = "▸ "
    ICON_NODE_EXPANDED = "▾ "
    ICON_FILE = "  "
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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.tv_options = OptionFlag.SELECTABLE


class ProjectWindow(_TVWindow):
    WIDTH = 32

    def __init__(self, root: Path) -> None:
        self.root = root
        super().__init__(root.name or str(root), flags=WindowFlag.MOVE | WindowFlag.CLOSE | WindowFlag.GROW)
        self.project_tree = ProjectTree(root)

    def compose_content(self) -> ComposeResult:
        yield self.project_tree

    def on_command_message(self, message: CommandMessage) -> None:
        if message.command == Command.CLOSE:
            message.stop()
            message.prevent_default()  # Window.close() would skip the unsaved-changes check
            self.app.close_window(self)  # type: ignore[attr-defined]
