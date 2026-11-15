"""Colour themes: every colour divide draws, in one place.

A theme (``Palette``) has four parts:

- ``ansi``: its 16 colours, by the names of the BIOS text-mode slots (black,
  blue, ... yellow, white). File marks and the Borland themes speak in slots.
- ``chrome``: the Textual theme of textual-vision's widgets (menus, dialogs,
  buttons, frames, status line). The Borland themes are textual-vision's own.
- ``ui``: divide's roles (desktop, editor, output, debug and help windows,
  progress bar, shadow...). Each is a slot name or a ``#RRGGBB``; the CSS sees
  them as ``$divide-<role>`` and the code asks ``palette.colour(role)``.
- ``syntax``: the colours of the syntax roles (keyword, variable, string...).
  ``TOKENS`` says which role, and which attributes, each token kind takes,
  the same in every theme: a theme only chooses colours.

Colours are written in full RGB; Textual (through Rich) sends them as the
terminal can show them: true colour, the 256-colour cube (the same in every
terminal) or the 16 ANSI colours, by what the terminal says it supports
(``COLORTERM``, ``TERM``, the Windows console), never by the operating system.
``--colors`` (or Options > Colors) overrides the detection.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Mapping

from rich.style import Style
from textual.theme import Theme
from textual_vision.themes import THEME_TURBO_C, THEME_TURBO_PASCAL

SLOTS = (
    "black", "blue", "green", "cyan", "red", "magenta", "brown", "lightgray",
    "darkgray", "lightblue", "lightgreen", "lightcyan", "lightred", "lightmagenta", "yellow", "white",
)  # in BIOS order: slot i is attribute colour i

# The 16 CGA/VGA text-mode colours, as Turbo Pascal and Turbo C showed them.
CGA = dict(zip(SLOTS, (
    "#000000", "#0000AA", "#00AA00", "#00AAAA", "#AA0000", "#AA00AA", "#AA5500", "#AAAAAA",
    "#555555", "#5555FF", "#55FF55", "#55FFFF", "#FF5555", "#FF55FF", "#FFFF55", "#FFFFFF",
)))

# Windows Terminal's Campbell scheme: the console colours Free Pascal's IDE gets
# on today's Windows.
CAMPBELL = dict(zip(SLOTS, (
    "#0C0C0C", "#0037DA", "#13A10E", "#3A96DD", "#C50F1F", "#881798", "#C19C00", "#CCCCCC",
    "#767676", "#3B78FF", "#16C60C", "#61D6D6", "#E74856", "#B4009E", "#F9F1A5", "#F2F2F2",
)))

# modern-dark's own 16, for the file marks and anything that asks for a slot.
MODERN = dict(zip(SLOTS, (
    "#16181D", "#4D8FE0", "#7EB866", "#3FA7B5", "#D4515D", "#B072D1", "#C98A4B", "#B6BCC8",
    "#5F6673", "#7DB4F5", "#A8DC8C", "#7FD8E3", "#FF7A85", "#D9A2F2", "#E8C77D", "#F3F5F8",
)))

# --------------------------------------------------------------------------
# Syntax: token kind -> (foreground role, background role, attributes).
# The token kinds are the lexers' (divide.lang.*) and tree-sitter's (php.*).
TOKENS: dict[str, tuple[str | None, str | None, dict[str, bool]]] = {}


def _tok(fg: str | None, *kinds: str, bg: str | None = None, **attrs: bool) -> None:
    for kind in kinds:
        TOKENS[kind] = (fg, bg, attrs)


B = {"bold": True}
_tok("keyword", "div.var.def", "div.loop", "div.cond", "div.keyword", "div.capsule", "div.location",
     "div.include", "div.tplvar", "json.key", "php.keyword", "php.constructor", **B)
_tok("name", "div.property", "div.function", "php.function", "php.function.builtin", "php.function.method")
_tok("variable", "div.replace", "div.var", "div.key", "div.property.value", "php.variable", "php.property")
_tok("variable", "json.ref", "php.variable.builtin", **B)
_tok("builtin", "div.var.builtin")
_tok("string", "div.string", "html.string", "json.string", "php.string")
_tok("string", "div.path", underline=True)
_tok("type", "php.type", "php.type.builtin")
_tok("number", "div.number", "json.number", "php.number")
_tok("constant", "div.constant", "json.constant", "php.constant", "html.entity")
_tok("constant", "php.constant.builtin", **B)
_tok("modifier", "div.modifier", "div.format")
_tok("comment", "div.comment", "div.ignored", "div.friendly", "html.comment", "json.comment", "php.comment")
_tok("comment", "div.doc", **B)
_tok("operator", "div.operator", "php.operator")
_tok("punct", "div.punct", "json.punct")
_tok("special", "div.special")
_tok("special", "div.subparser", "div.multirep", "div.macro", "php.tag", **B)
_tok("markup", "html.tag", "html.attr")
_tok("module", "php.module", "php.module.builtin")
_tok("error", "div.error", "json.error", bg="error-bg", **B)
_tok("error", "diag.error", bg="error-bg")  # diagnostics, over the syntax colours
_tok(None, "diag.warning", bg="warning-bg")
_tok("focus", "dialector.focus", bg="focus-bg", **B)
_tok("inserted", "trace.new", bg="inserted-bg", **B)  # what a mutation wrote
_tok("deleted", "trace.old", bg="deleted-bg", **B)  # what it took away
del B

SYNTAX_ROLES = (
    "keyword", "name", "variable", "builtin", "string", "type", "number", "constant", "modifier",
    "comment", "operator", "punct", "special", "markup", "module",
    "error", "error-bg", "warning-bg", "focus", "focus-bg", "inserted", "inserted-bg", "deleted", "deleted-bg",
)

# The roles of the UI; every theme gives every one (tests/test_themes.py checks).
UI_ROLES = (
    "desktop", "desktop-pattern", "shadow", "shadow-text",
    "editor-bg", "editor-text", "editor-gutter", "editor-cursor", "editor-cursor-bg", "editor-cursor-line",
    "editor-bracket", "editor-bracket-bg", "editor-selection", "editor-selection-bg",
    "breakpoint", "breakpoint-bg", "execution", "execution-bg",
    "output-bg", "output-text", "output-gutter", "output-cursor", "output-cursor-bg",
    "output-selection", "output-selection-bg", "output-frame", "output-frame-passive",
    "debug-bg", "debug-text", "debug-frame", "debug-frame-passive", "debug-title", "debug-selected", "debug-selected-bg",
    "help-bg", "help-text", "help-bold", "help-code", "help-link", "help-url", "help-rule",
    "help-selected", "help-selected-bg", "help-frame", "help-frame-passive",
    "progress-fill", "progress-track", "progress-text", "verdict-error",
    "list-bg", "list-text", "list-selected", "list-focused", "list-focused-bg", "list-scroll",
    "info-bg", "info-text",
    "history-bg", "history-text", "history-frame", "history-focused", "history-focused-bg",
)

# --------------------------------------------------------------------------
# Turbo Pascal's roles, in slots: the colours divide has always had.
BORLAND_UI = {
    "desktop": "lightgray", "desktop-pattern": "blue",  # TBackground 0x71: the ░ blue on gray
    "shadow": "black", "shadow-text": "darkgray",
    "editor-bg": "blue", "editor-text": "yellow", "editor-gutter": "cyan",
    "editor-cursor": "blue", "editor-cursor-bg": "yellow", "editor-cursor-line": "yellow",
    "editor-bracket": "white", "editor-bracket-bg": "cyan",
    "editor-selection": "blue", "editor-selection-bg": "lightgray",
    "breakpoint": "white", "breakpoint-bg": "red",  # Turbo Pascal's bars
    "execution": "black", "execution-bg": "cyan",
    "output-bg": "black", "output-text": "white", "output-gutter": "darkgray",  # the Output window
    "output-cursor": "black", "output-cursor-bg": "lightgray",
    "output-selection": "black", "output-selection-bg": "lightgray",
    "output-frame": "white", "output-frame-passive": "lightgray",
    "debug-bg": "cyan", "debug-text": "black", "debug-frame": "white", "debug-frame-passive": "black",
    "debug-title": "black", "debug-selected": "white", "debug-selected-bg": "red",  # Watches, Call stack
    "help-bg": "cyan", "help-text": "black", "help-bold": "white", "help-code": "blue",
    "help-link": "yellow", "help-url": "black", "help-rule": "lightgray",
    "help-selected": "yellow", "help-selected-bg": "blue", "help-frame": "white", "help-frame-passive": "lightgray",
    "progress-fill": "blue", "progress-track": "darkgray", "progress-text": "black",  # on the gray dialog
    "verdict-error": "lightred",
    # a dialog's lists (the files of File > Open, the histories): Turbo Pascal's own
    "list-bg": "cyan", "list-text": "black", "list-selected": "yellow",  # the chosen one, the list elsewhere
    "list-focused": "white", "list-focused-bg": "green", "list-scroll": "blue",  # the chosen one, in the list
    "info-bg": "blue", "info-text": "cyan",  # File > Open's pane: the folder, the file under the bar
    "history-bg": "blue", "history-text": "white", "history-frame": "white",  # an input line's earlier entries
    "history-focused": "black", "history-focused-bg": "cyan",
}

# Div's structure in the reserved-word white, variables in light cyan, the HTML
# around it in the quieter cyan.
BORLAND_SYNTAX = {
    "keyword": "white", "name": "white", "variable": "lightcyan", "builtin": "lightgreen",
    "string": "lightgreen", "type": "lightgreen", "number": "lightmagenta", "constant": "lightmagenta",
    "modifier": "lightmagenta", "comment": "lightgray", "operator": "yellow", "punct": "yellow",
    "special": "lightred", "markup": "cyan", "module": "cyan",
    "error": "white", "error-bg": "red", "warning-bg": "brown", "focus": "black", "focus-bg": "lightcyan",
    "inserted": "black", "inserted-bg": "lightgreen", "deleted": "white", "deleted-bg": "red",
}

# Campbell's blue is lighter than CGA's: its cyan, light red and light magenta
# no longer read on it, so those roles take the Campbell colours that do.
FREE_PASCAL_SYNTAX = {
    **BORLAND_SYNTAX,
    "number": "brown", "constant": "brown", "modifier": "brown",
    "special": "lightcyan", "markup": "lightgray", "module": "lightgray",
}

FREE_PASCAL_UI = {**BORLAND_UI, "editor-gutter": "lightgray", "info-text": "lightcyan"}  # Campbell's cyan is faint on its blue

# --------------------------------------------------------------------------
# modern-dark: deep gray surfaces, light text, one blue accent.
_BG, _PANEL, _SURFACE, _RAISED = "#1A1D23", "#22262E", "#2B3039", "#3A404B"
_TEXT, _MUTED, _BRIGHT, _ACCENT = "#D8DCE3", "#8F97A5", "#F3F5F8", "#3D7BC4"

MODERN_CHROME = dataclasses.replace(
    THEME_TURBO_PASCAL,
    name="modern-dark",
    primary="#7DB4F5", secondary=_RAISED, accent=_ACCENT, foreground=_BRIGHT, background=_BG,
    surface=_SURFACE, panel=_PANEL, warning="#E8C77D", error="#FF7A85", success="#A8DC8C",
    variables={
        "text": _TEXT, "text-muted": _MUTED,
        "window-content-background": _BG,
        "block-cursor-foreground": _BG, "block-cursor-background": "#7DB4F5", "block-cursor-text-style": "bold",
        "input-cursor-foreground": _BG, "input-cursor-background": _TEXT, "input-cursor-text-style": "none",
        "scrollbar": _MUTED, "scrollbar-active": "#7DB4F5", "scrollbar-background": _PANEL,
        "scrollbar-background-hover": _PANEL, "scrollbar-background-active": _PANEL,
        "scrollbar-corner-color": _PANEL, "scrollbar-color-hover": "#7DB4F5",
        "input-fg": _BRIGHT, "input-bg": "#11141A", "input-selected-fg": _BRIGHT, "input-selected-bg": _ACCENT,
        "input-arrow": "#A8DC8C",
        "button-face-fg": _BRIGHT, "button-face-bg": "#355E8F", "button-default-fg": "#9FD0FF",
        "button-focused-fg": _BRIGHT, "button-focused-bg": "#4D8FE0",
        "button-disabled-fg": _MUTED, "button-disabled-bg": _RAISED, "button-hotkey": "#E8C77D",
        "button-shadow-fg": "#0E1014", "button-shadow-bg": _SURFACE,
        "label-highlight": _BRIGHT, "label-hotkey": "#E8C77D",
        "frame-icon": "#A8DC8C",
        "combo-arrow-fg": _BRIGHT, "combo-arrow-bg": "#355E8F", "combo-sides-fg": "#355E8F", "combo-sides-bg": _SURFACE,
        "cluster-fg": _TEXT, "cluster-bg": _RAISED, "cluster-focused-fg": _BRIGHT, "cluster-focused-bg": _RAISED,
        "cluster-hotkey": "#E8C77D", "cluster-disabled-fg": _MUTED, "cluster-disabled-bg": _RAISED,
        "link-color": "#7DB4F5", "link-background": "transparent", "link-color-hover": _BRIGHT,
        "link-background-hover": _ACCENT,
        "footer-foreground": _TEXT, "footer-background": _SURFACE, "footer-key-foreground": "#E8C77D",
        "footer-key-background": _SURFACE, "footer-description-foreground": _TEXT,
        "footer-description-background": _SURFACE,
        "menu-hotkey": "#E8C77D", "menu-hotkey-background": _SURFACE,
        "desktop-pattern-color": _PANEL,
    },
)

MODERN_UI = {
    "desktop": "#121419", "desktop-pattern": "#252932",
    "shadow": "#07080A", "shadow-text": "#4A505C",
    "editor-bg": _BG, "editor-text": _TEXT, "editor-gutter": "#5F6673",
    "editor-cursor": _BG, "editor-cursor-bg": "#7DB4F5", "editor-cursor-line": "#E8C77D",
    "editor-bracket": _BRIGHT, "editor-bracket-bg": "#3F4A5C",
    "editor-selection": _BRIGHT, "editor-selection-bg": "#2F4B70",
    "breakpoint": _BRIGHT, "breakpoint-bg": "#8E2B36", "execution": "#101216", "execution-bg": "#5FB8C4",
    "output-bg": "#101216", "output-text": _TEXT, "output-gutter": "#5F6673",
    "output-cursor": "#101216", "output-cursor-bg": _TEXT,
    "output-selection": _BRIGHT, "output-selection-bg": "#2F4B70",
    "output-frame": _TEXT, "output-frame-passive": "#5F6673",
    "debug-bg": _PANEL, "debug-text": _TEXT, "debug-frame": "#5FB8C4", "debug-frame-passive": "#5F6673",
    "debug-title": _TEXT, "debug-selected": "#101216", "debug-selected-bg": "#E8C77D",
    "help-bg": _PANEL, "help-text": _TEXT, "help-bold": _BRIGHT, "help-code": "#E8C77D",
    "help-link": "#7DB4F5", "help-url": "#B6BCC8", "help-rule": "#5F6673",
    "help-selected": "#101216", "help-selected-bg": "#7DB4F5", "help-frame": "#7DB4F5", "help-frame-passive": "#5F6673",
    "progress-fill": "#4D8FE0", "progress-track": _RAISED, "progress-text": _TEXT,
    "verdict-error": "#FF7A85",
    "list-bg": "#11141A", "list-text": _TEXT, "list-selected": "#E8C77D",
    "list-focused": _BRIGHT, "list-focused-bg": "#2F5F9E", "list-scroll": "#5F6673",
    "info-bg": "#1E3350", "info-text": "#9FD0FF",
    "history-bg": "#1E3350", "history-text": _TEXT, "history-frame": "#7DB4F5",
    "history-focused": _BRIGHT, "history-focused-bg": "#2F5F9E",
}

MODERN_SYNTAX = {
    "keyword": "#C792EA", "name": "#82AAFF", "variable": "#7FD8E3", "builtin": "#5FB8C4",
    "string": "#A8DC8C", "type": "#E8C77D", "number": "#F2A36B", "constant": "#F2A36B",
    "modifier": "#E8C77D", "comment": "#8A93A3", "operator": "#89DDFF", "punct": "#A3ACBA",
    "special": "#FF7A85", "markup": "#F07178", "module": "#E8C77D",
    "error": _BRIGHT, "error-bg": "#8E2B36", "warning-bg": "#5A4A1F", "focus": "#101216", "focus-bg": "#7DB4F5",
    "inserted": "#101216", "inserted-bg": "#A8DC8C", "deleted": _BRIGHT, "deleted-bg": "#8E2B36",
}


# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Palette:
    name: str
    label: str  # with its ~hotkey~, for menus and dialogs
    description: str
    ansi: Mapping[str, str]
    chrome: Theme
    ui: Mapping[str, str]
    syntax: Mapping[str, str]
    _styles: dict = field(default_factory=dict, compare=False, repr=False)

    def hex(self, colour: str) -> str:
        """A slot name or a ``#RRGGBB``, as ``#RRGGBB`` (as the terminal's 16
        colours, when that is all it has: see ``set_ansi16``)."""
        value = colour if colour.startswith("#") else self.ansi[colour]
        return self.snap(value) if _ansi16 else value

    def slot_of(self, value: str) -> str:
        """The slot of this palette a ``#RRGGBB`` is, or is nearest to."""
        value = value.upper()
        for slot, rgb in self.ansi.items():
            if rgb.upper() == value:
                return slot
        r, g, b = (int(value[i:i + 2], 16) for i in (1, 3, 5))

        def distance(slot: str) -> int:
            rgb = self.ansi[slot]
            return sum((int(rgb[i:i + 2], 16) - c) ** 2 for i, c in zip((1, 3, 5), (r, g, b)))

        return min(SLOTS, key=distance)

    def snap(self, value: str) -> str:
        """``value`` as its slot's CGA colour: Rich sends exactly that ANSI colour."""
        return CGA[self.slot_of(value)] if value.startswith("#") else value

    def colour(self, role: str) -> str:
        """The ``#RRGGBB`` of a UI role (or a syntax role)."""
        return self.hex(self.ui[role] if role in self.ui else self.syntax[role])

    def style(self, fg: str | None = None, bg: str | None = None, **attrs: bool) -> Style:
        """A Rich style from roles."""
        return Style(color=self.colour(fg) if fg else None, bgcolor=self.colour(bg) if bg else None, **attrs)

    def token_styles(self) -> dict[str, Style]:
        """Token kind -> style, for the editor and everything that shows code."""
        if _ansi16 not in self._styles:  # one set per colour mode
            self._styles[_ansi16] = {
                kind: Style(
                    color=self.hex(self.syntax[fg]) if fg else None,
                    bgcolor=self.hex(self.syntax[bg]) if bg else None,
                    **attrs,
                )
                for kind, (fg, bg, attrs) in TOKENS.items()
            }
        return self._styles[_ansi16]

    def textual_theme(self) -> Theme:
        """The chrome, with divide's roles as ``$divide-<role>`` variables."""
        extra = {f"divide-{role}": self.colour(role) for role in UI_ROLES}
        theme = dataclasses.replace(self.chrome, name=self.name, variables={**self.chrome.variables, **extra})
        if not _ansi16:
            return theme

        def snap(value):
            return self.snap(value) if isinstance(value, str) and len(value) == 7 and value.startswith("#") else value

        colours = {f.name: snap(getattr(theme, f.name)) for f in dataclasses.fields(theme) if f.name not in ("name", "variables", "ansi")}
        return dataclasses.replace(theme, variables={k: snap(v) for k, v in theme.variables.items()}, **colours)


def recolour(theme: Theme, table: Mapping[str, str], name: str) -> Theme:
    """``theme`` (in CGA colours) with each CGA colour replaced by its slot in ``table``."""
    by_hex = {v.upper(): slot for slot, v in CGA.items()}

    def swap(value):
        if isinstance(value, str) and value.upper() in by_hex:
            return table[by_hex[value.upper()]]
        return value

    fields = {f.name: swap(getattr(theme, f.name)) for f in dataclasses.fields(theme) if f.name not in ("name", "variables", "ansi")}
    return dataclasses.replace(theme, name=name, variables={k: swap(v) for k, v in theme.variables.items()}, **fields)


THEMES: dict[str, Palette] = {
    p.name: p
    for p in (
        Palette("turbo-pascal", "Turbo ~P~ascal", "Turbo Vision's colours: gray menus, blue windows, yellow text.",
                CGA, THEME_TURBO_PASCAL, BORLAND_UI, BORLAND_SYNTAX),
        Palette("turbo-c", "Turbo ~C~", "Turbo C 2.01's: as Turbo Pascal, white-on-black menu hotkeys.",
                CGA, THEME_TURBO_C, BORLAND_UI, BORLAND_SYNTAX),
        Palette("free-pascal", "~F~ree Pascal", "Turbo Vision's layout in Windows Terminal's Campbell colours.",
                CAMPBELL, recolour(THEME_TURBO_PASCAL, CAMPBELL, "free-pascal"),
                FREE_PASCAL_UI, FREE_PASCAL_SYNTAX),
        Palette("modern-dark", "~M~odern dark", "Deep grays, light text and a blue accent, high contrast.",
                MODERN, MODERN_CHROME, MODERN_UI, MODERN_SYNTAX),
    )
}
DEFAULT = "turbo-pascal"

_current = DEFAULT
_ansi16 = False  # the terminal has only the 16 ANSI colours


def set_ansi16(only16: bool) -> None:
    """With 16 colours, each colour goes to the slot it stands for in its palette
    (Campbell's light green stays light green, modern-dark's surfaces black),
    not to the ANSI colour nearest in RGB, which loses what it meant."""
    global _ansi16
    _ansi16 = bool(only16)


def ansi16() -> bool:
    return _ansi16


def get(name: str | None) -> Palette:
    return THEMES.get(name or DEFAULT, THEMES[DEFAULT])


def current() -> Palette:
    """The palette of the running app (divide runs one app at a time)."""
    return THEMES[_current]


def use(name: str) -> Palette:
    global _current
    _current = name if name in THEMES else DEFAULT
    return THEMES[_current]


# Colour depth: what Rich (and so Textual) sends to the terminal.
DEPTHS = {"auto": "auto", "truecolor": "truecolor", "256": "256", "16": "standard"}
DEPTH_LABELS = {"auto": "~A~utomatic (what the terminal says)", "truecolor": "~T~rue colour (24-bit)",
                "256": "~2~56 colours", "16": "~1~6 colours (ANSI)"}
