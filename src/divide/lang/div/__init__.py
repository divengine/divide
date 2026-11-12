"""The Div template language (github.com/divengine/div)."""

from .dialect import DEFAULT_DIALECT, DEFAULT_TAGS, Dialect, resolve_dialect, template_properties
from .lexer import Lexer, Token, tokenize

__all__ = [
    "DEFAULT_DIALECT", "DEFAULT_TAGS", "Dialect", "Lexer", "Token",
    "resolve_dialect", "template_properties", "tokenize",
]
