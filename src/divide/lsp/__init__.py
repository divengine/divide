"""Language servers: completion, hover, definitions and diagnostics from tools
written for each language (phpactor, intelephense…), through the Language
Server Protocol.

divide is the client (``divide.lsp.client``, on pygls); this module knows the
servers (``SERVERS``), finds their commands and converts between the
protocol's positions and the editor's text offsets.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

AUTO = "auto"
OFF = "off"


@dataclass(frozen=True)
class ServerSpec:
    name: str
    language: str  # divide.lang name
    command: tuple[str, ...]  # program and arguments; the program is looked for
    project_bins: tuple[str, ...] = ()  # where a project may carry it
    url: str = ""
    init_options: dict = field(default_factory=dict)


SERVERS: tuple[ServerSpec, ...] = (
    ServerSpec(
        "phpactor", "php", ("phpactor", "language-server"),
        project_bins=("vendor/bin/phpactor",),
        url="https://phpactor.readthedocs.io",
    ),
    ServerSpec(
        "intelephense", "php", ("intelephense", "--stdio"),
        project_bins=("node_modules/.bin/intelephense",),
        url="https://intelephense.com",
    ),
)


def servers_for(language: str) -> list[ServerSpec]:
    return [s for s in SERVERS if s.language == language]


def spec(name: str) -> ServerSpec | None:
    return next((s for s in SERVERS if s.name == name), None)


def find_command(server: ServerSpec, root: Path, override: list[str] | None = None) -> list[str] | None:
    """The command line of ``server``: the user's, else the project's copy, else the PATH's.

    A ``.phar`` given as the program runs with php."""
    if override:
        program, rest = override[0], list(override[1:]) or list(server.command[1:])
        if program.endswith(".phar"):
            php = shutil.which("php")
            return [php, program, *rest] if php and Path(program).is_file() else None
        found = program if Path(program).is_file() else shutil.which(program)
        return [found, *rest] if found else None
    for rel in server.project_bins:
        candidate = root / rel
        if candidate.is_file():
            return [str(candidate), *server.command[1:]]
    found = shutil.which(server.command[0])
    return [found, *server.command[1:]] if found else None


# ------------------------------------------------------------------ positions
# The protocol counts columns in UTF-16 code units; the editor in characters.
def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def line_starts(text: str) -> list[int]:
    starts = [0]
    for m in re.finditer("\n", text):
        starts.append(m.end())
    return starts


def to_position(text: str, offset: int, starts: list[int] | None = None) -> tuple[int, int]:
    """Text offset -> (line, UTF-16 column)."""
    starts = starts or line_starts(text)
    offset = max(0, min(offset, len(text)))
    line = max(0, _bisect(starts, offset))
    return line, _utf16_len(text[starts[line]:offset])


def to_offset(text: str, line: int, character: int, starts: list[int] | None = None) -> int:
    """(line, UTF-16 column) -> text offset (clamped to the line)."""
    starts = starts or line_starts(text)
    if line >= len(starts):
        return len(text)
    begin = starts[line]
    end = starts[line + 1] - 1 if line + 1 < len(starts) else len(text)
    units = 0
    for i, ch in enumerate(text[begin:end]):
        if units >= character:
            return begin + i
        units += 2 if ord(ch) > 0xFFFF else 1
    return end


def _bisect(starts: list[int], offset: int) -> int:
    lo, hi = 0, len(starts)
    while lo < hi:
        mid = (lo + hi) // 2
        if starts[mid] <= offset:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1


# ------------------------------------------------------------------ snippets
_SNIPPET = re.compile(r"\\([$}\\])|\$\{(\d+)(?::((?:[^{}\\]|\\.)*))?\}|\$\{(\d+)\|([^|]*)\|\}|\$(\d+)")


def from_snippet(text: str, caret: str) -> str:
    """A snippet as plain text: placeholders keep their default text, the first
    tab stop (or $0) becomes ``caret``."""
    placed = False

    def repl(m: re.Match) -> str:
        nonlocal placed
        if m.group(1):
            return m.group(1)
        if m.group(2) is not None:  # ${1:default}
            default = from_snippet(m.group(3) or "", caret="") if m.group(3) else ""
            if not default and not placed:
                placed = True
                return caret
            return default
        if m.group(4) is not None:  # ${1|a,b|}
            return m.group(5).split(",")[0]
        if not placed:  # $1, $0
            placed = True
            return caret
        return ""

    return _SNIPPET.sub(repl, text)


def plain_markup(value) -> str:
    """Hover contents (MarkupContent, MarkedString or a list) as text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "\n\n".join(plain_markup(v) for v in value if v)
    text = getattr(value, "value", None)
    return text if isinstance(text, str) else str(value)
