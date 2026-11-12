"""Colour theme for Div token kinds (used by the editor and the CLI preview)."""

from __future__ import annotations

from rich.style import Style

# Palette loosely based on Monokai, tuned so that the families of Div blocks
# are distinguishable at a glance: replacements (cyan), control flow (pink),
# scopes (orange), definitions (green), code containers (purple).
DIV_STYLES: dict[str, Style] = {
    "div.replace": Style(color="#66D9EF"),
    "div.modifier": Style(color="#FD971F", bold=True),
    "div.var": Style(color="#A6E3FF"),
    "div.var.builtin": Style(color="#66D9EF", italic=True),
    "div.var.def": Style(color="#A6E22E", bold=True),
    "div.format": Style(color="#E6DB74"),
    "div.loop": Style(color="#F92672", bold=True),
    "div.cond": Style(color="#F92672", bold=True),
    "div.keyword": Style(color="#F92672", bold=True, italic=True),
    "div.capsule": Style(color="#FD971F", bold=True),
    "div.location": Style(color="#FD971F", bold=True),
    "div.subparser": Style(color="#AE81FF", bold=True),
    "div.multirep": Style(color="#AE81FF", bold=True),
    "div.include": Style(color="#A6E22E", bold=True),
    "div.path": Style(color="#A6E22E", underline=True),
    "div.tplvar": Style(color="#A6E22E", bold=True),
    "div.special": Style(color="#AE81FF", bold=True),
    "div.comment": Style(color="#75715E", italic=True),
    "div.doc": Style(color="#9C9A86", bold=True, italic=True),
    "div.ignored": Style(color="#B8B8A8", dim=True),
    "div.macro": Style(color="#AE81FF", bold=True),
    "div.friendly": Style(color="#75715E"),
    "div.property": Style(color="#FD971F", bold=True),
    "div.property.value": Style(color="#E6DB74"),
    "div.string": Style(color="#E6DB74"),
    "div.number": Style(color="#AE81FF"),
    "div.constant": Style(color="#66D9EF", italic=True),
    "div.operator": Style(color="#F92672"),
    "div.function": Style(color="#A6E22E"),
    "div.punct": Style(color="#C0C0B8"),
    "div.key": Style(color="#FD971F"),
    "div.error": Style(color="#FFFFFF", bgcolor="#8B1E3F", bold=True),
    "html.tag": Style(color="#7F9FBF"),
    "html.attr": Style(color="#9FB8A0"),
    "html.string": Style(color="#C8B88A"),
    "html.comment": Style(color="#75715E", italic=True),
    "html.entity": Style(color="#AE81FF"),
}


# --------------------------------------------------------------------------
# Borland-style palette: the 16 CGA text-mode colours, yellow on blue like the
# Turbo Pascal / Turbo C editors. Div is the "code" of a template, so its
# structure gets the reserved-word white, variables get light cyan, and the
# HTML around it stays in the quieter cyan/yellow range.
CGA = {
    "black": "#000000", "blue": "#0000AA", "green": "#00AA00", "cyan": "#00AAAA",
    "red": "#AA0000", "magenta": "#AA00AA", "brown": "#AA5500", "lightgray": "#AAAAAA",
    "darkgray": "#555555", "lightblue": "#5555FF", "lightgreen": "#55FF55",
    "lightcyan": "#55FFFF", "lightred": "#FF5555", "lightmagenta": "#FF55FF",
    "yellow": "#FFFF55", "white": "#FFFFFF",
}


def _c(name: str, **kw) -> Style:
    return Style(color=CGA[name], **kw)


TURBO_STYLES: dict[str, Style] = {
    "div.replace": _c("lightcyan"),
    "div.modifier": _c("lightmagenta"),
    "div.var": _c("lightcyan"),
    "div.var.builtin": _c("lightgreen"),
    "div.var.def": _c("white", bold=True),
    "div.format": _c("lightmagenta"),
    "div.loop": _c("white", bold=True),
    "div.cond": _c("white", bold=True),
    "div.keyword": _c("white", bold=True),
    "div.capsule": _c("white", bold=True),
    "div.location": _c("white", bold=True),
    "div.subparser": _c("lightred", bold=True),
    "div.multirep": _c("lightred", bold=True),
    "div.include": _c("white", bold=True),
    "div.path": _c("lightgreen", underline=True),
    "div.tplvar": _c("white", bold=True),
    "div.special": _c("lightred"),
    "div.comment": _c("lightgray"),
    "div.doc": _c("lightgray", bold=True),
    "div.ignored": _c("lightgray"),
    "div.macro": _c("lightred", bold=True),
    "div.friendly": _c("lightgray"),
    "div.property": _c("white"),
    "div.property.value": _c("lightcyan"),
    "div.string": _c("lightgreen"),
    "div.number": _c("lightmagenta"),
    "div.constant": _c("lightmagenta"),
    "div.operator": _c("yellow"),
    "div.function": _c("white"),
    "div.punct": _c("yellow"),
    "div.key": _c("lightcyan"),
    "div.error": Style(color=CGA["white"], bgcolor=CGA["red"], bold=True),
    "html.tag": _c("cyan"),
    "html.attr": _c("cyan"),
    "html.string": _c("lightgreen"),
    "html.comment": _c("lightgray"),
    "html.entity": _c("lightmagenta"),
}
