"""PHP: colours from tree-sitter's PHP grammar, errors from PHP itself.

The grammar (``tree-sitter-php``, with its own highlight query) only colours
the code. Whether the code is right is PHP's answer: ``php -l`` parses the
buffer and reports the first error, as it would when the file runs.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from functools import lru_cache

from divide.lang.div.diagnostics import Diagnostic

PREFIX = "php."  # highlight names: php.keyword, php.string… (the theme styles them)


@lru_cache(maxsize=1)
def grammar() -> tuple[object, str] | None:
    """``(tree-sitter Language, highlight query)``; None without tree-sitter-php."""
    try:
        import tree_sitter_php
        from tree_sitter import Language
    except ImportError:
        return None
    query = tree_sitter_php.HIGHLIGHTS_QUERY
    # the grammar's capture names, in our own namespace (predicates name them too)
    query = re.sub(r"@([a-z][a-z.]*)", lambda m: "@" + PREFIX + m.group(1), query)
    return Language(tree_sitter_php.language_php()), query


_ERROR = re.compile(r"^(?:PHP )?(Parse error|Fatal error|Warning|Deprecated|Notice):\s*(.*?) in Standard input code on line (\d+)", re.M)


def parse_lint(output: str, text: str) -> list[Diagnostic]:
    """The errors of ``php -l`` as diagnostics over their whole line."""
    lines = text.split("\n")
    starts = [0]
    for line in lines[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    found: list[Diagnostic] = []
    for kind, message, number in _ERROR.findall(output):
        row = min(max(int(number) - 1, 0), len(lines) - 1)
        start = starts[row]
        line = lines[row]
        indent = len(line) - len(line.lstrip())
        end = start + len(line)
        severity = "error" if kind.endswith("error") else "warning"
        # "Error: syntax error…" in the Messages window; warnings keep PHP's word for them
        text_ = message if severity == "error" else f"{kind}: {message}"
        found.append(Diagnostic(start + indent if indent < len(line) else start, max(end, start + 1), severity, text_))
    return found


async def lint(text: str, php: str | None = None, timeout: float = 10.0) -> list[Diagnostic] | None:
    """PHP's verdict on ``text`` (None: no php to ask)."""
    php = php or shutil.which("php")
    if not php:
        return None
    proc = await asyncio.create_subprocess_exec(
        php, "-d", "display_errors=stderr", "-d", "log_errors=0", "-l",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(text.encode("utf-8")), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return None
    if proc.returncode == 0:
        return []
    return parse_lint(err.decode("utf-8", "replace") + out.decode("utf-8", "replace"), text)


def in_parentheses(text: str, offset: int, window: int = 4000) -> bool:
    """Is ``offset`` inside a parenthesis still open (a call's arguments)? Strings
    and comments are skipped. Language servers may answer a signature for the
    call next to the cursor even after it is closed: this tells them apart."""
    start = max(0, offset - window)
    if start:
        start = text.find("\n", start) + 1 or start
    depth = 0
    i = start
    while i < offset:
        ch = text[i]
        if ch in "'\"":
            i += 1
            while i < offset and text[i] != ch:
                i += 2 if text[i] == "\\" else 1
        elif ch == "#" or (ch == "/" and text.startswith("//", i)):
            end = text.find("\n", i)
            i = offset if end < 0 or end >= offset else end
            continue
        elif ch == "/" and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = offset if end < 0 or end >= offset else end + 2
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        i += 1
    return depth > 0
