"""The progress box's bar, in Norton Commander's style, and the indexing bar."""

import asyncio

from divide.app import Divide
from divide.ui.progress import BLOCK, ProgressDialog, ProgressScreen, bar_text, run_with_progress


def test_bar_text():
    assert bar_text(10, 0).plain == "░" * 10
    assert bar_text(10, 0.05).plain == "▓" + "░" * 9  # half a cell
    assert bar_text(10, 0.5).plain == "█" * 5 + "░" * 5
    assert bar_text(10, 1).plain == "█" * 10
    trip = [bar_text(10, None, phase).plain for phase in range(13)]
    assert trip[0] == BLOCK + "░" * 6 and trip[6] == "░" * 6 + BLOCK and trip[12] == trip[0]  # there and back
    assert all(len(t) == 10 and BLOCK in t for t in trip)
    assert set("".join(trip) + bar_text(7, 0.3).plain) <= set("█▓░")  # CP437 blocks


async def test_the_box_shows_how_far_the_job_is(tmp_path):
    app = Divide(tmp_path, [])
    async with app.run_test(size=(100, 30)) as pilot:
        for _ in range(4):
            await pilot.pause()
        dialog = ProgressDialog("Working", [("Files", "3")], width=52)
        step = asyncio.Event()
        result: list[int] = []

        async def job() -> int:
            await step.wait()
            return 3

        def run() -> None:
            async def go():
                result.append(await run_with_progress(app, dialog, job(), lambda r: ("Success", False, [])))
            app.run_worker(go())

        run()
        await pilot.pause(0.3)
        assert isinstance(app.screen, ProgressScreen)
        bar = dialog._bar().plain
        assert len(bar) == dialog.query_one(".progress-bar").size.width and BLOCK in bar  # it cannot say: the block goes back and forth
        dialog.progress(0.5)
        half = dialog._bar().plain
        assert half.endswith("  50%") and len(half) == len(bar) and half.count("█") * 2 + half.count("▓") == len(bar) - 5
        step.set()
        await pilot.pause(0.2)
        assert result == [3] and dialog._bar().plain == half  # kept: not a success


async def test_indexing_bar_in_the_status_line(tmp_path):
    app = Divide(tmp_path, [])
    async with app.run_test(size=(100, 30)) as pilot:
        for _ in range(4):
            await pilot.pause()
        app._lsp_progress_changed("phpactor", "t1", "Indexing", None)
        assert app.status_line._hint_text.endswith("phpactor: Indexing...")
        app._lsp_progress_changed("phpactor", "t1", "Indexing", 42)
        assert app.status_line._hint_text.endswith("phpactor: Indexing ████░░░░░░ 42%")
        app._lsp_progress_changed("phpactor", "t1", None, None)
        assert not app.lsp_working and "Indexing" not in app.status_line._hint_text
