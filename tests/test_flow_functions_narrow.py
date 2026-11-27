"""The Functions window's narrow layout follows its own width once it is filled (#33), whether its Resize
event comes before or after that: here the Resize never comes, so the test needs no timing. The window
is filled from examples/generator's files alone; nothing runs."""

import shutil
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "generator"
FLOW = "flows/generate_php_dto.yml"


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "generator"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build", "vendor", ".div", "composer.lock"))
    return root.resolve()


def _no_resize(monkeypatch) -> list:
    """Resize events the window gets, recorded and never handled."""
    from divide.ui.flowfunctions import FunctionsWindow
    seen: list = []
    monkeypatch.setattr(FunctionsWindow, "on_resize", lambda self, event: seen.append(event.size.width))
    return seen


async def _filled(app, pilot):
    from divide.app import CM_FLOW_FUNCTIONS
    from divide.ui.flowfunctions import FunctionsWindow
    await pilot.pause(0.3)
    app.run_command(CM_FLOW_FUNCTIONS)
    for _ in range(300):
        await pilot.pause(0.05)
        win = app.active_window()
        if isinstance(win, FunctionsWindow) and win.catalog is not None:
            return win
    pytest.fail("the Functions window was never filled")


@pytest.mark.parametrize("size, narrow", [((80, 25), True), ((160, 40), False)])
async def test_the_layout_follows_the_width_once_filled_without_a_resize(project, monkeypatch, size, narrow):
    from divide.app import Divide
    _no_resize(monkeypatch)
    app = Divide(project, [project / FLOW])
    async with app.run_test(size=size) as pilot:
        win = await _filled(app, pilot)
        assert win.size.width, "filled before it was laid out"
        assert (win.size.width < 100) is narrow
        assert win.has_class("narrow") is narrow


async def test_a_resize_still_changes_the_layout(project):
    from divide.app import Divide
    app = Divide(project, [project / FLOW])
    async with app.run_test(size=(160, 40)) as pilot:
        win = await _filled(app, pilot)
        assert not win.has_class("narrow")
        await pilot.resize_terminal(80, 25)
        for _ in range(100):
            await pilot.pause(0.05)
            if win.has_class("narrow"):
                break
        assert win.has_class("narrow") and win.size.width < 100
