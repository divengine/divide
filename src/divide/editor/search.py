"""Find / replace over plain text (UI-independent).

Offsets are code-point indexes into the text. Options follow the Turbo Pascal
Find and Replace dialogs: case sensitive, whole words only, regular
expression, direction and origin.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SearchOptions:
    case_sensitive: bool = False
    whole_words: bool = False
    regex: bool = False
    backward: bool = False
    entire_scope: bool = False  # origin: False = from cursor
    prompt: bool = True  # replace: ask on every occurrence


class SearchError(ValueError):
    """The search text is not a valid pattern."""


def compile_pattern(query: str, opts: SearchOptions) -> re.Pattern[str]:
    if not query:
        raise SearchError("Empty search text")
    body = query if opts.regex else re.escape(query)
    if opts.whole_words:
        body = rf"(?<!\w)(?:{body})(?!\w)"
    flags = re.MULTILINE | (0 if opts.case_sensitive else re.IGNORECASE)
    try:
        return re.compile(body, flags)
    except re.error as exc:
        raise SearchError(f"Bad regular expression: {exc}") from exc


def find(text: str, pattern: re.Pattern[str], pos: int, *, backward: bool = False) -> re.Match[str] | None:
    """First match at/after ``pos``, or the last one ending at/before ``pos`` when backward.

    Empty matches are skipped so that repeated searches always move.
    """
    if backward:
        last = None
        for m in pattern.finditer(text, 0, pos):
            if m.end() > m.start():
                last = m
        return last
    while pos <= len(text):
        m = pattern.search(text, pos)
        if m is None:
            return None
        if m.end() > m.start():
            return m
        pos = m.start() + 1
    return None


def expand(match: re.Match[str], replacement: str, opts: SearchOptions) -> str:
    """Replacement text for one match (``\\1`` / ``\\g<name>`` when regex)."""
    if not opts.regex:
        return replacement
    try:
        return match.expand(replacement)
    except (re.error, IndexError) as exc:
        raise SearchError(f"Bad replacement: {exc}") from exc


def replace_all(text: str, pattern: re.Pattern[str], replacement: str, opts: SearchOptions, start: int = 0) -> tuple[str, int]:
    """Replace every non-empty match from ``start`` on. Returns (new text, count)."""
    out: list[str] = [text[:start]]
    pos = last = start
    count = 0
    while (m := find(text, pattern, pos)) is not None:
        out.append(text[last : m.start()])
        out.append(expand(m, replacement, opts))
        last = pos = m.end()
        count += 1
    out.append(text[last:])
    return "".join(out), count
