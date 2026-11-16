"""Turbo Vision dialogs: message boxes and the file open / save-as dialog."""

from __future__ import annotations

import fnmatch
from datetime import datetime
from pathlib import Path

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from rich.segment import Segment
from textual.screen import ModalScreen
from textual.strip import Strip
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.cluster import CheckBoxes, Cluster, RadioButtons
from textual_vision.constants import Command
from textual_vision.dialogs import Dialog
from textual_vision.input_line import InputLine
from textual_vision.label import Label
from textual_vision.list_box import ListBox

from divide.editor.search import SearchOptions
from divide.ui.history import HistoryInput
from divide.ui.shadow import install_shadows
from divide.ui.windows import PassiveScrollBar, RuleFrame

CM_CHANGE_ALL = Command.USER + 100


# Textual runs the handler of every class in the MRO unless prevent_default()
# is called, so handlers here never call super(): they prevent_default() when
# they replace the base behaviour and simply return when they extend it.


class DialogScreen(ModalScreen[Command]):
    """Runs one Dialog modally over the desktop (no dimming, centred)."""

    DEFAULT_CSS = """
    DialogScreen { align: center middle; background: transparent; layers: windows; }
    """
    BINDINGS = [Binding("escape", "cancel", show=False)]

    def __init__(self, dialog: Dialog) -> None:
        super().__init__()
        install_shadows(self)
        self.dialog = dialog
        self._dismissed = False

    def compose(self) -> ComposeResult:
        yield self.dialog

    def action_cancel(self) -> None:
        self.dialog.end_modal(Command.CANCEL)

    def on_dialog_dialog_closed(self, message: Dialog.DialogClosed) -> None:
        message.stop()
        if not self._dismissed:
            self._dismissed = True
            self.dismiss(message.result)


class _Dialog(Dialog):
    """Dialog whose children are composed inside the window content."""

    DEFAULT_CSS = """
    _Dialog > .tv-window-content { margin: 1 2; layout: vertical; }
    _Dialog RuleFrame .frame--active, _Dialog RuleFrame .frame--passive { color: $divide-dialog-frame; }
    _Dialog RuleFrame .frame--title { color: $divide-dialog-title; }
    _Dialog .dlg-text { color: $text; background: $surface; width: 1fr; height: auto; }
    _Dialog .dlg-buttons { height: 2; align-horizontal: center; margin-top: 1; }
    _Dialog .dlg-buttons Button { margin: 0 1; }
    """

    def compose_content(self) -> ComposeResult:
        yield from ()

    def compose(self) -> ComposeResult:
        yield RuleFrame(title=self._title, flags=self._window_flags, active=True)
        with Container(classes="tv-window-content"):
            yield from self.compose_content()

    def end_modal(self, command: Command) -> None:
        if command != Command.CANCEL and self.valid(command):
            for line in self.query(HistoryInput):
                line.remember()  # what was accepted joins the line's history
        super().end_modal(command)

    def on_key(self, event: events.Key) -> None:
        # Enter in an input line or a cluster presses the default button, as in Turbo Vision.
        if event.key == "enter" and isinstance(self.current, (InputLine, Cluster, HistoryInput)):
            default = next((b for b in self.query(Button) if b.is_default), None)
            if default is not None:
                event.stop()
                event.prevent_default()
                default.press()


class MessageBox(_Dialog):
    """Text plus a row of buttons. Plain letters also press the buttons."""

    def __init__(self, title: str, text: str, buttons: list[tuple[str, Command, str]], *, width: int = 52) -> None:
        super().__init__(title=title)
        self._text = text
        self._buttons = buttons
        lines = sum(max(1, -(-len(part) // (width - 6))) for part in text.split("\n"))
        self.styles.width = width
        self.styles.height = lines + 7

    def compose_content(self) -> ComposeResult:
        yield Static(self._text, classes="dlg-text", markup=False)
        with Horizontal(classes="dlg-buttons"):
            for i, (label, command, bid) in enumerate(self._buttons):
                yield Button(label, command, is_default=(i == 0), id=bid)

    def on_key(self, event: events.Key) -> None:
        if event.character and len(event.character) == 1:
            letter = event.character.lower()
            for child in self.query(Button):
                if child.hotkey == letter:
                    event.stop()
                    event.prevent_default()
                    child.press()
                    return


def confirm_save(name: str) -> MessageBox:
    return MessageBox(
        "Confirm",
        f"{name} has been modified. Save?",
        [("~Y~es", Command.YES, "yes"), ("~N~o", Command.NO, "no"), ("~C~ancel", Command.CANCEL, "cancel")],
    )


def about_box(version: str) -> MessageBox:
    return MessageBox(
        "About",
        f"divide {version}\n\nTerminal IDE for the Divengine projects.\nhttps://github.com/divengine",
        [("O~K~", Command.OK, "ok")],
        width=48,
    )


class FileList(ListBox):
    """The files of the folder, on Turbo Pascal's cyan: the chosen one white on
    green while the list has the focus, yellow when the focus is elsewhere.
    Reports the chosen entry and accepts on a double click."""

    COMPONENT_CLASSES = ListBox.COMPONENT_CLASSES | {"list-viewer--selected"}
    DEFAULT_CSS = """
    FileList { background: $divide-list-bg; }
    FileList > .list-viewer--normal { color: $divide-list-text; background: $divide-list-bg; }
    FileList > .list-viewer--focused { color: $divide-list-focused; background: $divide-list-focused-bg; }
    FileList > .list-viewer--selected { color: $divide-list-selected; background: $divide-list-bg; }
    """

    can_focus = True  # Tab brings the keys here, not only Turbo Vision's focus

    def __init__(self, dialog: "FileDialog", **kwargs) -> None:
        super().__init__(**kwargs)
        self._dialog = dialog

    def focus_item(self, item: int) -> None:
        super().focus_item(item)
        self._dialog.entry_focused(self.focused)

    def select_item(self, item: int) -> None:
        self._dialog.entry_chosen(item)

    def on_click(self, event: events.Click) -> None:
        if event.chain >= 2:
            self.select_item(self.focused)

    def on_focus(self) -> None:
        self.refresh()

    def on_blur(self) -> None:
        self.refresh()

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        item = self.top_item + y
        normal = self.get_component_rich_style("list-viewer--normal")
        if not 0 <= item < self.range:
            return Strip([Segment(" " * width, normal)], width)
        if item == self.focused:
            style = self.get_component_rich_style("list-viewer--focused" if self.has_focus else "list-viewer--selected")
        else:
            style = normal
        text = (" " + self.get_text(item))[:width].ljust(width)  # a space before, as Turbo Pascal's
        return Strip([Segment(text, style)], width)


def file_info(path: Path, name: str, width: int) -> str:
    """Turbo Pascal's second line: ``NAME   size   May 4, 2019  10:16pm``."""
    try:
        st = path.stat()
    except OSError:
        return name[:width]
    t = datetime.fromtimestamp(st.st_mtime)
    when = f"{t:%b} {t.day}, {t.year}  {t.hour % 12 or 12}:{t.minute:02d}{'am' if t.hour < 12 else 'pm'}"
    size = "Directory" if path.is_dir() else str(st.st_size)
    room = max(1, width - len(when) - len(size) - 4)
    shown = name if len(name) <= room else name[:room - 3] + "..."
    return f"{shown:<{room}}  {size}  {when}"[:width]


class FileDialog(_Dialog):
    """Open / Save-as dialog, laid out as Turbo Pascal's: the name line (with
    its history), the files on cyan with their scroll bar, the buttons in a
    column at the right, and the pane below with the folder and the file under
    the bar (size, date). One column of names: today's are longer than 8.3.

    Entries are ``..``, folders (``name/``) and files matching the wildcard.
    ``chosen`` holds the resulting path once the dialog ends with OK. With
    ``folders`` it lists only folders and OK on ``.`` chooses the one shown.
    """

    DEFAULT_CSS = """
    FileDialog { width: 66; height: 22; }
    FileDialog > .tv-window-content { margin: 1 1; }
    FileDialog .fd-body { height: 1fr; padding: 0 1; }
    FileDialog .fd-left { width: 1fr; height: 1fr; }
    FileDialog .fd-files-label { margin-top: 1; }
    FileDialog .fd-files { height: 1fr; margin-bottom: 1; }
    FileDialog FileList { width: 1fr; height: 1fr; }
    FileDialog .fd-bar { width: 1; height: 1fr; background: $divide-list-bg; }
    FileDialog .fd-bar .scrollbar--arrow, FileDialog .fd-bar .scrollbar--track, FileDialog .fd-bar .scrollbar--thumb {
        color: $divide-list-scroll; background: $divide-list-bg;
    }
    FileDialog .fd-buttons { width: 13; height: 1fr; margin-left: 2; padding-top: 1; }
    FileDialog .fd-buttons Button { width: 12; margin-bottom: 1; }
    FileDialog .fd-info { width: 1fr; height: 2; padding: 0 1; color: $divide-info-text; background: $divide-info-bg; }
    """

    def __init__(
        self, title: str, directory: Path, *, name: str = "", pattern: str = "*", ok_label: str = "~O~pen",
        folders: bool = False,
    ) -> None:
        super().__init__(title=title)
        self.folders = folders
        if folders:
            pattern = "."
        self.directory = directory.resolve()
        self.pattern = pattern
        self.ok_label = ok_label
        self.chosen: Path | None = None
        self.input = InputLine(max_len=1024)
        self.input.data = name or pattern
        self.list = FileList(self)
        self.bar = PassiveScrollBar(classes="fd-bar")
        self.list.v_scroll_bar = self.bar
        self.info = Static("", classes="fd-info", markup=False)
        self.info_lines = ("", "")
        self._entries: list[str] = []
        self._syncing = False

    def compose_content(self) -> ComposeResult:
        with Horizontal(classes="fd-body"):
            with Vertical(classes="fd-left"):
                yield Label("~N~ame (. is the folder below)" if self.folders else "~N~ame", link=self.input)
                yield HistoryInput(self.input, "folder" if self.folders else "file")
                yield Label("~F~olders" if self.folders else "~F~iles", link=self.list, classes="fd-files-label")
                with Horizontal(classes="fd-files"):
                    yield self.list
                    yield self.bar
            with Vertical(classes="fd-buttons"):
                yield Button(self.ok_label, Command.OK, is_default=True, id="ok")
                yield Button("Cancel", Command.CANCEL, id="cancel")
        yield self.info

    def on_mount(self) -> None:
        self.call_after_refresh(self._load)

    def show_info(self, index: int | None = None) -> None:
        """The pane: the folder and its wildcard, then the entry under the bar."""
        width = max(10, (self.info.size.width or self.size.width or 64) - 2)
        first = str(self.directory / self.pattern) if not self.folders else str(self.directory)
        if len(first) > width:
            first = "..." + first[-(width - 3):]
        second = ""
        if index is not None and 0 <= index < len(self._entries):
            entry = self._entries[index]
            second = file_info(self.directory / entry.rstrip("/"), entry, width)
        self.info_lines = (first, second)
        self.info.update(f"{first}\n{second}")
    # ------------------------------------------------------------ entries
    def _load(self) -> None:
        try:
            children = sorted(self.directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            children = []
        entries = [] if self.directory.parent == self.directory else [".."]
        for child in children:
            if child.name.startswith("."):
                continue
            if child.is_dir():
                entries.append(child.name + "/")
            elif not self.folders and fnmatch.fnmatch(child.name, self.pattern):
                entries.append(child.name)
        self._entries = entries
        self._syncing = True
        self.list.set_list(entries)
        self._syncing = False
        self.show_info(self.list.focused if entries else None)
        self.input.refresh()

    def entry_focused(self, index: int) -> None:
        if self._syncing or not (0 <= index < len(self._entries)):
            return
        self.show_info(index)
        entry = self._entries[index]
        if not entry.endswith("/") and entry != "..":
            self.input.data = entry
            self.input._cursor_pos = len(entry)
            self.input.refresh()

    def entry_chosen(self, index: int) -> None:
        if 0 <= index < len(self._entries):
            self.accept(self._entries[index])

    # ------------------------------------------------------------- accept
    def accept(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if self.folders and text == ".":
            self.chosen = self.directory
            self.end_modal(Command.OK)
            return
        target = Path(text).expanduser()
        if not target.is_absolute():
            target = self.directory / target
        if any(ch in target.name for ch in "*?[") and not self.folders:
            if target.parent.is_dir():
                self.directory = target.parent.resolve()
                self.pattern = target.name
                self._load()
            return
        if target.is_dir():
            self.directory = target.resolve()
            self.input.data = self.pattern
            self._load()
            return
        if not target.parent.is_dir():
            self.app.notify(f"No such folder: {target.parent}", severity="error")
            return
        self.chosen = target.resolve()
        self.end_modal(Command.OK)

    def on_command_message(self, message) -> None:
        if message.command == Command.OK:
            message.stop()
            message.prevent_default()  # Dialog would end_modal(OK) without a chosen path
            if self.current is self.list and 0 <= self.list.focused < len(self._entries):
                entry = self._entries[self.list.focused]
                if entry.endswith("/") or entry == "..":
                    self.accept(entry)
                    return
            self.accept(self.input.data)

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter" and self.input.has_focus:
            event.stop()
            event.prevent_default()
            self.accept(self.input.data)


class SearchDialog(_Dialog):
    """Find (``replace=False``) or Replace dialog, laid out like Turbo Pascal's.

    After OK / Change all: ``search_text``, ``replacement`` and ``options`` hold the input.
    """

    DEFAULT_CSS = """
    SearchDialog { width: 62; }
    SearchDialog HistoryInput { margin-bottom: 1; }
    SearchDialog .sd-row { height: auto; }
    SearchDialog .sd-col { width: 1fr; height: auto; }
    SearchDialog Cluster { margin-bottom: 1; width: 1fr; }
    """

    def __init__(self, *, replace: bool, query: str, replacement: str, options: SearchOptions) -> None:
        super().__init__(title="Replace" if replace else "Find")
        self.replace = replace
        self.styles.height = 19 if replace else 16
        self.query_input = InputLine(max_len=1024)
        self.query_input.data = query
        self.replace_input = InputLine(max_len=1024)
        self.replace_input.data = replacement
        flags = ["~C~ase sensitive", "~W~hole words only", "~R~egular expression"]
        if replace:
            flags.append("~P~rompt on replace")
        self.flags = CheckBoxes(flags)
        self.flags.value = (
            int(options.case_sensitive) | int(options.whole_words) << 1 | int(options.regex) << 2 | int(options.prompt) << 3
        ) & ((1 << len(flags)) - 1)
        self.direction = RadioButtons(["Forwar~d~", "~B~ackward"])
        self.direction.value = 2 if options.backward else 1
        self.origin = RadioButtons(["~F~rom cursor", "~E~ntire scope"])
        self.origin.value = 2 if options.entire_scope else 1
        self.search_text = query
        self.replacement = replacement
        self.options = options

    def compose_content(self) -> ComposeResult:
        yield Label("~T~ext to find", link=self.query_input)
        yield HistoryInput(self.query_input, "find")
        if self.replace:
            yield Label("~N~ew text", link=self.replace_input)
            yield HistoryInput(self.replace_input, "replace")
        with Horizontal(classes="sd-row"):
            with Vertical(classes="sd-col"):
                yield Label("Options", link=self.flags)
                yield self.flags
            with Vertical(classes="sd-col"):
                yield Label("Direction", link=self.direction)
                yield self.direction
                yield Label("Origin", link=self.origin)
                yield self.origin
        with Horizontal(classes="dlg-buttons"):
            yield Button("O~K~", Command.OK, is_default=True, id="ok")
            if self.replace:
                yield Button("Change ~a~ll", CM_CHANGE_ALL, id="all")
            yield Button("Cancel", Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.query_input.select_all)

    def _collect(self) -> None:
        bits = self.flags.value
        self.search_text = self.query_input.data
        self.replacement = self.replace_input.data
        self.options = SearchOptions(
            case_sensitive=bool(bits & 1),
            whole_words=bool(bits & 2),
            regex=bool(bits & 4),
            prompt=bool(bits & 8) if self.replace else self.options.prompt,
            backward=self.direction.value == 2,
            entire_scope=self.origin.value == 2,
        )

    def on_command_message(self, message) -> None:
        if message.command == Command.OK:
            self._collect()  # Dialog's own handler then ends the modal
        elif message.command == CM_CHANGE_ALL:
            message.stop()
            message.prevent_default()
            self._collect()
            self.end_modal(CM_CHANGE_ALL)


def replace_prompt() -> MessageBox:
    return MessageBox(
        "Replace",
        "Replace this occurrence?",
        [("~Y~es", Command.YES, "yes"), ("~N~o", Command.NO, "no"), ("~A~ll", CM_CHANGE_ALL, "all"), ("Cancel", Command.CANCEL, "cancel")],
        width=50,
    )


def information(title: str, text: str) -> MessageBox:
    return MessageBox(title, text, [("O~K~", Command.OK, "ok")], width=max(36, min(70, len(text) + 8)))


class GotoLineDialog(_Dialog):
    DEFAULT_CSS = """
    GotoLineDialog { width: 40; height: 10; }
    GotoLineDialog HistoryInput { width: 15; }
    """

    def __init__(self, line: int) -> None:
        super().__init__(title="Go to Line Number")
        self.input = InputLine(max_len=9)
        self.input.data = str(line)
        self.line: int | None = None

    def compose_content(self) -> ComposeResult:
        yield Label("Enter new line ~n~umber", link=self.input)
        yield HistoryInput(self.input, "line")
        with Horizontal(classes="dlg-buttons"):
            yield Button("O~K~", Command.OK, is_default=True, id="ok")
            yield Button("Cancel", Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.input.select_all)

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        try:
            self.line = int(self.input.data.strip())
        except ValueError:
            self.app.notify("Not a line number", severity="error")
            return False
        return self.line >= 1


CM_BROWSE = Command.USER + 101


async def browse_into(
    dialog: _Dialog, line: InputLine, title: str, pattern: str, start: Path, *, folders: bool = False
) -> bool:
    """File dialog over ``dialog``; the chosen file's absolute path goes into ``line``.

    Call from a worker. ``start``: the folder to begin in, unless ``line`` already
    names a file or folder that exists (relative paths are taken from ``start``).
    ``folders``: choose a folder, not a file."""
    current = line.data.strip()
    if current:
        here = Path(current).expanduser()
        here = here if here.is_absolute() else start / here
        if here.is_dir():
            start = here
        elif here.parent.is_dir():
            start = here.parent
    chooser = FileDialog(title, start, pattern=pattern, ok_label="~O~K", folders=folders)
    if await dialog.app.push_screen_wait(DialogScreen(chooser)) != Command.OK or chooser.chosen is None:
        return False
    line.data = str(chooser.chosen)
    line._cursor_pos = len(line.data)
    line.refresh()
    return True


class InputDialog(_Dialog):
    """One line of text (a name or a path): ``value`` holds it after OK.

    With ``browse=(pattern, folder)`` a Browse button picks a file with the file
    dialog and writes its absolute path (relative paths stay welcome)."""

    DEFAULT_CSS = """
    InputDialog { width: 64; height: 9; }
    InputDialog HistoryInput { width: 1fr; }
    InputDialog .dlg-hint { color: $text-muted; background: $surface; height: 1; }
    """

    def __init__(
        self,
        title: str,
        label: str,
        text: str = "",
        *,
        hint: str = "",
        select: tuple[int, int] | None = None,
        browse: tuple[str, Path] | None = None,
        allow_empty: bool = False,
        history: str | None = None,
    ) -> None:
        super().__init__(title=title)
        self.history = history or f"input:{title}"  # one history per kind of question
        self.browse = browse
        self.allow_empty = allow_empty
        self.input = InputLine(max_len=1024)
        self.input.data = text
        self.label = label
        self.hint = hint
        self.select = select
        self.value: str | None = None

    def compose_content(self) -> ComposeResult:
        yield Label(self.label, link=self.input)
        yield HistoryInput(self.input, self.history)
        yield Static(self.hint, classes="dlg-hint", markup=False)
        with Horizontal(classes="dlg-buttons"):
            yield Button("O~K~", Command.OK, is_default=True, id="ok")
            if self.browse is not None:
                yield Button("~B~rowse...", CM_BROWSE, id="browse")
            yield Button("Cancel", Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self._place_cursor)

    def on_command_message(self, message) -> None:
        if message.command == CM_BROWSE and self.browse is not None:
            message.stop()
            message.prevent_default()
            pattern, folder = self.browse
            self.run_worker(browse_into(self, self.input, self.title_text(), pattern, folder), exclusive=True)

    def title_text(self) -> str:
        return f"{self._title}: browse"

    def _place_cursor(self) -> None:
        if self.select is None:
            self.input.select_all()
            return
        start, end = self.select
        line = self.input
        line._sel_start, line._sel_end, line._cursor_pos = start, end, end
        line.refresh()

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        self.value = self.input.data.strip()
        return bool(self.value) or self.allow_empty


def confirm(title: str, text: str) -> MessageBox:
    return MessageBox(title, text, [("~Y~es", Command.YES, "yes"), ("~N~o", Command.NO, "no")], width=max(40, min(64, len(text) + 8)))
