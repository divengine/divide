"""The languages of divide's interface: gettext catalogues.

divide's own texts (menus, dialogs, hints, messages) are written in English
and marked ``_("...")``; ``locale/<lang>/LC_MESSAGES/divide.mo`` holds each
translation, made from ``divide.po`` (``tools/i18n.py`` extracts, updates and
compiles them with Babel). What other programs say (Div, PHP, Xdebug, the
language servers) is shown as they say it.

The language is chosen once, when divide starts, the first one of:

- ``DIVIDE_LANGUAGE`` in the environment (the tests and the screenshots use ``en``),
- ``--language`` on the command line (read from ``sys.argv`` at import: see ``argv_language``),
- ``language`` in the config (Options > Language: it applies at the next start),
- the system's: ``LANGUAGE``, ``LC_ALL``, ``LC_MESSAGES``, ``LANG``.

A language without a catalogue is English. Translations keep the menus'
``~hotkey~`` marks (a letter unique in its menu or dialog) and the
``{placeholders}``; ``tests/test_i18n.py`` checks both, and that every text
is translated.
"""

from __future__ import annotations

import gettext
import os
import sys
from pathlib import Path

from divide import config

DOMAIN = "divide"
LOCALE_DIR = Path(__file__).parent / "locale"
SOURCE = "en"  # the language the texts are written in
LANGUAGES = {"auto": "Automatic (the system's)", "en": "~E~nglish", "es": "E~s~pañol"}  # each in itself, with its own hotkey

_translation: gettext.NullTranslations = gettext.NullTranslations()
current = SOURCE


def available() -> list[str]:
    """The languages divide has: English and those with a compiled catalogue."""
    found = {p.parent.parent.name for p in LOCALE_DIR.glob(f"*/LC_MESSAGES/{DOMAIN}.mo")}
    return [SOURCE, *sorted(found - {SOURCE})]


def system_language() -> str:
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "")
        for part in value.split(":"):  # LANGUAGE may list several: es_ES:es:en
            code = part.split(".")[0].split("@")[0].split("_")[0].lower()
            if code and code not in ("c", "posix"):
                return code
    return SOURCE


def argv_language(argv: list[str] | None = None) -> str | None:
    """``--language X`` given to the divide command. The texts are made when the modules are
    imported, before ``main`` parses its arguments, so the language is read here first."""
    argv = sys.argv if argv is None else argv
    if not argv or "divide" not in Path(argv[0]).name:
        return None
    args = argv[1:]
    for n, arg in enumerate(args):
        if arg == "--language" and n + 1 < len(args):
            return args[n + 1]
        if arg.startswith("--language="):
            return arg.split("=", 1)[1]
    return None


def chosen() -> str:
    """The language to use, by the order above."""
    forced = os.environ.get("DIVIDE_LANGUAGE") or argv_language()
    if forced and forced != "auto":
        return forced
    setting = config.load().get("language", "auto")
    return system_language() if setting in (None, "", "auto") else str(setting)


def use(language: str) -> str:
    """Translate into ``language`` from now on (English when there is no catalogue). Returns it."""
    global _translation, current
    code = language.split("_")[0].lower()
    if code == SOURCE:
        _translation, current = gettext.NullTranslations(), SOURCE
        return current
    try:
        _translation = gettext.translation(DOMAIN, LOCALE_DIR, languages=[code])
        current = code
    except OSError:
        _translation, current = gettext.NullTranslations(), SOURCE
    return current


def _(text: str) -> str:
    """``text`` in the interface's language."""
    return _translation.gettext(text)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _translation.ngettext(singular, plural, n)


use(chosen())
