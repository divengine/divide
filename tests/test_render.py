"""Rendering through PHP + Div.

Needs ``php`` and a Div engine: set DIVIDE_DIV_PHP to a composer
``vendor/autoload.php`` (with divengine/div) or to a Div checkout's
``src/div.php`` (with its vendor/ installed). Skipped otherwise.
"""

import os
import shutil
from pathlib import Path

import pytest

from divide.app import Divide
from divide.run.render import ENV_ENGINE, IncludeTarget, check_data, find_engine, render, resolve_includes
from divide.ui.dialogs import DialogScreen, MessageBox
from divide.ui.windows import EditorWindow, MessagesWindow, OutputWindow

ENGINE = os.environ.get(ENV_ENGINE)
needs_div = pytest.mark.skipif(
    not (shutil.which("php") and ENGINE and Path(ENGINE).is_file()),
    reason=f"needs php and {ENV_ENGINE} pointing to Div",
)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


def make_project(tmp_path: Path) -> Path:
    (tmp_path / "parts").mkdir()
    (tmp_path / "parts" / "greet.tpl").write_text("Hi {$name}!")
    page = tmp_path / "page.tpl"
    page.write_text("{% parts/greet %}|[$items]<{$value}>[/$items]")
    (tmp_path / "page.json").write_text('// data for page.tpl\n{"name": "Rafa", "items": [1, 2]}\n')
    return page


def test_find_engine_in_vendor(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_ENGINE, raising=False)
    (tmp_path / "vendor" / "divengine" / "div").mkdir(parents=True)
    (tmp_path / "vendor" / "autoload.php").write_text("<?php")
    sub = tmp_path / "templates" / "x"
    sub.mkdir(parents=True)
    assert find_engine([sub]) == (tmp_path / "vendor" / "autoload.php").resolve()
    assert find_engine([tmp_path / "templates"], configured=str(tmp_path / "nope.php")) is not None
    monkeypatch.setenv(ENV_ENGINE, str(tmp_path / "vendor" / "autoload.php"))
    assert find_engine([Path("/")]) is not None


def test_check_data():
    assert check_data('{"a": 1, b: \'x\', // note\n "u": "http://x"}') is None
    assert "not valid JSON" in check_data('{"a": 1')
    assert "object" in check_data("3")


@needs_div
async def test_render_bridge(tmp_path):
    page = make_project(tmp_path)
    result = await render(Path(ENGINE), page, page.read_text(), (tmp_path / "page.json").read_text(), cwd=tmp_path)
    assert result.output == "Hi Rafa!|<1><2>"
    assert not result.fatal and result.version


@needs_div
async def test_render_bridge_reports_bad_data(tmp_path):
    page = make_project(tmp_path)
    result = await render(Path(ENGINE), page, "{$name}", '{"name": ', cwd=tmp_path)
    assert [m.level for m in result.serious] == ["DATA"]
    assert result.output == "{$name}"


async def settle(pilot, n=4):
    for _ in range(n):
        await pilot.pause()


async def wait_output(pilot, app, text, tries=40):
    for _ in range(tries):
        out = app.output_window()
        if out is not None and out.view.text == text:
            return out
        await pilot.pause(0.05)
    raise AssertionError(f"output never became {text!r}: {out.view.text if out else None!r}")


@needs_div
async def test_run_render_window_and_unsaved_changes(tmp_path):
    page = make_project(tmp_path)
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+f9")
        out = await wait_output(pilot, app, "Hi Rafa!|<1><2>")
        assert isinstance(out, OutputWindow) and app.messages_window() is None
        assert "page.json" in out.summary
        # unsaved template edits are rendered
        win = app.window_for(page.resolve())
        win.editor.move_cursor((0, 0))
        app.raise_window(win)
        await settle(pilot)
        await pilot.press("X", "ctrl+f9")
        await wait_output(pilot, app, "XHi Rafa!|<1><2>")
        assert page.read_text().startswith("{%")


@needs_div
async def test_edit_data_save_rerenders_and_reports(tmp_path):
    page = make_project(tmp_path)
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+f9")
        await wait_output(pilot, app, "Hi Rafa!|<1><2>")
        app.raise_window(app.window_for(page.resolve()))
        await settle(pilot)
        await pilot.press("alt+r", "e")  # Run > Edit data
        await settle(pilot)
        data = app.active_editor()
        assert data.path == (tmp_path / "page.json").resolve()
        data.editor.load_text('{"name": "Div", "items": []}')
        await pilot.press("f2")  # saving the data re-renders
        await wait_output(pilot, app, "Hi Div!|")
        data.editor.load_text('{"name": ')
        await pilot.press("f2")
        for _ in range(40):
            if app.messages_window() is not None:
                break
            await pilot.pause(0.05)
        messages = app.messages_window()
        assert isinstance(messages, MessagesWindow)
        assert any(line.startswith("DATA:") for line in messages.list.items)


async def test_render_without_engine_explains(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_ENGINE, str(tmp_path / "missing.php"))
    page = tmp_path / "a.tpl"
    page.write_text("{$x}")
    app = Divide(tmp_path, [page])
    async with app.run_test() as pilot:
        await settle(pilot)
        await pilot.press("ctrl+f9")
        await settle(pilot)
        assert isinstance(app.screen, DialogScreen) and isinstance(app.screen.dialog, MessageBox)
        assert "Div was not found" in app.screen.dialog._text


async def test_data_file_choice_is_used(tmp_path):
    page = tmp_path / "a.tpl"
    page.write_text("{$x}")
    other = tmp_path / "other.json"
    other.write_text("{}")
    app = Divide(tmp_path, [page])
    async with app.run_test() as pilot:
        await settle(pilot)
        assert app.data_file_for(page.resolve()) == (tmp_path / "a.json").resolve()
        app.data_files[page.resolve()] = other.resolve()
        assert app.template_for_data(other.resolve()) == page.resolve()
        assert isinstance(app.query_one(EditorWindow), EditorWindow)


def site(tmp_path: Path) -> Path:
    """examples/showcase.tpl including components/card relative to itself, project root above."""
    (tmp_path / "examples" / "components").mkdir(parents=True)
    (tmp_path / "examples" / "components" / "card.tpl").write_text("<card/>")
    page = tmp_path / "examples" / "showcase.tpl"
    page.write_text("{% layout %}\n{%% components/card %%}\n")
    return page


@needs_div
async def test_div_resolves_includes_relative_to_the_template(tmp_path):
    page = site(tmp_path)
    got = await resolve_includes(Path(ENGINE), page, ["components/card", "layout", "components/card:{}"], cwd=tmp_path)
    card = (tmp_path / "examples" / "components" / "card.tpl").resolve()
    assert got["components/card"].file == card
    assert got["layout"].file is None
    assert got["components/card:{}"] == IncludeTarget("components/card", card)  # data part dropped, as Div does


@needs_div
async def test_include_warnings_and_goto_include(tmp_path):
    page = site(tmp_path)
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(120, 40)) as pilot:
        win = app.window_for(page.resolve())
        for _ in range(60):
            if win.editor.include_targets:
                break
            await pilot.pause(0.05)
        assert [d.message for d in win.editor.diagnostics] == ["Div cannot find the template layout"]

        win.editor.move_cursor((1, 6))  # on components/card
        await pilot.press("ctrl+j")  # Ctrl+Enter as most terminals send it
        for _ in range(60):
            if app.active_editor() is not win:
                break
            await pilot.pause(0.05)
        assert app.active_editor().path == (tmp_path / "examples" / "components" / "card.tpl").resolve()

        app.raise_window(win)
        win.editor.move_cursor((0, 4))  # on layout: Div cannot find it, offer to create it
        await pilot.press("ctrl+j")
        for _ in range(60):
            if isinstance(app.screen, DialogScreen):
                break
            await pilot.pause(0.05)
        assert "Div cannot find layout" in app.screen.dialog._text
        await pilot.press("y")
        for _ in range(60):
            if not win.editor.diagnostics:
                break
            await pilot.pause(0.05)
        assert (tmp_path / "examples" / "layout.tpl").is_file()
        assert app.active_editor().path == (tmp_path / "examples" / "layout.tpl").resolve()
        assert win.editor.diagnostics == []  # Div finds it now
