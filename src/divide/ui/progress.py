"""The box Turbo Pascal showed while compiling, for anything that takes a while.

``ProgressDialog`` lists what runs (``Template: index.tpl``), a clock and, at
the bottom, what to do: Esc stops the job while it runs; then the verdict
("Success", "Errors") and any key closes it. It also closes by itself after a
moment (a success sooner: a quick render only flashes it), since what came
out is behind it already (the output, the Messages window).

Under the rows, a bar in Norton Commander's style, in CP437 blocks: ``█`` and
``▓`` fill a track of ``░`` while the job says how far it is (``progress``);
a job that cannot say gets a block going back and forth over the track. A job
that ended fills the bar, whatever its verdict: the bar says how far the job
got, the verdict how it went; only a job stopped with Esc leaves it as it was.

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
from rich.text import Text
from textual.widgets import Static

from divide import themes
from divide.ui.dialogs import _Dialog
from divide.ui.shadow import install_shadows

T = TypeVar("T")

AUTO_CLOSE = 2.0  # seconds a success stays up
AUTO_CLOSE_PROBLEMS = 5.0  # errors or warnings: a little longer, to be read
TIME = "Time"
BLOCK = "▓██▓"  # what goes back and forth while the job cannot say how far it is


def bar_text(width: int, fraction: float | None = None, phase: int = 0, *,
             fill: str | None = None, track: str | None = None) -> Text:
    """A bar ``width`` cells wide: ``fraction`` (0-1) filled, half cells as ``▓``;
    None: ``BLOCK`` at step ``phase`` of its trip there and back. The colours
    are the palette's progress-fill and progress-track (blue and dark gray on
    the gray dialogs of the Borland palettes)."""
    palette = themes.current()
    fill = fill or palette.colour("progress-fill")
    track = track or palette.colour("progress-track")
    width = max(1, width)
    if fraction is None:
        block = BLOCK[:width]
        span = width - len(block)
        at = phase % (2 * span) if span > 0 else 0
        at = 2 * span - at if at > span else at
        return Text.assemble(("░" * at, track), (block, fill), ("░" * (width - at - len(block)), track))
    halves = round(max(0.0, min(1.0, fraction)) * width * 2)
    full, half = divmod(halves, 2)
    return Text.assemble(("█" * full + "▓" * half, fill), ("░" * (width - full - half), track))


class ProgressDialog(_Dialog):
    DEFAULT_CSS = """
    ProgressDialog > .tv-window-content { margin: 1 2 1 2; }  /* the last row is the frame's */
    ProgressDialog .progress-rows { color: $text; background: $surface; width: 1fr; height: auto; }
    ProgressDialog .progress-bar { background: $surface; width: 1fr; height: 1; margin-top: 1; }
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
        self.stopped = False  # by Esc: the bar stays where it was
        self.fraction: float | None = None  # how far the job is, when it can say
        self._phase = 0
        self._started = time.monotonic()
        self.styles.width = width
        self._fit()

    def _fit(self) -> None:
        self.styles.height = len(self.rows) + 8

    def compose_content(self) -> ComposeResult:
        yield Static(self._rows_text(), classes="progress-rows", markup=False)
        yield Static(self._bar(), classes="progress-bar", markup=False)
        yield Static(self.verdict, classes="progress-verdict", markup=False)

    def on_mount(self) -> None:
        self._clock = self.set_interval(0.1, self._tick)

    def _rows_text(self) -> str:
        pad = max(len(label) for label in self.rows) + 1
        room = self.width - pad - 8
        lines = []
        for label, value in self.rows.items():
            value = value if len(value) <= room else "..." + value[-(room - 3):]
            lines.append(f"{label + ':':>{pad}} {value}")
        return "\n".join(lines)

    def _bar(self) -> Text:
        """The bar, with the percentage when the job says how far it is."""
        shown = self.query(".progress-bar").first() if self.is_mounted else None
        width = shown.size.width if shown is not None and shown.size.width else self.width - 6  # inside frame and margins
        if self.running and self.fraction is None:
            return bar_text(width, None, self._phase)
        if not self.running and self.fraction is None:
            return bar_text(width, 0.0 if self.stopped else 1.0)  # ended: full, whatever the verdict
        fraction = self.fraction if self.running or self.stopped else 1.0
        bar = bar_text(width - 5, fraction)
        bar.append(f"{round(fraction * 100):4d}%", style=themes.current().colour("progress-text"))
        return bar

    def _show(self) -> None:
        if not self.is_mounted:
            return
        self.query_one(".progress-rows", Static).update(self._rows_text())
        self.query_one(".progress-bar", Static).update(self._bar())
        verdict = self.query_one(".progress-verdict", Static)
        verdict.update(self.verdict)
        verdict.set_class(not self.running and self.ok is True, "-done")
        verdict.set_class(not self.running and self.ok is False, "-failed")

    def _tick(self) -> None:
        if self.running:
            self._phase += 1
            self.rows[TIME] = f"{time.monotonic() - self._started:.1f} s"
            self._show()

    def progress(self, fraction: float | None) -> None:
        """How far the job is, 0 to 1 (None: it cannot say)."""
        self.fraction = None if fraction is None else max(0.0, min(1.0, fraction))
        self._show()

    def set(self, label: str, value: str) -> None:
        """Change (or add) one row."""
        grew = label not in self.rows
        self.rows[label] = value
        if grew:
            self._fit()
        self._show()

    def finish(self, verdict: str, ok: bool, rows: list[tuple[str, str]] | None = None, *, stopped: bool = False) -> None:
        """The job ended (or was ``stopped``): final rows and ``verdict`` ("Success"), then any key closes."""
        self.running = False
        self.ok = ok
        self.stopped = stopped
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
        dialog.finish("Stopped", False, stopped=True)
    else:
        word, ok, rows = verdict(result)
        dialog.finish(word, ok, rows)
        app.set_timer(AUTO_CLOSE if ok else AUTO_CLOSE_PROBLEMS, screen.close)
    return result
