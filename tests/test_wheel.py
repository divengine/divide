"""The mouse wheel on the Turbo Vision lists (they draw their own rows): File > Open's files."""

from textual import events
from textual_vision.constants import Command

from divide.app import Divide
from divide.ui.dialogs import DialogScreen, FileDialog


async def until(pilot, pred, tries=200):
    for _ in range(tries):
        if pred():
            return
        await pilot.pause(0.02)
    raise AssertionError("timed out")


def wheel(app, widget, down: bool = True) -> None:
    x, y = widget.region.x + 2, widget.region.y + 2
    kind = events.MouseScrollDown if down else events.MouseScrollUp
    app.post_message(kind(None, x, y, 0, 0, 0, False, False, False, screen_x=x, screen_y=y))


async def test_the_wheel_moves_the_bar_of_the_file_list(tmp_path):
    for i in range(40):
        (tmp_path / f"page{i:02}.tpl").write_text("x", encoding="utf-8")
    app = Divide(tmp_path, [])
    async with app.run_test(size=(100, 30)) as pilot:
        app.run_command(Command.OPEN)
        await until(pilot, lambda: isinstance(app.screen, DialogScreen) and isinstance(app.screen.dialog, FileDialog))
        files = app.screen.dialog.list
        await until(pilot, lambda: files.range > 30)
        start = files.focused
        wheel(app, files)
        await until(pilot, lambda: files.focused == start + 3)
        wheel(app, files)
        await until(pilot, lambda: files.focused == start + 6)
        assert files.top_item <= files.focused < files.top_item + files.size.height  # the bar stays in sight
        wheel(app, files, down=False)
        await until(pilot, lambda: files.focused == start + 3)
