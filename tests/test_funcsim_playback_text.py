"""The Mock Simulation playback window's text is written when it is made, from the trace (#33): the bar,
the panel and the result are there as soon as the window opens, before any refresh runs, so the window is
never shown, nor read, empty. Its first refresh is held back here, which is what a slow runner does by
chance: the test needs no timing and no PHP."""

from pathlib import Path

from divide.run import functrace as ftr

FUNCTION = "<?php\nreturn function (array &$context): string {\n    return 'pending';\n};\n"


def _trace(status: str = "returned", lines: bool = True) -> ftr.FunctionTrace:
    events = [{"seq": 1, "type": "line", "line": 3, "depth": 0}] if lines else []
    return ftr.parse_trace({
        "protocol": "divide.function-trace", "version": 1, "scenario": {},
        "function": {"name": "checkout", "file": "functions/checkout.php"},
        "result": {"status": status, "return": "pending", "return_type": "string", "stdout": "sent: no\n"},
        "events": events, "truncated": False})


def _app(tmp_path: Path):
    from divide.app import Divide
    (tmp_path / "functions").mkdir()
    (tmp_path / "functions" / "checkout.php").write_text(FUNCTION, encoding="utf-8")
    return Divide(tmp_path, [])


def _held(monkeypatch) -> list:
    """The window's call_after_refresh callbacks, kept and never run: its first refresh never comes."""
    from divide.ui.funcsim import FunctionPlaybackWindow
    held: list = []
    monkeypatch.setattr(FunctionPlaybackWindow, "call_after_refresh", lambda self, callback, *a, **k: held.append(callback))
    return held


async def test_the_text_is_there_before_the_first_refresh(tmp_path, monkeypatch):
    app = _app(tmp_path)
    async with app.run_test(size=(120, 34)) as pilot:
        await pilot.pause(0.2)
        held = _held(monkeypatch)
        win = app.open_function_playback(tmp_path, _trace(lines=False), {}, traced=False)
        # made, not yet refreshed: the text is the trace's already
        assert "MOCK SIMULATION" in str(win.bar.render())
        assert "Run without the line trace" in str(win.info.render())
        assert "pending" in str(win.verdict.render())
        await pilot.pause(0.2)
        assert held, "the refresh was expected to be held back"
        assert app.active_window() is win
        assert "Run without the line trace" in str(win.info.render()) and "pending" in str(win.verdict.render())


async def test_a_traced_run_names_its_first_line_before_the_first_refresh(tmp_path, monkeypatch):
    app = _app(tmp_path)
    async with app.run_test(size=(120, 34)) as pilot:
        await pilot.pause(0.2)
        _held(monkeypatch)
        win = app.open_function_playback(tmp_path, _trace(), {})
        assert "line 3" in str(win.bar.render()) and "event 1/1" in str(win.bar.render())
        assert "pending" in str(win.verdict.render())


async def test_a_refresh_keeps_that_text_and_lays_it_out_for_the_width(tmp_path):
    """Made before its width is known, the window writes the wide layout; once laid out narrow, its
    refresh puts the result first in the panel, and changes nothing else."""
    app = _app(tmp_path)
    async with app.run_test(size=(120, 34)) as pilot:
        await pilot.pause(0.2)
        win = app.open_function_playback(tmp_path, _trace(lines=False), {}, traced=False)
        before = (str(win.bar.render()), str(win.info.render()), str(win.verdict.render()))
        for _ in range(40):
            await pilot.pause(0.05)
            if win.is_mounted:
                break
        win.refresh_view()
        bar, info, verdict = str(win.bar.render()), str(win.info.render()), str(win.verdict.render())
        assert (bar, verdict) == (before[0], before[2])
        assert info == (verdict + before[1] if win.has_class("narrow") else before[1])
