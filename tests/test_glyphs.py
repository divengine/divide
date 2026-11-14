"""Every character divide can draw is ASCII or in Turbo Vision's own set (CP437).

A Turbo Vision screen is a grid of cells: a character some terminal or font
draws two cells wide (or not at all) shifts its line and breaks the frames,
on one platform and not on another. CP437 is what the frames themselves need.
"""

import ast
from pathlib import Path

from divide.glyphs import CP437, screen_text

SOURCE = Path(__file__).resolve().parent.parent / "src" / "divide"


def drawn_strings(tree: ast.AST):
    """String constants, but not docstrings."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            yield node


def test_only_ascii_and_cp437_glyphs():
    found = []
    for path in sorted(SOURCE.rglob("*.py")):
        if path.name == "glyphs.py":
            continue  # the table of what is translated
        for node in drawn_strings(ast.parse(path.read_text(), str(path))):
            for ch in node.value:
                if ord(ch) > 127 and ch not in CP437:
                    found.append(f"{path.relative_to(SOURCE)}:{node.lineno} {ch!r} U+{ord(ch):04X}")
    assert not found, "\n".join(found)


def test_screen_text():
    assert screen_text("ASCII stays") == "ASCII stays"
    assert screen_text("pages “02.10 …” — ñandú, ░ ✓") == 'pages "02.10 ..." -- ñandú, ░ √'
    assert screen_text("wide 中 and 🙂") == "wide ? and ?"


def test_scrollbars_snap_to_cells():
    import divide.app  # noqa: F401  (installs the renderer)
    from textual.scrollbar import ScrollBar

    bars = ScrollBar.renderer.render_bar(size=10, virtual_size=37, window_size=10, position=3.3)
    assert all(ch in " " for seg in bars.segments for ch in seg.text)
