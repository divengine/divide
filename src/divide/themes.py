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

from divide.i18n import _

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
# tree-sitter's other grammars (divide.lang.treesitter: Textual's queries, captures as ts.*)
_tok("keyword", "ts.keyword", "ts.keyword.operator", "ts.conditional", "ts.storageclass", "ts.import", "ts.include",
     "ts.media", "ts.charset", "ts.keyframes", "ts.supports", "ts.namespace", "ts.preproc", "ts.toml.type",
     "ts.heading", "ts.markup.heading", **B)
_tok("markup", "ts.tag", "ts.markup")
_tok("name", "ts.tag.attribute", "ts.attribute", "ts.property", "ts.css.property", "ts.yaml.field", "ts.field",
     "ts.label", "ts.function", "ts.function.builtin", "ts.function.method", "ts.function.call", "ts.constructor")
_tok("string", "ts.string", "ts.string.special", "ts.string.special.symbol", "ts.text.literal", "ts.markup.raw")
_tok("string", "ts.text.uri", "ts.link.uri", "ts.markup.link", underline=True)
_tok("special", "ts.string.escape", "ts.link.label", "ts.embedded", "ts.punctuation.special")
_tok("comment", "ts.comment")
_tok("number", "ts.number", "ts.float", "ts.toml.datetime")
_tok("constant", "ts.constant", "ts.boolean")
_tok("constant", "ts.constant.builtin", **B)
_tok("type", "ts.type", "ts.type.builtin", "ts.type.definition", "ts.type.qualifier")
_tok("variable", "ts.variable", "ts.parameter")
_tok("variable", "ts.variable.builtin", **B)
_tok("operator", "ts.operator")
_tok("punct", "ts.punctuation.bracket", "ts.punctuation.delimiter", "ts.tag.delimiter", "ts.list.marker",
     "ts.heading.marker")
# INI and CSV (divide.lang.plain): a column in each colour, in turn
_tok("keyword", "ini.section", **B)
_tok("name", "ini.key")
_tok("string", "ini.string")
_tok("number", "ini.number")
_tok("constant", "ini.constant")
_tok("comment", "ini.comment")
_tok("operator", "ini.operator")
for _n, _role in enumerate(("keyword", "string", "number", "name", "type", "constant")):
    _tok(_role, f"csv.col{_n}")
_tok("punct", "csv.sep")
_tok("error", "ts.error", "ts.html.end_tag_error", "ts.toml.error", bg="error-bg")
_tok("error", "div.error", "json.error", bg="error-bg", **B)
_tok("error", "diag.error", bg="error-bg")  # diagnostics, over the syntax colours
_tok("warning", "diag.warning", bg="warning-bg")  # its own colour: a number or a constant may be brown too
_tok("focus", "dialector.focus", bg="focus-bg", **B)
_tok("inserted", "trace.new", bg="inserted-bg", **B)  # what a mutation wrote
_tok("deleted", "trace.old", bg="deleted-bg", **B)  # what it took away
_tok("diff-add", "diff.add", bg="diff-add-bg")  # a diff's lines (Git): added, removed
_tok("diff-del", "diff.del", bg="diff-del-bg")
_tok("diff-mod", "diff.mod", bg="diff-mod-bg")  # our side of a conflict
_tok("diff-hunk", "diff.hunk")  # @@ -1,3 +1,4 @@
_tok("diff-meta", "diff.meta", **B)  # diff --git, index, ---, +++, a commit's header
del B

SYNTAX_ROLES = (
    "keyword", "name", "variable", "builtin", "string", "type", "number", "constant", "modifier",
    "comment", "operator", "punct", "special", "markup", "module",
    "error", "error-bg", "warning", "warning-bg", "focus", "focus-bg", "inserted", "inserted-bg", "deleted", "deleted-bg",
    "diff-add", "diff-add-bg", "diff-del", "diff-del-bg", "diff-hunk", "diff-meta", "diff-mod", "diff-mod-bg",
    # the diff viewer (divide.ui.diffview): a line's background, the words that changed in it
    "diff-text", "diff-add-line", "diff-add-word", "diff-del-line", "diff-del-word", "diff-mod-line",
    "diff-file", "diff-file-bg",
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
    "list-match", "list-match-focused", "list-dim",
    "info-bg", "info-text",
    "history-bg", "history-text", "history-frame", "history-focused", "history-focused-bg",
    "dialog-frame", "dialog-title",
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
    "list-match": "white", "list-match-focused": "yellow", "list-dim": "blue",  # Go to file: the letters typed, the folders
    "info-bg": "blue", "info-text": "cyan",  # File > Open's pane: the folder, the file under the bar
    "history-bg": "blue", "history-text": "white", "history-frame": "white",  # an input line's earlier entries
    "history-focused": "black", "history-focused-bg": "cyan",
    "dialog-frame": "white", "dialog-title": "white",  # a dialog's double frame and its title, on the gray
}

# Div's structure in the reserved-word white, variables in light cyan, the HTML
# around it in the quieter cyan.
BORLAND_SYNTAX = {
    "keyword": "white", "name": "white", "variable": "lightcyan", "builtin": "lightgreen",
    "string": "lightgreen", "type": "lightgreen", "number": "lightmagenta", "constant": "lightmagenta",
    "modifier": "lightmagenta", "comment": "lightgray", "operator": "yellow", "punct": "yellow",
    "special": "lightred", "markup": "cyan", "module": "cyan",
    "error": "white", "error-bg": "red", "warning": "white", "warning-bg": "brown", "focus": "black", "focus-bg": "lightcyan",
    "inserted": "black", "inserted-bg": "lightgreen", "deleted": "white", "deleted-bg": "red",
    "diff-add": "white", "diff-add-bg": "green", "diff-del": "white", "diff-del-bg": "red",
    "diff-hunk": "lightcyan", "diff-meta": "yellow", "diff-mod": "white", "diff-mod-bg": "brown",
    "diff-text": "white", "diff-add-line": "#005A00", "diff-add-word": "#00A000",
    "diff-del-line": "#6A0000", "diff-del-word": "#B00000", "diff-mod-line": "#5A4A00",
    "diff-file": "black", "diff-file-bg": "cyan",
}

# Campbell's blue is lighter than CGA's: its cyan, light red and light magenta
# no longer read on it, so those roles take the Campbell colours that do.
FREE_PASCAL_SYNTAX = {
    **BORLAND_SYNTAX,
    "number": "brown", "constant": "brown", "modifier": "brown",
    "special": "lightcyan", "markup": "lightgray", "module": "lightgray",
}

FREE_PASCAL_UI = {
    **BORLAND_UI, "editor-gutter": "lightgray", "info-text": "lightcyan",  # Campbell's cyan is faint on its blue
    "dialog-frame": "black", "dialog-title": "black",  # its white is nearly its light gray
}

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
    "list-match": "#7DB4F5", "list-match-focused": "#E8C77D", "list-dim": "#8B93A1",
    "info-bg": "#1E3350", "info-text": "#9FD0FF",
    "history-bg": "#1E3350", "history-text": _TEXT, "history-frame": "#7DB4F5",
    "history-focused": _BRIGHT, "history-focused-bg": "#2F5F9E",
    "dialog-frame": _BRIGHT, "dialog-title": _BRIGHT,
}

MODERN_SYNTAX = {
    "keyword": "#C792EA", "name": "#82AAFF", "variable": "#7FD8E3", "builtin": "#5FB8C4",
    "string": "#A8DC8C", "type": "#E8C77D", "number": "#F2A36B", "constant": "#F2A36B",
    "modifier": "#E8C77D", "comment": "#8A93A3", "operator": "#89DDFF", "punct": "#A3ACBA",
    "special": "#FF7A85", "markup": "#F07178", "module": "#E8C77D",
    "error": _BRIGHT, "error-bg": "#8E2B36", "warning": _BRIGHT, "warning-bg": "#5A4A1F", "focus": "#101216", "focus-bg": "#7DB4F5",
    "inserted": "#101216", "inserted-bg": "#A8DC8C", "deleted": _BRIGHT, "deleted-bg": "#8E2B36",
    "diff-add": "#D8F0CC", "diff-add-bg": "#1F3A24", "diff-del": "#F5C6CB", "diff-del-bg": "#4A1F26",
    "diff-hunk": "#7FD8E3", "diff-meta": "#E8C77D", "diff-mod": _BRIGHT, "diff-mod-bg": "#5A4A1F",
    "diff-text": _TEXT, "diff-add-line": "#1C3326", "diff-add-word": "#2F6B40",
    "diff-del-line": "#3D1E24", "diff-del-word": "#83303C", "diff-mod-line": "#3D3520",
    "diff-file": _BRIGHT, "diff-file-bg": _RAISED,
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
    # A monochrome theme: the only ANSI slots it may become with 16 colours (None: any, each its own),
    # the attributes that tell token kinds apart where hue cannot, and marks drawn where hue was the cue.
    ansi16_slots: tuple[str, ...] | None = None
    token_attrs: Mapping[str, Mapping[str, bool]] = field(default_factory=dict)
    marks: bool = False
    menu_active: str | None = None  # the text of the menu item under the bar (default: the menus' text)
    hotkey_style: str = "none"  # menus' and buttons' hotkey letters: underlined where a brighter one is not enough
    _styles: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def monochrome(self) -> bool:
        return self.ansi16_slots is not None

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

    def slot16_of(self, value: str) -> str:
        """The slot ``value`` becomes with 16 colours: its own (``slot_of``), or for a monochrome
        theme the nearest of the few it may use, by light (so it stays one hue, never another)."""
        if self.ansi16_slots is None:
            return self.slot_of(value)
        light = _light(value)
        return min(self.ansi16_slots, key=lambda slot: abs(_light(self.ansi[slot]) - light))

    def snap(self, value: str) -> str:
        """``value`` as its slot's CGA colour: Rich sends exactly that ANSI colour."""
        return CGA[self.slot16_of(value)] if value.startswith("#") else value

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
                    **{**attrs, **self.token_attrs.get(kind, {})},
                )
                for kind, (fg, bg, attrs) in TOKENS.items()
            }
        return self._styles[_ansi16]

    def textual_theme(self) -> Theme:
        """The chrome, with divide's roles as ``$divide-<role>`` variables."""
        extra = {f"divide-{role}": self.colour(role) for role in UI_ROLES}
        extra["divide-menu-active"] = self.hex(self.menu_active) if self.menu_active else self.chrome.variables["text"]
        extra["divide-hotkey-style"] = self.hotkey_style
        theme = dataclasses.replace(self.chrome, name=self.name, variables={**self.chrome.variables, **extra})
        if not _ansi16:
            return theme

        def snap(value):
            return self.snap(value) if isinstance(value, str) and len(value) == 7 and value.startswith("#") else value

        colours = {f.name: snap(getattr(theme, f.name)) for f in dataclasses.fields(theme) if f.name not in ("name", "variables", "ansi")}
        return dataclasses.replace(theme, variables={k: snap(v) for k, v in theme.variables.items()}, **colours)


def _light(value: str) -> float:
    """How light a ``#RRGGBB`` is (relative luminance, 0 to 1)."""
    def channel(c: int) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(value[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def recolour(theme: Theme, table: Mapping[str, str], name: str) -> Theme:
    """``theme`` (in CGA colours) with each CGA colour replaced by its slot in ``table``."""
    by_hex = {v.upper(): slot for slot, v in CGA.items()}

    def swap(value):
        if isinstance(value, str) and value.upper() in by_hex:
            return table[by_hex[value.upper()]]
        return value

    fields = {f.name: swap(getattr(theme, f.name)) for f in dataclasses.fields(theme) if f.name not in ("name", "variables", "ansi")}
    return dataclasses.replace(theme, name=name, variables={k: swap(v) for k, v in theme.variables.items()}, **fields)


# Turbo Pascal's chrome in Campbell's colours, but for the labels: Campbell's light yellow and white
# vanish on its light gray, so their hotkeys are red (as the menus' are on the same gray) and the
# label of the control with the focus is blue.
_fp = recolour(THEME_TURBO_PASCAL, CAMPBELL, "free-pascal")
FREE_PASCAL_CHROME = dataclasses.replace(
    _fp, variables={**_fp.variables, "label-hotkey": CAMPBELL["red"], "label-highlight": CAMPBELL["blue"]})

# --------------------------------------------------------------------------
# Phosphor: one hue in levels of light, as on a monochrome CRT (white, green P1, amber P3). Where the
# other themes tell things apart by hue, these do it by light, by reverse video (a bright bar with
# dark text), by bold, underline and strike, and by marks in the editor's margin (``marks``).
@dataclass(frozen=True)
class Phosphor:
    bg: str  # the screen: #000000 on the black variants, a dark tint on the others
    panel: str  # menus, dialogs, lists: a little lit
    raised: str  # a bar, a line that stands out, a field
    mid: str  # half lit: a changed word, a dim bar
    dim: str  # gutters, comments, what is secondary
    text: str  # the text
    bright: str  # the bar, what is emphasised
    max: str  # the brightest: keywords, frames of the active window
    slots16: tuple[str, ...]  # what it may become with 16 colours: black and the hue's dark and light slots


def _phosphor_ansi(p: Phosphor) -> dict[str, str]:
    """The 16 slots in the hue: the dark ones dim, the light ones bright (file marks, Git letters...)."""
    dark, light = p.dim, p.bright
    return {"black": "#000000", "blue": dark, "green": dark, "cyan": dark, "red": dark, "magenta": dark,
            "brown": dark, "lightgray": p.text, "darkgray": p.mid, "lightblue": light, "lightgreen": light,
            "lightcyan": light, "lightred": light, "lightmagenta": light, "yellow": light, "white": p.max}


def _phosphor_chrome(name: str, p: Phosphor) -> Theme:
    return dataclasses.replace(
        THEME_TURBO_PASCAL, name=name,
        primary=p.bright, secondary=p.raised, accent=p.bright, foreground=p.max, background=p.bg,
        surface=p.panel, panel=p.panel, warning=p.bright, error=p.max, success=p.bright,
        variables={
            "text": p.text, "text-muted": p.dim,
            "window-content-background": p.bg,
            "block-cursor-foreground": p.bg, "block-cursor-background": p.bright, "block-cursor-text-style": "bold",
            "input-cursor-foreground": p.bg, "input-cursor-background": p.text, "input-cursor-text-style": "none",
            "scrollbar": p.dim, "scrollbar-active": p.bright, "scrollbar-background": p.panel,
            "scrollbar-background-hover": p.panel, "scrollbar-background-active": p.panel,
            "scrollbar-corner-color": p.panel, "scrollbar-color-hover": p.bright,
            "input-fg": p.bright, "input-bg": p.raised, "input-selected-fg": p.bg, "input-selected-bg": p.bright,
            "input-arrow": p.bright,
            "button-face-fg": p.max, "button-face-bg": p.raised, "button-default-fg": p.max,
            "button-focused-fg": p.bg, "button-focused-bg": p.bright,
            "button-disabled-fg": p.mid, "button-disabled-bg": p.panel, "button-hotkey": p.bright,
            "button-shadow-fg": "#000000", "button-shadow-bg": p.panel,
            "label-highlight": p.max, "label-hotkey": p.bright,
            "frame-icon": p.bright,
            "combo-arrow-fg": p.max, "combo-arrow-bg": p.raised, "combo-sides-fg": p.raised, "combo-sides-bg": p.panel,
            "cluster-fg": p.text, "cluster-bg": p.panel, "cluster-focused-fg": p.max, "cluster-focused-bg": p.panel,
            "cluster-hotkey": p.bright, "cluster-disabled-fg": p.mid, "cluster-disabled-bg": p.panel,
            "link-color": p.bright, "link-background": "transparent", "link-color-hover": p.bg,
            "link-background-hover": p.bright,
            "footer-foreground": p.text, "footer-background": p.panel, "footer-key-foreground": p.bright,
            "footer-key-background": p.panel, "footer-description-foreground": p.text,
            "footer-description-background": p.panel,
            "menu-hotkey": p.max, "menu-hotkey-background": p.panel,
            "desktop-pattern-color": p.raised,
        },
    )


def _phosphor_ui(p: Phosphor) -> dict[str, str]:
    return {
        "desktop": p.bg, "desktop-pattern": p.raised,
        "shadow": "#000000", "shadow-text": p.dim,
        "editor-bg": p.bg, "editor-text": p.text, "editor-gutter": p.dim,
        "editor-cursor": p.bg, "editor-cursor-bg": p.bright, "editor-cursor-line": p.bright,
        "editor-bracket": p.max, "editor-bracket-bg": p.raised,
        "editor-selection": p.bg, "editor-selection-bg": p.text,  # reverse video
        "breakpoint": p.max, "breakpoint-bg": p.raised,  # and its mark in the margin
        "execution": p.bg, "execution-bg": p.bright,  # reverse: the brightest bar there is, and its mark
        "output-bg": p.bg, "output-text": p.text, "output-gutter": p.dim,
        "output-cursor": p.bg, "output-cursor-bg": p.text,
        "output-selection": p.bg, "output-selection-bg": p.text,
        "output-frame": p.bright, "output-frame-passive": p.dim,
        "debug-bg": p.panel, "debug-text": p.text, "debug-frame": p.bright, "debug-frame-passive": p.dim,
        "debug-title": p.max, "debug-selected": p.bg, "debug-selected-bg": p.bright,
        "help-bg": p.panel, "help-text": p.text, "help-bold": p.max, "help-code": p.bright,
        "help-link": p.max, "help-url": p.bright, "help-rule": p.dim,
        "help-selected": p.bg, "help-selected-bg": p.bright, "help-frame": p.bright, "help-frame-passive": p.dim,
        "progress-fill": p.bright, "progress-track": p.raised, "progress-text": p.text,
        "verdict-error": p.max,
        "list-bg": p.panel, "list-text": p.text, "list-selected": p.max,
        "list-focused": p.bg, "list-focused-bg": p.bright, "list-scroll": p.dim,
        "list-match": p.max, "list-match-focused": p.raised, "list-dim": p.dim,
        "info-bg": p.raised, "info-text": p.bright,
        "history-bg": p.raised, "history-text": p.text, "history-frame": p.bright,
        "history-focused": p.bg, "history-focused-bg": p.bright,
        "dialog-frame": p.bright, "dialog-title": p.max,
    }


def _phosphor_syntax(p: Phosphor) -> dict[str, str]:
    """Light, not hue: keywords brightest and bold, names and values bright, text normal, comments dim."""
    return {
        "keyword": p.max, "name": p.text, "variable": p.bright, "builtin": p.bright,
        "string": p.text, "type": p.bright, "number": p.bright, "constant": p.bright,
        "modifier": p.text, "comment": p.dim, "operator": p.text, "punct": p.dim,
        "special": p.max, "markup": p.text, "module": p.text,
        # states: an error is the brightest bar (reverse), a warning a raised one, underlined
        "error": p.bg, "error-bg": p.bright, "warning": p.max, "warning-bg": p.raised, "focus": p.bg, "focus-bg": p.bright,
        "inserted": p.bg, "inserted-bg": p.bright, "deleted": p.text, "deleted-bg": p.raised,
        "diff-add": p.bg, "diff-add-bg": p.bright, "diff-del": p.text, "diff-del-bg": p.raised,
        "diff-hunk": p.bright, "diff-meta": p.max, "diff-mod": p.max, "diff-mod-bg": p.mid,
        "diff-text": p.text, "diff-add-line": p.raised, "diff-add-word": p.mid,
        "diff-del-line": p.panel, "diff-del-word": p.raised, "diff-mod-line": p.mid,
        "diff-file": p.bg, "diff-file-bg": p.text,
    }


# What hue told apart, told apart otherwise: comments in italics, a warning underlined (an error is a
# bright bar), what a mutation took away struck through, a deleted diff line too.
PHOSPHOR_ATTRS = {
    "div.comment": {"italic": True}, "html.comment": {"italic": True}, "php.comment": {"italic": True},
    "json.comment": {"italic": True}, "ts.comment": {"italic": True}, "ini.comment": {"italic": True},
    "diag.error": {"bold": True}, "diag.warning": {"underline": True},
    "trace.old": {"strike": True}, "diff.del": {"strike": True},
}

_GREEN = dict(mid="#1C5A26", dim="#2FA043", text="#4FE065", bright="#8CFF96", max="#D4FFD8",
              slots16=("black", "green", "lightgreen"))
_AMBER = dict(mid="#553300", dim="#B07000", text="#F0A020", bright="#FFC24D", max="#FFE6B0",
              slots16=("black", "brown", "yellow"))
PHOSPHORS = {
    "phosphor-white": Phosphor(bg="#000000", panel="#141414", raised="#2A2A2A", mid="#4A4A4A", dim="#8E8E8E",
                               text="#C8C8C8", bright="#EEEEEE", max="#FFFFFF",
                               slots16=("black", "darkgray", "lightgray", "white")),
    "phosphor-green": Phosphor(bg="#06140A", panel="#0C2412", raised="#143A1C", **_GREEN),
    "phosphor-green-black": Phosphor(bg="#000000", panel="#0A1E0E", raised="#123419", **_GREEN),
    "phosphor-amber": Phosphor(bg="#140C02", panel="#241606", raised="#3A240A", **_AMBER),
    "phosphor-amber-black": Phosphor(bg="#000000", panel="#1E1205", raised="#33200A", **_AMBER),
}


def _phosphor_palette(name: str, label: str, description: str) -> Palette:
    p = PHOSPHORS[name]
    return Palette(name, label, description, _phosphor_ansi(p), _phosphor_chrome(name, p), _phosphor_ui(p),
                   _phosphor_syntax(p), ansi16_slots=p.slots16, token_attrs=PHOSPHOR_ATTRS, marks=True,
                   menu_active=p.bg, hotkey_style="underline")


THEMES: dict[str, Palette] = {
    p.name: p
    for p in (
        Palette("turbo-pascal", _('Turbo ~P~ascal'), _("Turbo Vision's colours: gray menus, blue windows, yellow text."),
                CGA, THEME_TURBO_PASCAL, BORLAND_UI, BORLAND_SYNTAX),
        Palette("turbo-c", _('Turbo ~C~'), _("Turbo C 2.01's: as Turbo Pascal, white-on-black menu hotkeys."),
                CGA, THEME_TURBO_C, BORLAND_UI, BORLAND_SYNTAX),
        Palette("free-pascal", _('~F~ree Pascal'), _("Turbo Vision's layout in Windows Terminal's Campbell colours."),
                CAMPBELL, FREE_PASCAL_CHROME,
                FREE_PASCAL_UI, FREE_PASCAL_SYNTAX),
        Palette("modern-dark", _('~M~odern dark'), _('Deep grays, light text and a blue accent, high contrast.'),
                MODERN, MODERN_CHROME, MODERN_UI, MODERN_SYNTAX),
        _phosphor_palette("phosphor-white", _('Phosphor ~W~hite'),
                          _('A monochrome screen: white and grays on black, nothing told by hue.')),
        _phosphor_palette("phosphor-green", _('Phosphor ~G~reen'),
                          _('Green phosphor on dark green glass, nothing told by hue.')),
        _phosphor_palette("phosphor-green-black", _('Phosphor Green ~B~lack'),
                          _('The same green phosphor on a black screen.')),
        _phosphor_palette("phosphor-amber", _('Phosphor Ambe~r~'),
                          _('Amber phosphor on dark amber glass, nothing told by hue.')),
        _phosphor_palette("phosphor-amber-black", _('Phosphor Amber B~l~ack'),
                          _('The same amber phosphor on a black screen.')),
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
DEPTH_LABELS = {"auto": _('~A~utomatic (what the terminal says)'), "truecolor": _('~T~rue colour (24-bit)'),
                "256": _('~2~56 colours'), "16": _('~1~6 colours (ANSI)')}
