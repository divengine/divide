"""The editor's TextArea themes, made from the palettes (divide.themes)."""

from __future__ import annotations

from rich.style import Style
from textual._text_area_theme import TextAreaTheme

from divide import themes
from divide.themes import CGA  # noqa: F401  (the CGA colours, for whoever needs a slot's RGB)

EDITOR, OUTPUT = "editor", "output"
SELECTION = "divide.selection"  # the selection, drawn over the syntax colours (DivEditor._render_line)


def theme_name(palette: themes.Palette, kind: str) -> str:
    return palette.name if kind == EDITOR else f"{palette.name}-{kind}"


def editor_theme(p: themes.Palette) -> TextAreaTheme:
    """The editor: Borland's yellow on blue in the Borland themes."""
    return TextAreaTheme(
        name=theme_name(p, EDITOR),
        base_style=p.style("editor-text", "editor-bg"),
        gutter_style=p.style("editor-gutter", "editor-bg"),
        cursor_style=p.style("editor-cursor", "editor-cursor-bg"),
        cursor_line_gutter_style=p.style("editor-cursor-line", "editor-bg"),
        bracket_matching_style=p.style("editor-bracket", "editor-bracket-bg", bold=True),
        selection_style=p.style("editor-selection", "editor-selection-bg"),
        syntax_styles={**p.token_styles(), SELECTION: p.style("editor-selection", "editor-selection-bg")},
    )


def output_theme(p: themes.Palette) -> TextAreaTheme:
    """Turbo Pascal's Output window; Div tags left in a render keep their
    colours, everything else is plain."""
    return TextAreaTheme(
        name=theme_name(p, OUTPUT),
        base_style=p.style("output-text", "output-bg"),
        gutter_style=p.style("output-gutter", "output-bg"),
        cursor_style=p.style("output-cursor", "output-cursor-bg"),
        cursor_line_gutter_style=p.style("output-cursor-bg", "output-bg"),
        bracket_matching_style=p.style("output-text", "output-bg"),
        selection_style=p.style("output-selection", "output-selection-bg"),
        syntax_styles={**{k: v for k, v in p.token_styles().items() if k.startswith("div.")},
                       SELECTION: p.style("output-selection", "output-selection-bg")},
    )


_all: dict[bool, list[TextAreaTheme]] = {}  # per colour mode (themes.ansi16)


def all_themes() -> list[TextAreaTheme]:
    """Every palette's editor and output themes (made once per colour mode)."""
    mode = themes.ansi16()
    if mode not in _all:
        _all[mode] = [make(p) for p in themes.THEMES.values() for make in (editor_theme, output_theme)]
    return _all[mode]
