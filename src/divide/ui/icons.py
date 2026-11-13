"""File icons for the project window: Nerd Font glyphs, when the user wants them.

Nerd Fonts are fonts patched with icons in Unicode's private use area. Without
such a font in the terminal the glyphs are boxes, so icons are an option
(Options > Nerd Font icons), off by default; the plain style keeps only the
Turbo Vision ▸ ▾ of the folders.
"""

from __future__ import annotations

from pathlib import Path

from divide.editor.theme import CGA

PLAIN = "plain"
NERD = "nerd"
MODES = (PLAIN, NERD)

FOLDER = ""  # nf-fa-folder
FOLDER_OPEN = ""  # nf-fa-folder_open
FILE = ""  # nf-fa-file

# by extension: (glyph, colour)
BY_EXTENSION: dict[str, tuple[str, str]] = {
    ".tpl": ("", "lightcyan"),  # nf-fa-code: a Div template
    ".div": ("", "lightcyan"),
    ".dialect": ("", "lightmagenta"),  # nf-fa-paint_brush: a Div dialect
    ".php": ("", "lightmagenta"),  # nf-dev-php
    ".phtml": ("", "lightmagenta"),
    ".json": ("", "yellow"),  # nf-seti-json
    ".md": ("", "white"),  # nf-dev-markdown
    ".html": ("", "lightred"),  # nf-dev-html5
    ".htm": ("", "lightred"),
    ".css": ("", "lightblue"),  # nf-dev-css3
    ".js": ("", "yellow"),  # nf-dev-javascript
    ".py": ("", "yellow"),  # nf-dev-python
    ".sh": ("", "lightgreen"),  # nf-oct-terminal
    ".xml": ("", "cyan"),  # nf-fa-file_code_o
    ".txt": ("", "lightgray"),  # nf-fa-file_text
    ".lock": ("", "lightgray"),  # nf-fa-lock
    ".png": ("", "lightmagenta"),  # nf-fa-file_image_o
    ".jpg": ("", "lightmagenta"),
    ".gif": ("", "lightmagenta"),
    ".svg": ("", "lightmagenta"),
}
BY_NAME: dict[str, tuple[str, str]] = {
    "composer.json": ("", "brown"),  # nf-dev-composer
    "composer.lock": ("", "brown"),
    ".gitignore": ("", "lightred"),  # nf-dev-git
    "LICENSE": ("", "lightgray"),  # nf-fa-legal
}


def icon_for(path: Path, *, folder: bool = False, expanded: bool = False) -> tuple[str, str | None]:
    """``(glyph, colour)`` of a project entry; the colour is a CGA name or None."""
    if folder:
        return (FOLDER_OPEN if expanded else FOLDER), None
    found = BY_NAME.get(path.name) or BY_EXTENSION.get(path.suffix.lower())
    if found is None:
        return FILE, None
    glyph, colour = found
    return glyph, CGA[colour]
