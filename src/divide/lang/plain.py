"""Colours for two simple formats with no tree-sitter grammar at hand: INI and CSV.

- INI (``php.ini``, ``.ini``, ``.editorconfig``): ``[sections]``, ``key = value``,
  comments (``;`` or ``#``), quoted strings and numbers in the values.
- CSV / TSV: each column in a colour of its own, in turn (as "rainbow CSV"
  tools do), so a column can be followed down the file; quoted fields may hold
  the separator and new lines. The separator is guessed from the first line
  (``,`` ``;`` tab ``|``); ``.tsv`` is tabs.

The tokens are ``(start, end, kind)`` offsets into the text, as divide's other
lexers give them; the kinds (``ini.*``, ``csv.*``) are coloured by role in
divide.themes.TOKENS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CSV_COLOURS = 6  # csv.col0 ... csv.col5, then again
SEPARATORS = ",;\t|"


@dataclass(frozen=True)
class Token:
    start: int
    end: int
    kind: str


_INI_LINE = re.compile(r"[^\n]*")
_INI_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?[KMG]?\b")
_INI_CONSTANT = re.compile(r"(?i)\b(?:on|off|true|false|yes|no|none|null)\b")


def ini_tokens(text: str) -> list[Token]:
    tokens: list[Token] = []
    for m in _INI_LINE.finditer(text):
        line, base = m.group(), m.start()
        body = line.lstrip()
        at = base + len(line) - len(body)
        if not body:
            continue
        if body[0] in ";#":
            tokens.append(Token(at, base + len(line), "ini.comment"))
        elif body[0] == "[":
            close = body.find("]")
            tokens.append(Token(at, at + (close + 1 if close >= 0 else len(body)), "ini.section"))
        elif "=" in body or ":" in body:
            eq = min(i for i in (body.find("="), body.find(":")) if i >= 0)
            tokens.append(Token(at, at + len(body[:eq].rstrip()), "ini.key"))
            tokens.append(Token(at + eq, at + eq + 1, "ini.operator"))
            tokens.extend(_ini_value(body[eq + 1:], at + eq + 1))
    return tokens


def _ini_value(value: str, base: int) -> list[Token]:
    out: list[Token] = []
    comment = re.search(r"\s[;#]", value)
    text = value[:comment.start()] if comment else value
    for q in re.finditer(r"\"[^\"]*\"?|'[^']*'?", text):
        out.append(Token(base + q.start(), base + q.end(), "ini.string"))
    quoted = [(t.start - base, t.end - base) for t in out]
    for pattern, kind in ((_INI_NUMBER, "ini.number"), (_INI_CONSTANT, "ini.constant")):
        for m in pattern.finditer(text):
            if not any(a <= m.start() < b for a, b in quoted):
                out.append(Token(base + m.start(), base + m.end(), kind))
    if comment:
        out.append(Token(base + comment.start() + 1, base + len(value), "ini.comment"))
    return out


def csv_separator(text: str, tsv: bool = False) -> str:
    if tsv:
        return "\t"
    first = text.split("\n", 1)[0]
    counts = {sep: first.count(sep) for sep in SEPARATORS}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def csv_tokens(text: str, separator: str | None = None) -> list[Token]:
    sep = separator or csv_separator(text)
    tokens: list[Token] = []
    col, start, i, n = 0, 0, 0, len(text)
    quoted = False
    while i <= n:
        ch = text[i] if i < n else "\n"
        if quoted:
            if ch == '"' and i + 1 < n and text[i + 1] == '"':
                i += 2
                continue
            if ch == '"':
                quoted = False
            elif i == n:
                quoted = False
                continue
            i += 1
            continue
        if ch == '"' and i == start:
            quoted = True
            i += 1
            continue
        if ch == sep or ch == "\n" or i == n:
            if i > start:
                tokens.append(Token(start, i, f"csv.col{col % CSV_COLOURS}"))
            if ch == sep:
                tokens.append(Token(i, i + 1, "csv.sep"))
                col += 1
            else:
                col = 0
            start = i + 1
        i += 1
    return tokens
