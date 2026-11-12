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
