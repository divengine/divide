"""Options > Colors: the colour theme, seen as it is chosen, and the colour depth.

Moving through the themes paints the whole IDE in them (the dialog too, and
the sample below the list); OK keeps the one chosen, also for the next start
(the config's ``palette``), Cancel goes back to the one there was.

The colour depth is what divide sends to the terminal: automatic (what the
terminal says it can: ``COLORTERM``, ``TERM``, the Windows console), or forced
to true colour, 256 or 16 colours, for a terminal that says less than it can
(over ssh or tmux ``COLORTERM`` is often lost). It applies from the next start.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.cluster import Cluster, RadioButtons
from textual_vision.constants import Command
from textual_vision.label import Label

from divide import config, themes
from divide.ui.dialogs import _Dialog
from divide.ui.windows import EditorView

SAMPLE = """{= title: "Colours" =}
<h1>{$title}</h1>  <!-- a comment -->
[$items]{?( $price > 10 )?}<b>{$name}</b>{/?}[/$items]
{% card.tpl %}  {$total:2.} 42"""

DETECTED = {"truecolor": "true colour", "256": "256 colours", "standard": "16 colours", "windows": "16 colours (Windows console)"}


def depth_setting() -> str:
    value = config.load().get("colors", "auto")
    return value if value in themes.DEPTHS else "auto"


class PickButtons(RadioButtons):
    """Radio buttons that choose as the cursor moves, as Turbo Vision's
    (TRadioButtons::movedTo): each theme is seen the moment it is reached."""

    def _move_sel(self, delta: int) -> None:
        super()._move_sel(delta)
        if 0 <= self.sel < len(self._items) and not self.value & (1 << self.sel):
            self.press(self.sel)
            self.post_message(Cluster.Changed(self.value))


class ColorsDialog(_Dialog):
    """The themes (each one previewed as it is chosen) and the colour depth."""

    DEFAULT_CSS = """
    ColorsDialog { width: 66; height: 23; }
    ColorsDialog Cluster { width: 1fr; margin-bottom: 1; }
    ColorsDialog .colors-about { color: $text-muted; background: $surface; height: 1; margin-bottom: 1; }
    ColorsDialog .colors-sample { width: 1fr; height: 4; margin-bottom: 1; scrollbar-size: 0 0; }
    ColorsDialog .dlg-hint { color: $text-muted; background: $surface; height: auto; }
    """

    def __init__(self, current: str, detected: str | None) -> None:
        super().__init__(title="Colors")
        self.names = list(themes.THEMES)
        self.original = current if current in self.names else themes.DEFAULT
        self.choice = self.original
        self.themes = PickButtons([p.label for p in themes.THEMES.values()])
        self.themes.value = 1 << self.names.index(self.original)
        self.themes.sel = self.names.index(self.original)
        self.depths = list(themes.DEPTHS)
        self.depth = depth_setting()
        self.depth_radio = RadioButtons(list(themes.DEPTH_LABELS.values()), columns=2)
        self.depth_radio.value = 1 << self.depths.index(self.depth)
        self.depth_radio.sel = self.depths.index(self.depth)
        self.about = Static(themes.get(self.original).description, classes="colors-about", markup=False)
        self.detected = detected

    def compose_content(self) -> ComposeResult:
        yield Label("~T~heme", link=self.themes)
        yield self.themes
        yield self.about
        sample = EditorView(SAMPLE, path=Path("sample.tpl"), read_only=True, classes="colors-sample")
        sample.can_focus = False
        yield sample
        yield Label("Colour ~d~epth (from the next start)", link=self.depth_radio)
        yield self.depth_radio
        shown = DETECTED.get(self.detected or "", "no colours")
        yield Static(f"This terminal gets {shown} now.", classes="dlg-hint", markup=False)
        with Horizontal(classes="dlg-buttons"):
            yield Button("O~K~", Command.OK, is_default=True, id="ok")
            yield Button("Cancel", Command.CANCEL, id="cancel")

    def _chosen(self, radio: RadioButtons, names: list[str]) -> str:
        return names[max(0, radio.value.bit_length() - 1)]

    def on_cluster_changed(self, message: Cluster.Changed) -> None:
        name = self._chosen(self.themes, self.names)
        if name != self.choice:
            self.choice = name
            self.about.update(themes.get(name).description)
            self.app.theme = name  # the preview: the whole IDE in the theme

    def valid(self, command: Command) -> bool:
        if command == Command.OK:
            self.choice = self._chosen(self.themes, self.names)
            self.depth = self._chosen(self.depth_radio, self.depths)
        elif self.app.theme != self.original:
            self.app.theme = self.original  # Cancel (or Esc): the theme there was
        return True


class ColorsMixin:
    """Options > Colors (mixed into the Divide app)."""

    async def choose_colors(self) -> None:
        dialog = ColorsDialog(self.theme, self.console.color_system)  # type: ignore[attr-defined]
        if await self.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            if self.theme != dialog.original:  # type: ignore[attr-defined]
                self.theme = dialog.original  # type: ignore[attr-defined]
            return
        self.theme = dialog.choice  # type: ignore[attr-defined]
        data = config.load()
        data["palette"], data["colors"] = dialog.choice, dialog.depth
        config.save(data)
