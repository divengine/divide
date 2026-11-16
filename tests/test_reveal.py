"""A jump selects its target with the line in the middle, but scrolls sideways only as far
as needed: the start of a line that fits in the window stays in view."""

import pytest

from divide.app import Divide


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


async def settle(pilot, n=10):
    for _ in range(n):
        await pilot.pause()


LINES = [f"line {n}" for n in range(200)]
LINES[150] = " " * 20 + "[$products] product =>"
LINES[170] = "x" * 300 + "[$far]"


async def test_jump_keeps_a_line_that_fits_from_its_start(tmp_path):
    page = tmp_path / "page.tpl"
    page.write_text("\n".join(LINES) + "\n")
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(60, 30)) as pilot:
        await settle(pilot)
        win = app.window_for(page)
        ed = win.editor
        start = ed.text.index("[$products]")
        app._select_in(win, start, start + len("[$products] product =>"))
        await settle(pilot)
        assert ed.scroll_x == 0
        height = ed.scrollable_content_region.height
        assert ed.scroll_y < 150 < ed.scroll_y + height
        assert abs((150 - ed.scroll_y) - height // 2) <= 1  # the line in the middle

        far = ed.text.index("[$far]")
        app._select_in(win, far, far + len("[$far]"))
        await settle(pilot)
        width = ed.scrollable_content_region.width - ed.gutter_width
        assert ed.scroll_x < 300 + 6 <= ed.scroll_x + width  # still sideways when it must
