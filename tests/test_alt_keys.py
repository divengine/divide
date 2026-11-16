"""Alt+letter opens its menu in every language, Alt+F and Alt+B too."""

from textual._xterm_parser import XTermParser

import divide.app  # noqa: F401 - it fixes the key table


def events(data: str) -> list:
    parser = XTermParser()
    return [e for e in list(parser.feed(data)) + list(parser.feed("")) if hasattr(e, "key")]


def keys(data: str) -> list[str]:
    return [event.key for event in events(data)]


def test_alt_f_and_alt_b_are_alt_keys():
    assert keys("\x1bf") == ["alt+f"]
    assert keys("\x1bb") == ["alt+b"]
    assert keys("\x1bs") == ["alt+s"]


def test_alt_letters_type_nothing():
    """Without a character, no editor or input line types the letter: the menus get it."""
    assert [(e.key, e.character, e.is_printable) for e in events("\x1bc")] == [("alt+c", None, False)]
    assert [(e.key, e.character) for e in events("c")] == [("c", "c")]
