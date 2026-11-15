"""The outline of a Div template: its constructs, nested as they are written.

Div has no declarations: a template is rewritten by the engine until nothing
changes, so its "outline" is the structure the editor can see. The lexer
(``Lexer.blocks``) records every construct it recognises with Div's own
matching rules (balanced keyed blocks, the longest key that closes); here
they are nested by what contains what, and each one is shown by its opening
tag as it is written, so any dialect reads as itself:

- definitions and properties: ``{= title: "Shop" =}``, ``{@ ... @}``, ``@_DIALECT = erb.dialect``;
- includes: ``{% layout/header %}``, ``{%% components/card %%}``;
- blocks, with what they hold below them: lists ``[$products] product =>``,
  iterations ``[:1,10:]``, conditions ``{?( ... )?}``, conditional parts
  ``?$logged`` / ``!$logged``, capsules ``[[product``, locations and their
  content ``(( content ))`` / ``{{content``, sub-parsers, multiple
  replacements, ignored parts and macros.

Replacements (``{$name}``) and formulas are left out: they are the template's
text, not its shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .lexer import Block

# Blocks with a body: shown by their opening tag, their content below them.
BODIES = {"loop", "iteration", "conditions", "capsule", "location-content", "if", "if-not",
          "subparser", "multirep", "ignore"}
# Opening tags paired here with a closing tag of their own kind, in nesting order.
PAIRS = {"conditions-end": "conditions", "iteration-end": "iteration"}
MAX_LABEL = 60


@dataclass(frozen=True)
class Entry:
    kind: str
    label: str
    level: int
    start: int  # the opening tag, as offsets into the text: what Enter selects
    end: int
    body_end: int  # after the closing tag (the tag's end without a body)

    @property
    def text(self) -> str:
        return "  " * self.level + self.label


def label(text: str, start: int, end: int) -> str:
    """The tag on one line, cut when it is long."""
    shown = re.sub(r"\s+", " ", text[start:end]).strip()
    return shown if len(shown) <= MAX_LABEL else shown[: MAX_LABEL - 3] + "..."


def outline(text: str, blocks: list[Block]) -> list[Entry]:
    """``blocks`` (from the lexer, for ``text``) as nested outline entries, in order."""
    found: list[list] = []  # [kind, start, head, end]
    open_at: dict[str, list[int]] = {kind: [] for kind in PAIRS.values()}
    for b in sorted(blocks, key=lambda b: (b.start, -b.end)):
        if b.kind in PAIRS:
            stack = open_at[PAIRS[b.kind]]
            if stack:
                found[stack.pop()][3] = b.end
            continue
        if b.kind in open_at:
            open_at[b.kind].append(len(found))
        found.append([b.kind, b.start, b.head, b.end])
    entries: list[Entry] = []
    ends: list[int] = []  # the ends of the blocks the current one is inside
    for kind, start, head, end in sorted(found, key=lambda f: (f[1], -f[3])):
        while ends and ends[-1] <= start:
            ends.pop()
        shown = label(text, start, head if kind in BODIES else end)
        entries.append(Entry(kind, shown, len(ends), start, head, end))
        ends.append(end)  # what starts before it ends is inside it (a list inside a {= =} too)
    return entries
