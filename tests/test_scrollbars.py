"""Turbo Vision's standard scroll bars, on the window's border."""

from divide.app import Divide
from divide.ui.outline import OutlineWindow
from divide.ui.windows import EditorWindow

import pytest

LONG = "".join(f"line {n} " + "x" * (n % 7) * 30 + "\n" for n in range(200))


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


async def settle(pilot, times: int = 6) -> None:
    for _ in range(times):
        await pilot.pause()


def screen_lines(app) -> list[str]:
    return [strip.text for strip in app.screen._compositor.render_strips()]


def editor_of(app) -> EditorWindow:
    return next(w for w in app.windows() if isinstance(w, EditorWindow))


async def test_bars_on_the_border(tmp_path):
    path = tmp_path / "long.txt"
    path.write_text(LONG)
    app = Divide(tmp_path, [path])
    async with app.run_test(size=(80, 24)) as pilot:
        await settle(pilot)
        window = editor_of(app)
        wr = window.region
        editor = window.editor
        # the view's own bars are gone: the text reaches the border
        assert editor.styles.scrollbar_size_vertical == 0 and editor.styles.scrollbar_size_horizontal == 0
        assert editor.region.right == wr.right - 1 and editor.region.bottom == wr.bottom - 1
        lines = screen_lines(app)
        right = [line[wr.right - 1] for line in lines[wr.y + 1:wr.bottom - 1]]
        assert right[0] == "▲" and right[-1] == "▼" and right[1] == "■" and set(right[2:-1]) == {"▒"}
        bottom = lines[wr.bottom - 1]
        assert bottom[wr.x + 18] == "◄" and bottom[wr.right - 3] == "►" and bottom[wr.right - 2:wr.right] == "─┘"
        assert "1:1" in bottom[:18]  # the indicator keeps its place

        # ▼ a line, the track a page, ◄ ► a column; the focus stays in the text
        await pilot.click(offset=(wr.right - 1, wr.bottom - 2))
        await settle(pilot, 3)
        assert editor.scroll_y == 1 and app.focused is editor
        await pilot.click(offset=(wr.right - 1, wr.y + 10))
        await settle(pilot, 3)
        assert editor.scroll_y == 1 + editor.scrollable_content_region.height
        await pilot.click(offset=(wr.right - 3, wr.bottom - 1))
        await settle(pilot, 3)
        assert editor.scroll_x == 1
        assert editor.cursor_location == (0, 0)  # scrolling does not move the cursor

        # the ■ follows the view
        editor.scroll_to(y=editor.max_scroll_y, animate=False)
        await settle(pilot, 3)
        right = [line[wr.right - 1] for line in screen_lines(app)[wr.y + 1:wr.bottom - 1]]
        assert right[-2] == "■"


async def test_only_the_active_window_shows_them(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text(LONG)
    b.write_text("short\n")
    app = Divide(tmp_path, [a, b])
    async with app.run_test(size=(80, 24)) as pilot:
        await settle(pilot)
        first, second = [w for w in app.windows() if isinstance(w, EditorWindow)]
        app.raise_window(first)
        await settle(pilot)
        assert first.v_bar.display and first.h_bar.display
        assert not second.v_bar.display  # nothing to scroll
        app.raise_window(second)
        await settle(pilot)
        assert not first.v_bar.display and not first.h_bar.display


async def test_a_list_drives_its_bar(tmp_path):
    path = tmp_path / "a.php"
    path.write_text("<?php\n" + "".join(f"function f{n}() {{}}\n" for n in range(60)))
    app = Divide(tmp_path, [path])
    async with app.run_test(size=(80, 24)) as pilot:
        await settle(pilot)
        app.show_outline()
        await settle(pilot)
        window = next(w for w in app.windows() if isinstance(w, OutlineWindow))
        bar = window.v_bar
        assert bar.display and bar.max_val == len(window.symbols) - 1
        wr = window.region
        await pilot.click(offset=(wr.right - 1, wr.bottom - 2))
        await settle(pilot, 3)
        assert window.list.focused == 1 == bar.value
