"""File marks for the project window: one ASCII character, coloured by type.

A Turbo Vision screen is a grid of cells: a character the terminal draws two
cells wide shifts the rest of its line and breaks the frames. So every mark is
plain ASCII, the same width in every terminal, font and platform, and it goes
in the blank cell files already have where folders show their ► ▼: the tree
keeps its width. Options > File type marks turns them on; the plain style
(the default) leaves that cell blank.
"""

from __future__ import annotations

from pathlib import Path

from divide import lang as languages
from divide import themes

PLAIN = "plain"
MARKS = "marks"
MODES = (PLAIN, MARKS)

FILE = ("-", "lightgray")  # a file of no known type

# by extension: (mark, colour slot) — a hint of the language where there is one
BY_EXTENSION: dict[str, tuple[str, str]] = {
    ".tpl": ("{", "lightcyan"),  # Div's braces
    ".div": ("{", "lightcyan"),
    ".dialect": ("%", "lightgreen"),  # a Div dialect
    ".php": ("?", "lightmagenta"),  # <?php
    ".phtml": ("?", "lightmagenta"),
    ".json": (":", "yellow"),  # "key": value
    ".md": ("#", "white"),  # a heading
    ".html": ("<", "lightred"),
    ".htm": ("<", "lightred"),
    ".xml": ("<", "cyan"),
    ".css": ("*", "lightblue"),
    ".js": (";", "yellow"),
    ".py": ("@", "yellow"),
    ".sh": ("$", "lightgreen"),  # the prompt
    ".txt": ("=", "lightgray"),
    ".lock": ("=", "darkgray"),
    ".png": ("^", "lightmagenta"),  # a mountain: a picture
    ".jpg": ("^", "lightmagenta"),
    ".gif": ("^", "lightmagenta"),
    ".svg": ("^", "lightmagenta"),
}
BY_NAME: dict[str, tuple[str, str]] = {
    "composer.json": ("&", "brown"),
    "composer.lock": ("&", "brown"),
    ".gitignore": ("!", "lightred"),
    "LICENSE": ("c", "lightgray"),  # (c)
}


def mark_for(path: Path, palette: themes.Palette | None = None) -> tuple[str, str]:
    """``(mark, colour)`` of a file; the colour is the slot's ``#RRGGBB`` in the palette."""
    template = languages.language_of(path) == languages.DIV.name  # .tpl, .div, the project's template extension
    mark, slot = (BY_NAME.get(path.name) or (BY_EXTENSION[".tpl"] if template else None)
                  or BY_EXTENSION.get(path.suffix.lower()) or FILE)
    return mark, (palette or themes.current()).hex(slot)
