"""What divide draws: ASCII and Turbo Vision's own characters (CP437).

A Turbo Vision screen is a grid of cells. A character some terminal or font
draws two cells wide, or not at all, shifts its line and breaks the frames, on
one platform and not on another. divide's own strings keep to ASCII and CP437
(tests/test_glyphs.py checks it); text that comes from elsewhere (the help
books) goes through ``screen_text``.
"""

from __future__ import annotations

from rich.cells import cell_len

# CP437's glyphs: the control range as DOS drew it, then 0x80-0xFF
CP437 = frozenset("☺☻♥♦♣♠•◘○◙♂♀♪♫☼►◄↕‼¶§▬↨↑↓→←∟↔▲▼⌂") | frozenset(bytes(range(128, 256)).decode("cp437"))

# typography outside CP437, as ASCII
_ASCII = str.maketrans({
    "…": "...", "—": "--", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
    "›": ">", "‹": "<", "≠": "!=", "✓": "√", "✔": "√", "✗": "x", "▶": "►", "◀": "◄",
    "​": "", "️": "",  # zero width space, emoji presentation
})


def screen_text(text: str) -> str:
    """``text`` safe for the grid: typography as ASCII, wide characters as ``?``."""
    text = text.translate(_ASCII)
    if text.isascii():
        return text
    return "".join(ch if ch in CP437 or ch.isascii() or cell_len(ch) == 1 else "?" for ch in text)
