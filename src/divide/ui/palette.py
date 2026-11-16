"""Go to file (Ctrl+P) and the command palette (Alt+P), as VS Code's Ctrl+P and Ctrl+Shift+P.

Windows Terminal keeps Ctrl+Shift+P for its own palette, so divide's is Alt+P
(Ctrl+Shift+P still works where the terminal passes it on).

One dialog, two modes: a line to type in and the list of what matches, best
first, the letters that matched lit. In "Go to file" the list holds the
project's files (git's own list when the project is a repository, so what git
ignores stays out); a ``>`` at the start of the line turns it into the command
palette, which holds every entry of the menu bar (``File > Open...``) with its
key, and deleting the ``>`` goes back to the files. Up/Down (PgUp/PgDn) move
the bar while the keys stay in the line; Enter opens the file or runs the
command, Esc closes. With nothing typed, the files open in editors and the
commands run last come first.

The matching is fuzzy as VS Code's: the letters typed, in order, anywhere in
the name; it scores words that start with them, letters that follow one
another and, for files, the file name over its folders.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.strip import Strip
from textual.widgets import Static
from textual_vision.constants import Command
from textual_vision.events import CommandMessage
from textual_vision.input_line import InputLine
from textual_vision.list_box import ListBox
from textual_vision.menus import Menu

from divide.ui import history
from divide.ui.dialogs import _Dialog
from divide.ui.windows import HIDDEN_NAMES, PassiveScrollBar

COMMANDS_PREFIX = ">"
FILES_TITLE = "Go to File"
COMMANDS_TITLE = "Commands"
FILES_HINT = "Type a file name · > for the commands · Enter open · Esc close"
COMMANDS_HINT = "Type a command · delete the > for the files · Enter run · Esc close"
RECENT_COMMANDS = "commands"  # the history of the commands run from here
MAX_FILES = 20000  # what a project lists at most
MAX_SHOWN = 500  # rows of the list
SEPARATORS = "/\\_-. :>"


# ------------------------------------------------------------------ matching
def match(query: str, text: str, name_from: int = 0) -> tuple[float, list[int]] | None:
    """Score ``text`` for ``query`` (its letters in order, any case), or None.

    The best placement of the letters: each one scores, more at the start of
    a word (after ``/ _ - .`` or a capital after a small letter) and when it
    follows the one before; letters from ``name_from`` on (a file's name) score
    more. Linear in the places each letter occurs, so long paths cost little.
    Returns the score and the offsets of the matched letters.
    """
    query = "".join(query.split()).lower()
    if not query:
        return 0.0, []
    low = text.lower()
    positions: list[list[int]] = []
    start = 0
    for i, letter in enumerate(query):
        found = []
        last = len(low) - (len(query) - i)  # room for the letters after this one
        at = low.find(letter, start)
        while at != -1 and at <= last:
            found.append(at)
            at = low.find(letter, at + 1)
        if not found:
            return None
        positions.append(found)
        start = found[0] + 1

    def bonus(p: int) -> float:
        b = 1.0
        if p == 0 or text[p - 1] in SEPARATORS or (text[p].isupper() and text[p - 1].islower()):
            b += 2.0
        if p >= name_from:
            b += 1.0
        return b

    # best[i][k]: the best score with letter i at positions[i][k]; back: where letter i-1 was
    best: list[list[float]] = [[bonus(p) for p in positions[0]]]
    back: list[list[int]] = [[-1] * len(positions[0])]
    for i in range(1, len(query)):
        prev, prev_best = positions[i - 1], best[i - 1]
        row, row_back = [], []
        j, top, top_at = 0, float("-inf"), -1
        for p in positions[i]:
            while j < len(prev) and prev[j] < p:  # the best of the places before p
                if prev_best[j] > top:
                    top, top_at = prev_best[j], j
                j += 1
            if top_at < 0:
                row.append(float("-inf"))
                row_back.append(-1)
                continue
            score, at = top, top_at
            if j and prev[j - 1] == p - 1 and prev_best[j - 1] + 3.0 > score:  # right after the one before
                score, at = prev_best[j - 1] + 3.0, j - 1
            row.append(score + bonus(p))
            row_back.append(at)
        best.append(row)
        back.append(row_back)
    last_row = best[-1]
    k = max(range(len(last_row)), key=last_row.__getitem__)
    if last_row[k] == float("-inf"):
        return None
    score = last_row[k]
    offsets = []
    for i in range(len(query) - 1, -1, -1):
        offsets.append(positions[i][k])
        k = back[i][k]
    offsets.reverse()
    return score - len(text) / 1000, offsets  # the shorter of two equal ones first


# --------------------------------------------------------------------- items
@dataclass
class Item:
    """A row: ``text`` (lit where it matched), ``key`` at the right, ``value`` what it opens or runs."""

    text: str
    value: Any
    key: str = ""
    name_from: int = 0  # where the file name starts: the folders before it are dimmed
    offsets: tuple[int, ...] = ()


def menu_items(menu: Menu, path: tuple[str, ...] = ()) -> list[Item]:
    """Every entry of the menu bar: ``File > Open...``, its key, (command, param)."""
    found: list[Item] = []
    for entry in menu.items:
        if entry.is_separator or entry.disabled:
            continue
        here = (*path, entry.plain_name)
        if entry.sub_menu is not None:
            found.extend(menu_items(entry.sub_menu, here))
        else:
            found.append(Item(" > ".join(here), (entry.command, entry.param), key=entry.key_code))
    return found


def project_files(root: Path, limit: int = MAX_FILES) -> list[str]:
    """The project's files relative to ``root``: git's list when it is a repository (the
    tracked ones and the new ones it does not ignore), else a walk without the folders
    the project tree hides."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            capture_output=True, timeout=5, check=False,
        )
        if done.returncode == 0:
            names = sorted({n for n in done.stdout.decode("utf-8", "replace").split("\0") if n})
            return [n for n in names if (root / n).is_file()][:limit]
    except (OSError, subprocess.SubprocessError):
        pass
    found: list[str] = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in HIDDEN_NAMES and not d.startswith(".") and not d.endswith(".egg-info"))
        rel = Path(folder).relative_to(root)
        for name in sorted(files):
            found.append(str(rel / name) if rel.parts else name)
            if len(found) >= limit:
                return found
    return found


def file_item(rel: str) -> Item:
    return Item(rel, rel, name_from=rel.rfind("/") + 1)


def rank(query: str, items: list[Item], limit: int = MAX_SHOWN) -> list[Item]:
    """The items that match ``query``, best first, each with the offsets to light."""
    scored = []
    for n, item in enumerate(items):
        found = match(query, item.text, item.name_from)
        if found is not None:
            scored.append((-found[0], n, found[1], item))
    scored.sort(key=lambda s: (s[0], s[1]))
    return [Item(i.text, i.value, i.key, i.name_from, tuple(o)) for _, _, o, i in scored[:limit]]


# ------------------------------------------------------------------- dialog
class PaletteList(ListBox):
    """The matches on the dialog lists' cyan: the letters typed lit, folders and keys dimmed."""

    COMPONENT_CLASSES = ListBox.COMPONENT_CLASSES | {
        "palette--match", "palette--match-focused", "palette--dim",
    }
    DEFAULT_CSS = """
    PaletteList { background: $divide-list-bg; }
    PaletteList > .list-viewer--normal { color: $divide-list-text; background: $divide-list-bg; }
    PaletteList > .list-viewer--focused { color: $divide-list-focused; background: $divide-list-focused-bg; }
    PaletteList > .palette--match { color: $divide-list-match; }
    PaletteList > .palette--match-focused { color: $divide-list-match-focused; }
    PaletteList > .palette--dim { color: $divide-list-dim; }
    """

    def __init__(self, dialog: "PaletteDialog", **kwargs) -> None:
        super().__init__(**kwargs)
        self._dialog = dialog
        self.rows: list[Item] = []

    def show(self, rows: list[Item]) -> None:
        self.rows = rows
        self.set_list([r.text for r in rows])
        self.focus_item(0)

    def select_item(self, item: int) -> None:
        self._dialog.accept(item)

    def on_click(self, event: events.Click) -> None:
        if event.chain >= 2:
            self.select_item(self.focused)

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        index = self.top_item + y
        normal = self.get_component_rich_style("list-viewer--normal")
        if not 0 <= index < len(self.rows) or index >= self.range:
            return Strip([Segment(" " * width, normal)], width)
        row = self.rows[index]
        focused = index == self.focused
        base = self.get_component_rich_style("list-viewer--focused") if focused else normal
        lit = base + Style(color=self.get_component_rich_style(
            "palette--match-focused" if focused else "palette--match").color, bold=True)
        dim = base if focused else base + Style(color=self.get_component_rich_style("palette--dim").color)
        key = f" {row.key} " if row.key else ""
        room = max(0, width - 1 - len(key))
        text = row.text if len(row.text) <= room else "..." + row.text[-(room - 3):] if room > 3 else row.text[:room]
        shift = len(row.text) - len(text)  # cut at the left: the offsets move with it
        lit_at = {o - shift for o in row.offsets}
        segments = [Segment(" ", base)]
        for i, ch in enumerate(text):
            if i in lit_at and not (shift and i < 3):
                style = lit
            elif i + shift < row.name_from:
                style = dim
            else:
                style = base
            segments.append(Segment(ch, style))
        segments.append(Segment(" " * (room - len(text)), base))
        segments.append(Segment(key, dim))
        return Strip(Segment.simplify(segments), width)


class PaletteDialog(_Dialog):
    """Go to file, or (``>``) the commands. ``chosen`` holds the item once it ends with OK:
    a file's value is its path relative to the project, a command's (command, param)."""

    DEFAULT_CSS = """
    PaletteDialog { width: 76; height: 20; }
    PaletteDialog > .tv-window-content { margin: 1 1; }
    PaletteDialog InputLine { width: 1fr; margin: 0 1; }
    PaletteDialog .pl-body { height: 1fr; margin: 1 1 0 1; }
    PaletteDialog PaletteList { width: 1fr; height: 1fr; }
    PaletteDialog .pl-bar { width: 1; height: 1fr; background: $divide-list-bg; }
    PaletteDialog .pl-bar .scrollbar--arrow, PaletteDialog .pl-bar .scrollbar--track, PaletteDialog .pl-bar .scrollbar--thumb {
        color: $divide-list-scroll; background: $divide-list-bg;
    }
    PaletteDialog .pl-hint { height: 1; margin: 0 1; color: $text-muted; background: $surface; }
    """

    def __init__(self, files: list[str], commands: list[Item], *, recent_files: list[str] = (),
                 text: str = "") -> None:
        super().__init__(title=COMMANDS_TITLE if text.startswith(COMMANDS_PREFIX) else FILES_TITLE)
        self.files = [file_item(f) for f in files]
        self.commands = commands
        self.recent_files = [f for f in recent_files if f in set(files)]
        self.chosen: Item | None = None
        self.input = InputLine(max_len=256)
        self.input.data = text
        self.list = PaletteList(self)
        self.bar = PassiveScrollBar(classes="pl-bar")
        self.list.v_scroll_bar = self.bar
        self.hint = Static("", classes="pl-hint", markup=False)
        self.shown: list[Item] = []

    @property
    def commands_mode(self) -> bool:
        return self.input.data.startswith(COMMANDS_PREFIX)

    def compose_content(self) -> ComposeResult:
        yield self.input
        with Horizontal(classes="pl-body"):
            yield self.list
            yield self.bar
        yield self.hint

    def on_mount(self) -> None:
        self.call_after_refresh(self._start)

    def _start(self) -> None:
        line = self.input
        line._cursor_pos = len(line.data)
        line.refresh()
        self.refilter()

    # ------------------------------------------------------------ the list
    def candidates(self) -> list[Item]:
        """What the list holds before anything is typed: the recent ones first."""
        if self.commands_mode:
            recent = history.entries(RECENT_COMMANDS)
            order = {text: n for n, text in enumerate(recent)}
            return sorted(self.commands, key=lambda c: order.get(c.text, len(order)))
        recent = {f: n for n, f in enumerate(self.recent_files)}
        return sorted(self.files, key=lambda f: recent.get(f.value, len(recent)))

    def refilter(self) -> None:
        commands = self.commands_mode
        query = self.input.data[len(COMMANDS_PREFIX):] if commands else self.input.data
        self.title = COMMANDS_TITLE if commands else FILES_TITLE
        items = self.candidates()
        self.shown = rank(query, items) if query.strip() else items[:MAX_SHOWN]
        self.list.show(self.shown)
        if self.shown:
            self.hint.update(COMMANDS_HINT if commands else FILES_HINT)
        else:
            self.hint.update("No command matches" if commands else "No file matches")

    def on_input_line_changed(self, message: InputLine.Changed) -> None:
        message.stop()
        self.refilter()

    # -------------------------------------------------------------- accept
    def accept(self, index: int) -> None:
        if 0 <= index < len(self.shown):
            self.chosen = self.shown[index]
            if self.commands_mode:
                history.add(RECENT_COMMANDS, self.chosen.text)
            self.end_modal(Command.OK)

    def on_key(self, event: events.Key) -> None:
        if event.key in ("up", "down", "pageup", "pagedown") and self.input.has_focus:
            event.stop()
            event.prevent_default()
            self.list.tv_handle_key(event)  # the bar moves, the keys stay in the line
        elif event.key == "enter":
            event.stop()
            event.prevent_default()
            self.accept(self.list.focused)
        elif self.list.has_focus and event.character and event.character.isprintable() and len(event.character) == 1:
            event.stop()
            event.prevent_default()
            self.input.tv_select_self()
            self.input.focus()
            self.input.tv_handle_key(event)  # typing in the list goes on in the line


class PaletteMixin:
    """Search > Go to file and Command palette (mixed into the Divide app)."""

    async def palette(self, *, commands: bool = False) -> None:
        root = self.root.resolve()
        files = project_files(root)
        recent = []
        for window in reversed(self.editor_windows()):  # the one on top first
            path = window.path.resolve() if window.path is not None else None
            if path is not None and path.is_relative_to(root):
                recent.append(path.relative_to(root).as_posix())
        menu = self.menu_bar.menu if self.menu_bar is not None else self.init_menu_bar()
        dialog = PaletteDialog(files, menu_items(menu), recent_files=recent,
                               text=COMMANDS_PREFIX if commands else "")
        if await self.run_dialog(dialog) != Command.OK or dialog.chosen is None:
            return
        value = dialog.chosen.value
        if isinstance(value, tuple):
            command, param = value
            self.post_message(CommandMessage(command, info=param))  # as if chosen in the menu
        else:
            self.open_file(root / value)
