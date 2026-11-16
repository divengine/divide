"""Options > Language: the language of divide's interface, from the next start.

The texts are made when divide starts (see divide.i18n), so the choice is
kept in the config (``language``) and applies the next time; ``--language``
and ``DIVIDE_LANGUAGE`` choose for one run without changing it. Each
language is named in itself (English, Español), so anyone finds theirs.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.cluster import RadioButtons
from textual_vision.constants import Command
from textual_vision.label import Label

from divide import config, i18n
from divide.i18n import _
from divide.ui.dialogs import _Dialog, information


def choices() -> list[str]:
    """``auto`` and the languages divide has a catalogue for."""
    return ["auto", *i18n.available()]


def label(code: str) -> str:
    names = {"auto": _("~A~utomatic (the system's)")}
    name = names.get(code) or i18n.LANGUAGES.get(code, code)
    return name if "~" in name else f"~{name[0]}~{name[1:]}"


class LanguageDialog(_Dialog):
    """``chosen`` holds the code (``auto``, ``en``, ``es``...) once it ends with OK."""

    DEFAULT_CSS = """
    LanguageDialog { width: 50; }
    LanguageDialog RadioButtons { width: 1fr; margin-bottom: 1; }
    LanguageDialog .lang-note { color: $text-muted; background: $surface; height: auto; }
    """

    def __init__(self, current: str) -> None:
        super().__init__(title=_("Interface language"))
        self.codes = choices()
        self.radio = RadioButtons([label(c) for c in self.codes])
        self.radio.value = 1 << (self.codes.index(current) if current in self.codes else 0)  # one bit per button
        self.styles.height = len(self.codes) + 10
        self.chosen = current

    def compose_content(self) -> ComposeResult:
        yield Label(_("~L~anguage"), link=self.radio)
        yield self.radio
        yield Static(_("It applies from the next start. The help books stay in English."),
                     classes="lang-note", markup=False)
        with Horizontal(classes="dlg-buttons"):
            yield Button(_("O~K~"), Command.OK, is_default=True, id="ok")
            yield Button(_("Cancel"), Command.CANCEL, id="cancel")

    def valid(self, command: Command) -> bool:
        if command == Command.OK:
            self.chosen = self.codes[max(0, self.radio.value.bit_length() - 1)]
        return True


class LanguageMixin:
    """Options > Language (mixed into the Divide app)."""

    async def choose_language(self) -> None:
        current = config.load().get("language", "auto")
        dialog = LanguageDialog(current if current in choices() else "auto")
        if await self.run_dialog(dialog) != Command.OK or dialog.chosen == current:
            return
        config.set_value("language", dialog.chosen)
        await self.run_dialog(information(_("Interface language"), _("divide will speak the language chosen the next time it starts.")))
