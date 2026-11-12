"""Print a Div template with syntax highlighting: ``python -m divide.lang.div.preview file.tpl``."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text

from divide.editor.theme import DIV_STYLES

from .dialect import resolve_dialect
from .lexer import tokenize


def render(text: str, path: Path | None = None, show_kinds: bool = False) -> Text:
    dialect = resolve_dialect(text, path)
    out = Text(text)
    for tok in tokenize(text, dialect):
        style = DIV_STYLES.get(tok.kind)
        if style:
            out.stylize(style, tok.start, tok.end)
    return out


def main(argv: list[str]) -> int:
    console = Console()
    kinds = "--kinds" in argv
    for arg in [a for a in argv if not a.startswith("--")]:
        p = Path(arg)
        text = p.read_text(encoding="utf-8")
        console.rule(str(p))
        if kinds:
            for t in tokenize(text, resolve_dialect(text, p)):
                console.print(f"{t.start:5}-{t.end:<5} {t.kind:18} {text[t.start:t.end]!r}", highlight=False, markup=False)
        else:
            console.print(render(text, p), highlight=False, markup=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
