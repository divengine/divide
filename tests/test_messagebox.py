"""MessageBox ends on its own buttons' commands (#23): OK, Cancel, Yes and No as before, and a command of
its own beyond them (the replace prompt's All, the Mock Simulation's Keep null) too, through valid(); a
command that is not one of its buttons is left alone."""

from pathlib import Path

from textual_vision.constants import Command
from textual_vision.events import CommandMessage

from divide.ui.dialogs import CM_CHANGE_ALL, MessageBox, replace_prompt

CM_MINE = Command.USER + 900
CM_FOREIGN = Command.USER + 901


def _app(tmp_path: Path):
    from divide.app import Divide
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    return Divide(tmp_path, [tmp_path / "a.txt"])


async def _ask(app, pilot, box):
    """The box run as a dialog; the result is read from the returned dict once it ends."""
    out: dict = {}

    async def go() -> None:
        out["result"] = await app.run_dialog(box)

    app.run_worker(go())
    for _ in range(100):
        await pilot.pause(0.05)
        if getattr(app.screen, "dialog", None) is box:
            break
    return out


async def _ended(pilot, out) -> bool:
    for _ in range(40):
        await pilot.pause(0.05)
        if "result" in out:
            return True
    return False


def _box(buttons):
    return MessageBox("Box", "Text", buttons, width=50)


async def test_its_own_command_ends_it_with_that_command(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        out = await _ask(app, pilot, _box([("~K~eep", CM_MINE, "keep"), ("Cancel", Command.CANCEL, "cancel")]))
        await pilot.press("k")  # its hotkey
        assert await _ended(pilot, out) and out["result"] == CM_MINE

        out = await _ask(app, pilot, _box([("~K~eep", CM_MINE, "keep"), ("Cancel", Command.CANCEL, "cancel")]))
        await pilot.press("enter")  # the default button
        assert await _ended(pilot, out) and out["result"] == CM_MINE


async def test_ok_cancel_yes_and_no_end_it_as_before(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        buttons = [("~Y~es", Command.YES, "yes"), ("~N~o", Command.NO, "no"), ("Cancel", Command.CANCEL, "cancel")]
        for key, expected in (("y", Command.YES), ("n", Command.NO), ("escape", Command.CANCEL)):
            out = await _ask(app, pilot, _box(buttons))
            await pilot.press(key)
            assert await _ended(pilot, out) and out["result"] == expected, key
        out = await _ask(app, pilot, _box([("O~K~", Command.OK, "ok")]))
        await pilot.press("enter")
        assert await _ended(pilot, out) and out["result"] == Command.OK


async def test_a_command_not_among_its_buttons_does_not_end_it(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        box = _box([("~K~eep", CM_MINE, "keep"), ("Cancel", Command.CANCEL, "cancel")])
        out = await _ask(app, pilot, box)
        box.post_message(CommandMessage(CM_FOREIGN))
        assert not await _ended(pilot, out)
        assert getattr(app.screen, "dialog", None) is box
        await pilot.press("escape")
        assert await _ended(pilot, out) and out["result"] == Command.CANCEL


async def test_its_own_command_still_goes_through_valid(tmp_path):
    class Refusing(MessageBox):
        allow = False

        def valid(self, command):
            return command != CM_MINE or self.allow

    app = _app(tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        box = Refusing("Box", "Text", [("~K~eep", CM_MINE, "keep"), ("Cancel", Command.CANCEL, "cancel")])
        out = await _ask(app, pilot, box)
        await pilot.press("k")
        assert not await _ended(pilot, out)  # refused: it stays open
        box.allow = True
        await pilot.press("k")
        assert await _ended(pilot, out) and out["result"] == CM_MINE


async def test_the_replace_prompts_all_ends_it_with_change_all(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        out = await _ask(app, pilot, replace_prompt())
        await pilot.press("a")
        assert await _ended(pilot, out) and out["result"] == CM_CHANGE_ALL
