#!/usr/bin/env python3
"""divide's translations, with Babel (a development tool: divide itself needs only gettext).

    tools/i18n.py extract          # src/divide/locale/divide.pot from the texts marked _("...")
    tools/i18n.py update           # merge the .pot into every locale/<lang>/LC_MESSAGES/divide.po
    tools/i18n.py init es          # start a new language
    tools/i18n.py compile          # .po -> .mo (shipped with divide)
    tools/i18n.py all              # extract, update, compile

Translate the .po files with any gettext editor (Poedit, Weblate...), keeping
the ``~hotkey~`` marks (one letter, unique in its menu or dialog) and the
``{placeholders}``; tests/test_i18n.py checks them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "divide"
LOCALE = SRC / "locale"
POT = LOCALE / "divide.pot"
PYBABEL = [sys.executable, "-m", "babel.messages.frontend"]


def run(*args: str) -> None:
    subprocess.run([*PYBABEL, *args], check=True, cwd=ROOT)


def extract() -> None:
    LOCALE.mkdir(parents=True, exist_ok=True)
    run("extract", "--no-location", "--sort-output", "--keywords=_ ngettext:1,2", "--project=divide",
        "--msgid-bugs-address=https://github.com/divengine/divide/issues", "-o", str(POT), str(SRC))


def update() -> None:
    if any(LOCALE.glob("*/LC_MESSAGES/divide.po")):
        run("update", "--no-fuzzy-matching", "-D", "divide", "-i", str(POT), "-d", str(LOCALE))


def compile_all() -> None:
    if any(LOCALE.glob("*/LC_MESSAGES/divide.po")):
        run("compile", "--statistics", "-D", "divide", "-d", str(LOCALE))


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "all"
    if command == "extract":
        extract()
    elif command == "update":
        update()
    elif command == "init" and len(sys.argv) > 2:
        run("init", "-D", "divide", "-i", str(POT), "-d", str(LOCALE), "-l", sys.argv[2])
    elif command == "compile":
        compile_all()
    elif command == "all":
        extract(); update(); compile_all()
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
