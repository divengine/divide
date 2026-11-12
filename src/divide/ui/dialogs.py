"""Turbo Vision dialogs: message boxes and the file open / save-as dialog."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.constants import Command
from textual_vision.dialogs import Dialog
from textual_vision.frame import Frame
from textual_vision.input_line import InputLine
from textual_vision.label import Label
from textual_vision.list_box import ListBox


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
