"""The outline of a Div template: its constructs, nested by what holds them.

The constructs come from the lexer (see ``divide.lang.div.outline``), each one
shown by its opening tag as written and coloured by the lexer's own tokens,
so a template in another dialect reads as itself.
"""

from __future__ import annotations

from divide.lang.div import outline as div_outline
from divide.outline import Node, Painter

KINDS = {
    "tplvar": "definition", "default": "definition", "property": "property",
    "include": "include", "preprocessed": "include", "loop": "loop", "iteration": "iteration",
    "conditions": "condition", "if": "condition", "if-not": "condition", "capsule": "capsule",
    "location": "location", "location-content": "location", "subparser": "subparser",
    "multirep": "multirep", "ignore": "ignore", "macro": "macro",
}


def outline(text: str, tokens: list | None = None, blocks: list | None = None, dialect=None, **_context) -> list[Node]:
    if tokens is None or blocks is None:
        from divide.lang.div.lexer import Lexer

        lexer = Lexer(dialect)
        tokens = lexer.tokenize(text)
        blocks = lexer.blocks
    paint = Painter(text, tokens)
    roots: list[Node] = []
    stack: list[tuple[int, Node]] = []  # (level, node) of the blocks the next entry may be inside
    for entry in div_outline.outline(text, blocks):
        node = Node(KINDS.get(entry.kind, entry.kind), paint.spans(entry.start, entry.end), entry.start, entry.end)
        while stack and stack[-1][0] >= entry.level:
            stack.pop()
        (stack[-1][1].children if stack else roots).append(node)
        stack.append((entry.level, node))
    return roots
