"""The languages divide edits, by file extension.

Each language says what it is called, which files are its own, which help
topic explains its editor, and whether divide checks it (its errors go to
the Messages window). The editor and the app ask here instead of testing
extensions themselves, so a new language is one more entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Language:
    name: str  # the editor's ``lang``
    title: str  # for people: the status line, the Messages window
    extensions: frozenset[str]
    help_topic: str  # the help topic of its editor (F1)
    checked: bool = False  # its errors are listed in the Messages window


DIV = Language("div", "Div", frozenset({".tpl", ".div"}), "Editing-Templates", checked=True)
JSON = Language("json", "JSON", frozenset({".json", ".dialect"}), "Data-Files")
PHP = Language("php", "PHP", frozenset({".php", ".phtml"}), "Editing-PHP", checked=True)

LANGUAGES: tuple[Language, ...] = (DIV, JSON, PHP)


def language(name: str | None) -> Language | None:
    return next((lang for lang in LANGUAGES if lang.name == name), None)


def language_of(path: Path | None) -> str | None:
    """The language of a file: Div for templates (and untitled buffers), None for plain text."""
    if path is None:
        return DIV.name
    suffix = path.suffix.lower()
    return next((lang.name for lang in LANGUAGES if suffix in lang.extensions), None)
