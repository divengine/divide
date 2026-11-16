"""Search > Find in files (Shift+F2, Borland Pascal's Tools > Grep): a text in every file of the project.

Search > Find looks in the file being edited; this looks in all of the
project's files (the same list Go to file holds: git's when the project is a
repository), or the ones a mask names (``*.tpl;*.php``), with the Find
dialog's options: case sensitive, whole words only, regular expression. The
files open in editors are searched as they are being edited, saved or not.

What it finds goes to a window at the bottom, as Turbo Pascal's grep put it in
the Messages window: ``parts/header.tpl(12): <the line>``, a row per line with a match;
Enter (or a double click) opens the file there with the match selected.
"""

from __future__ import annotations

from divide.i18n import _, ngettext

import asyncio
import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual_vision.button import Button
from textual_vision.cluster import CheckBoxes
from textual_vision.constants import Command
from textual_vision.input_line import InputLine
from textual_vision.label import Label

from divide.editor.search import SearchError, SearchOptions, compile_pattern
from divide.ui.dialogs import _Dialog, information
from divide.ui.history import HistoryInput
from divide.ui.palette import project_files
from divide.ui.windows import LocationsWindow, MessageItem

MAX_MATCHES = 2000
MAX_BYTES = 2_000_000  # larger files are not text to search
MAX_SHOWN_LINE = 200


@dataclass(frozen=True)
class Hit:
    rel: str
    line: int  # 1-based
    start: int  # offsets into the file's text
    end: int
    text: str  # the line, trimmed

    @property
    def label(self) -> str:
        return f"{self.rel}({self.line}): {self.text}"


def masks(text: str) -> list[str]:
    return [m for m in re.split(r"[;,\s]+", text.strip()) if m] or ["*"]


def wanted(rel: str, patterns: list[str]) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p) for p in patterns)


def read_text(path: Path) -> str | None:
    """The file as text, or None for what is not (too large, binary, unreadable)."""
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    text = data.decode("utf-8", "replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def search(root: Path, files: list[str], pattern: re.Pattern[str], *, edited: dict[str, str] | None = None,
           limit: int = MAX_MATCHES) -> tuple[list[Hit], int]:
    """Every match of ``pattern`` in ``files`` (relative to ``root``); ``edited`` holds the
    texts of the files open in editors. Returns the hits (at most ``limit``) and how many
    files had one."""
    edited = edited or {}
    hits: list[Hit] = []
    in_files = 0
    for rel in files:
        text = edited.get(rel)
        if text is None:
            text = read_text(root / rel)
        if not text:
            continue
        line, line_start, counted = 1, 0, 0
        found = False
        for m in pattern.finditer(text):
            if m.end() == m.start():
                continue
            line += text.count("\n", counted, m.start())
            counted = m.start()
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.start())
            shown = text[line_start: line_end if line_end != -1 else len(text)].strip()
            if len(shown) > MAX_SHOWN_LINE:
                shown = shown[:MAX_SHOWN_LINE - 3] + "..."
            hits.append(Hit(rel, line, m.start(), m.end(), shown))
            found = True
            if len(hits) >= limit:
                return hits, in_files + 1
        in_files += found
    return hits, in_files


class FindInFilesDialog(_Dialog):
    """The text, the files to look in and the Find dialog's options."""

    DEFAULT_CSS = """
    FindInFilesDialog { width: 62; height: 15; }
    FindInFilesDialog HistoryInput { margin-bottom: 1; }
    FindInFilesDialog CheckBoxes { width: 1fr; }
    """

    def __init__(self, query: str, options: SearchOptions) -> None:
        super().__init__(title=_('Find in files'))
        self.query_input = InputLine(max_len=1024)
        self.query_input.data = query
        self.mask_input = InputLine(max_len=256)
        self.mask_input.data = "*"
        self.flags = CheckBoxes([_('~C~ase sensitive'), _('~W~hole words only'), _('~R~egular expression')])
        self.flags.value = int(options.case_sensitive) | int(options.whole_words) << 1 | int(options.regex) << 2
        self.search_text = query
        self.mask = "*"
        self.options = options

    def compose_content(self) -> ComposeResult:
        yield Label(_('~T~ext to find'), link=self.query_input)
        yield HistoryInput(self.query_input, "find")
        yield Label(_('~F~iles (*.tpl;*.php)'), link=self.mask_input)
        yield HistoryInput(self.mask_input, "find-files")
        yield Label(_('Options'), link=self.flags)
        yield self.flags
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('O~K~'), Command.OK, is_default=True, id="ok")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.query_input.select_all)

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        bits = self.flags.value
        self.search_text = self.query_input.data
        self.mask = self.mask_input.data.strip() or "*"
        self.options = SearchOptions(case_sensitive=bool(bits & 1), whole_words=bool(bits & 2), regex=bool(bits & 4))
        return bool(self.search_text)


class FindResultsWindow(LocationsWindow):
    """What Find in files found, one row per line with a match."""

    EMPTY = _('(nothing found)')
    HINT = _('Enter go to the match')

    def __init__(self, number: int = 0) -> None:
        super().__init__(_('Find in files'), number=number)


def result_items(root: Path, query: str, mask: str, hits: list[Hit], in_files: int) -> list[MessageItem]:
    """The heading, then a row per line with a match (the first one on it is the one selected)."""
    many = len(hits) >= MAX_MATCHES
    count = ngettext("{n} match", "{n} matches", len(hits)).format(n=f"{len(hits)}{'+' if many else ''}")
    files = ngettext("{n} file", "{n} files", in_files).format(n=in_files)
    head = _('"{query}" in {mask}: {count} in {files}').format(query=query, mask=mask, count=count, files=files)
    rows, seen = [MessageItem(head)], set()
    for h in hits:
        if (h.rel, h.line) not in seen:
            seen.add((h.rel, h.line))
            rows.append(MessageItem(h.label, root / h.rel, h.start, h.end))
    return rows


class FindInFilesMixin:
    """Search > Find in files (mixed into the Divide app)."""

    def find_results_window(self) -> FindResultsWindow | None:
        return next((w for w in self.windows() if isinstance(w, FindResultsWindow)), None)

    async def find_in_files(self) -> None:
        editor = self.active_editor()
        query = editor.editor.selected_text if editor is not None and "\n" not in editor.editor.selected_text else ""
        dialog = FindInFilesDialog(query or self.search_query, self.search_options)
        if await self.run_dialog(dialog) != Command.OK:
            return
        try:
            pattern = compile_pattern(dialog.search_text, dialog.options)
        except SearchError as exc:
            await self.run_dialog(information(_('Find in files'), str(exc)))
            return
        self.search_query = dialog.search_text
        root = self.root.resolve()
        patterns = masks(dialog.mask)
        edited = {}
        for window in self.editor_windows():
            path = window.path.resolve() if window.path is not None else None
            if path is not None and path.is_relative_to(root):
                edited[path.relative_to(root).as_posix()] = window.editor.text
        with self.busy(_('Finding in files')):
            files = await asyncio.to_thread(project_files, root)
            files = [f for f in files if wanted(f, patterns)]
            hits, in_files = await asyncio.to_thread(search, root, files, pattern, edited=edited)
        window = self.find_results_window()
        if window is None:
            window = self._open_messages_window(window=FindResultsWindow(number=self._free_number()))
        window.show(result_items(root, dialog.search_text, dialog.mask, hits, in_files))
        window.list.focus_item(1 if hits else 0)
        self.raise_window(window)
        window.list.focus()
