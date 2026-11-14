"""The box Turbo Pascal showed while compiling, for anything that takes a while.

``ProgressDialog`` lists what runs (``Template: index.tpl``), a clock and, at
the bottom, what to do: Esc stops the job while it runs; then the verdict
("Success", "Errors") waits for any key. A success also closes by itself after
a moment, so a quick render only flashes it.

``run_with_progress`` runs a coroutine under the box and returns its result
(None when the user stopped it) as soon as it ends: the caller shows what
came out behind the box, which stays up with its verdict.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from textual import events
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static

from divide.ui.dialogs import _Dialog
from divide.ui.shadow import install_shadows

T = TypeVar("T")

AUTO_CLOSE = 2.0  # seconds a success stays up
TIME = "Time"


class ProgressDialog(_Dialog):
    DEFAULT_CSS = """
    ProgressDialog > .tv-window-content { margin: 1 2 0 2; }
    ProgressDialog .progress-rows { color: $text; background: $surface; width: 1fr; height: auto; }
    ProgressDialog .progress-verdict { color: $text; background: $surface; width: 1fr; height: 1; margin-top: 1;
                                       text-align: center; }
    ProgressDialog .progress-verdict.-done { color: $foreground; background: $background; text-style: bold; }
    ProgressDialog .progress-verdict.-failed { color: $error; text-style: bold; }
    """

    def __init__(self, title: str, rows: list[tuple[str, str]], *, width: int = 52, stoppable: bool = True) -> None:
        super().__init__(title=title)
        self.rows: dict[str, str] = dict(rows)
        self.rows.setdefault(TIME, "0.0 s")
        self.width = width
        self.stoppable = stoppable
        self.running = True
        self.verdict = "Press Esc to stop" if stoppable else "Working..."
        self.ok: bool | None = None
        self._started = time.monotonic()
        self.styles.width = width
        self._fit()

    def _fit(self) -> None:
        self.styles.height = len(self.rows) + 6

    def compose_content(self) -> ComposeResult:
        yield Static(self._rows_text(), classes="progress-rows", markup=False)
        yield Static(self.verdict, classes="progress-verdict", markup=False)

    def on_mount(self) -> None:
        self._clock = self.set_interval(0.1, self._tick)

    def _rows_text(self) -> str:
        pad = max(len(label) for label in self.rows) + 1
        room = self.width - pad - 8
        lines = []
        for label, value in self.rows.items():
            value = value if len(value) <= room else "…" + value[-(room - 1):]
            lines.append(f"{label + ':':>{pad}} {value}")
        return "\n".join(lines)

    def _show(self) -> None:
        if not self.is_mounted:
            return
        self.query_one(".progress-rows", Static).update(self._rows_text())
        verdict = self.query_one(".progress-verdict", Static)
        verdict.update(self.verdict)
        verdict.set_class(not self.running and self.ok is True, "-done")
        verdict.set_class(not self.running and self.ok is False, "-failed")

    def _tick(self) -> None:
        if self.running:
            self.rows[TIME] = f"{time.monotonic() - self._started:.1f} s"
            self._show()

    def set(self, label: str, value: str) -> None:
        """Change (or add) one row."""
        grew = label not in self.rows
        self.rows[label] = value
        if grew:
            self._fit()
        self._show()

    def finish(self, verdict: str, ok: bool, rows: list[tuple[str, str]] | None = None) -> None:
        """The job ended: final rows and ``verdict`` ("Success"), then any key closes."""
        self.running = False
        self.ok = ok
        self.rows[TIME] = f"{time.monotonic() - self._started:.2f} s"
        for label, value in rows or []:
            self.rows[label] = value
        self._fit()
        self.verdict = f"{verdict}: press any key"
        self._show()


class ProgressScreen(ModalScreen[None]):
    """The dialog over the desktop: Esc stops the job, then any key (or click) closes."""

    DEFAULT_CSS = """
    ProgressScreen { align: center middle; background: transparent; layers: windows; }
    """

    def __init__(self, dialog: ProgressDialog, stop: Callable[[], None]) -> None:
        super().__init__()
        install_shadows(self)
        self.dialog = dialog
        self._stop = stop

    def compose(self) -> ComposeResult:
        yield self.dialog

    def close(self) -> None:
        if self.is_current:
            self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        if self.dialog.running:
            if event.key == "escape" and self.dialog.stoppable:
                self.dialog.verdict = "Stopping..."
                self.dialog._show()
                self._stop()
        else:
            self.close()

    def on_click(self, event: events.Click) -> None:
        event.stop()
        if not self.dialog.running:
            self.close()


async def run_with_progress(
    app,
    dialog: ProgressDialog,
    job: Awaitable[T],
    verdict: Callable[[T], tuple[str, bool, list[tuple[str, str]]]],
) -> T | None:
    """Show ``dialog`` while ``job`` runs; ``verdict(result)`` gives (word, ok, final rows).

    Exceptions of the job close the box and propagate. Call from a worker."""

    task: asyncio.Future[T] = asyncio.ensure_future(job)
    screen = ProgressScreen(dialog, stop=task.cancel)
    app.push_screen(screen)
    try:
        result: T | None = await task
    except asyncio.CancelledError:
        if not task.cancelled():
            raise  # our own worker is being cancelled
        result = None
    except BaseException:
        screen.close()
        raise
    if result is None:
        dialog.finish("Stopped", False)
    else:
        word, ok, rows = verdict(result)
        dialog.finish(word, ok, rows)
        if ok:
            app.set_timer(AUTO_CLOSE, screen.close)
    return result
