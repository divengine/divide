"""Turbo Vision dialogs: message boxes and the file open / save-as dialog."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.cluster import CheckBoxes, RadioButtons
from textual_vision.constants import Command
from textual_vision.dialogs import Dialog
from textual_vision.frame import Frame
from textual_vision.input_line import InputLine
from textual_vision.label import Label
from textual_vision.list_box import ListBox

from divide.editor.search import SearchOptions
from divide.ui.shadow import install_shadows

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
    _Dialog .dlg-text { color: $text; background: $surface; width: 1fr; height: auto; }
    _Dialog .dlg-buttons { height: 2; align-horizontal: center; margin-top: 1; }
    _Dialog .dlg-buttons Button { margin: 0 1; }
    """

    def compose_content(self) -> ComposeResult:
        yield from ()

    def compose(self) -> ComposeResult:
        yield Frame(title=self._title, flags=self._window_flags, active=True)
        with Container(classes="tv-window-content"):
            yield from self.compose_content()

    def on_key(self, event: events.Key) -> None:
        # Enter in an input line presses the default button, as in Turbo Vision.
        if event.key == "enter" and isinstance(self.current, InputLine):
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
        yield Static(self._text, classes="dlg-text")
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
    """ListBox that reports the focused entry and accepts on double click."""

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


class FileDialog(_Dialog):
    """Open / Save-as dialog: name line with wildcards, list of entries.

    Entries are ``..``, folders (``name/``) and files matching the wildcard.
    ``chosen`` holds the resulting path once the dialog ends with OK.
    """

    DEFAULT_CSS = """
    FileDialog { width: 64; height: 22; }
    FileDialog InputLine { width: 1fr; }
    FileDialog FileList { height: 1fr; margin-bottom: 0; }
    FileDialog .dlg-dir { color: $text; background: $surface; height: 1; }
    FileDialog Label { margin-top: 0; }
    """

    def __init__(self, title: str, directory: Path, *, name: str = "", pattern: str = "*", ok_label: str = "~O~pen") -> None:
        super().__init__(title=title)
        self.directory = directory.resolve()
        self.pattern = pattern
        self.ok_label = ok_label
        self.chosen: Path | None = None
        self.input = InputLine(max_len=1024)
        self.input.data = name or pattern
        self.list = FileList(self)
        self.dir_label = Static("", classes="dlg-dir")
        self._entries: list[str] = []
        self._syncing = False

    def compose_content(self) -> ComposeResult:
        yield Label("~N~ame", link=self.input)
        yield self.input
        yield Label("~F~iles", link=self.list)
        yield self.list
        yield self.dir_label
        with Horizontal(classes="dlg-buttons"):
            yield Button(self.ok_label, Command.OK, is_default=True, id="ok")
            yield Button("Cancel", Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self._load)

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
            elif fnmatch.fnmatch(child.name, self.pattern):
                entries.append(child.name)
        self._entries = entries
        self._syncing = True
        self.list.set_list(entries)
        self._syncing = False
        self.dir_label.update(str(self.directory))
        self.input.refresh()

    def entry_focused(self, index: int) -> None:
        if self._syncing or not (0 <= index < len(self._entries)):
            return
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
        target = Path(text).expanduser()
        if not target.is_absolute():
            target = self.directory / target
        if any(ch in target.name for ch in "*?["):
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
        if event.key == "enter" and self.current is self.input:
            event.stop()
            event.prevent_default()
            self.accept(self.input.data)


class SearchDialog(_Dialog):
    """Find (``replace=False``) or Replace dialog, laid out like Turbo Pascal's.

    After OK / Change all: ``search_text``, ``replacement`` and ``options`` hold the input.
    """

    DEFAULT_CSS = """
    SearchDialog { width: 62; }
    SearchDialog InputLine { width: 1fr; margin-bottom: 1; }
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
        yield self.query_input
        if self.replace:
            yield Label("~N~ew text", link=self.replace_input)
            yield self.replace_input
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
    GotoLineDialog InputLine { width: 12; }
    """

    def __init__(self, line: int) -> None:
        super().__init__(title="Go to Line Number")
        self.input = InputLine(max_len=9)
        self.input.data = str(line)
        self.line: int | None = None

    def compose_content(self) -> ComposeResult:
        yield Label("Enter new line ~n~umber", link=self.input)
        yield self.input
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


class InputDialog(_Dialog):
    """One line of text (a name): ``value`` holds it after OK."""

    DEFAULT_CSS = """
    InputDialog { width: 56; height: 9; }
    InputDialog InputLine { width: 1fr; }
    InputDialog .dlg-hint { color: $text-muted; background: $surface; height: 1; }
    """

    def __init__(self, title: str, label: str, text: str = "", *, hint: str = "", select: tuple[int, int] | None = None) -> None:
        super().__init__(title=title)
        self.input = InputLine(max_len=1024)
        self.input.data = text
        self.label = label
        self.hint = hint
        self.select = select
        self.value: str | None = None

    def compose_content(self) -> ComposeResult:
        yield Label(self.label, link=self.input)
        yield self.input
        yield Static(self.hint, classes="dlg-hint")
        with Horizontal(classes="dlg-buttons"):
            yield Button("O~K~", Command.OK, is_default=True, id="ok")
            yield Button("Cancel", Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self._place_cursor)

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
        return bool(self.value)


def confirm(title: str, text: str) -> MessageBox:
    return MessageBox(title, text, [("~Y~es", Command.YES, "yes"), ("~N~o", Command.NO, "no")], width=max(40, min(64, len(text) + 8)))
