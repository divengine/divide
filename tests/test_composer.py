"""Tools > Composer packages: the project's packages, composer run for them, the assistants.

Composer is a fake here (``$DIVIDE_COMPOSER``): it writes down what it was asked,
answers as composer would and changes composer.json as ``require`` / ``remove``
would. Nothing goes to the network.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from textual_vision.constants import Command

from divide.app import Divide
from divide.run import composer as cmp
from divide.ui.composer import AddPackageDialog, ComposerLogWindow, ComposerWindow, NewComposerDialog
from divide.ui.dialogs import DialogScreen
from divide.ui.progress import ProgressScreen

FAKE = r'''#!PYTHON
import json, sys, time
from pathlib import Path
args = [a for a in sys.argv[1:] if a not in ("--no-ansi", "--no-interaction")]
with open(LOG, "a") as log:
    log.write(json.dumps(args) + "\n")
file = Path("composer.json")
if args[0] == "search":
    print(json.dumps([{"name": "acme/tables", "description": "Tables for Div", "url": "https://x"},
                      {"name": "acme/forms", "description": "Forms", "url": "https://y"}]))
elif args[0] == "show":
    print(json.dumps({"name": args[2], "versions": ["dev-main", "2.1.0", "2.0.3", "1.9.0"]}))
elif args[0] == "outdated":
    print(json.dumps({"installed": [{"name": "divengine/div", "version": "6.1.3", "latest": "7.0.0"}]}))
elif args[0] in ("require", "remove"):
    data = json.loads(file.read_text())
    dev = "--dev" in args
    section = "require-dev" if dev else "require"
    for spec in [a for a in args[1:] if not a.startswith("--")]:
        name, _, constraint = spec.partition(":")
        if args[0] == "require":
            data.setdefault(section, {})[name] = constraint or "*"
        else:
            data.get(section, {}).pop(name, None)
    file.write_text(json.dumps(data, indent=4))
    print("Loading composer repositories with package information")
    print("Writing lock file")
elif args[0] == "install":
    print("Installing dependencies from lock file")
    print("Generating autoload files")
elif args[0] == "validate":
    print("./composer.json is invalid, the following errors/warnings were found:")
    sys.exit(2)
elif args[0] == "slow":
    print("working", flush=True)
    time.sleep(30)
'''


@pytest.fixture
def fake(tmp_path, monkeypatch):
    log = tmp_path / "composer-calls.log"
    script = tmp_path / "bin" / "composer"
    script.parent.mkdir()
    script.write_text(FAKE.replace("PYTHON", sys.executable).replace("LOG", repr(str(log))))
    script.chmod(0o755)
    monkeypatch.setenv(cmp.ENV, str(script))
    return log


def calls(log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


SHOP = Path(__file__).resolve().parent.parent / "examples" / "shop"


async def settle(pilot, n=10):
    for _ in range(n):
        await pilot.pause()


async def until(pilot, check, tries=200):
    for _ in range(tries):
        if check():
            return
        await pilot.pause(0.05)
    raise AssertionError("timed out")


async def close_progress(pilot, app):
    """Until composer's job is over; its box closes by itself when it went well, a key closes it else."""
    await settle(pilot, 4)
    await until(pilot, lambda: all(w.is_finished for w in app.workers if w.group == "composer")
                or (isinstance(app.screen, ProgressScreen) and not app.screen.dialog.running))
    if isinstance(app.screen, ProgressScreen):
        await until(pilot, lambda: not app.screen.dialog.running)
        await pilot.press("escape")
    await until(pilot, lambda: all(w.is_finished for w in app.workers if w.group == "composer"))
    await settle(pilot)


# ------------------------------------------------------------------ reading
def test_the_packages_of_a_project(tmp_path):
    (tmp_path / "composer.json").write_text(json.dumps({
        "name": "acme/shop", "require": {"php": ">=8.0", "divengine/div": "^6.1", "ext-mbstring": "*"},
        "require-dev": {"phpunit/phpunit": "^10"}}))
    (tmp_path / "composer.lock").write_text((SHOP / "composer.lock").read_text())
    project = cmp.read(tmp_path)
    names = [(p.name, p.kind) for p in project.packages]
    assert names[0] == ("divengine/div", "require")
    assert ("phpunit/phpunit", "dev") in names
    assert ("divengine/functions", "dependency") in names
    assert names[-2:] == [("ext-mbstring", "platform"), ("php", "platform")]
    div = project.packages[0]
    assert div.version and div.description and "divengine/functions" in div.requires
    assert cmp.read(tmp_path / "nothing").json is None
    (tmp_path / "composer.json").write_text("{broken")
    assert cmp.read(tmp_path).problem is not None


def test_constraints_names_and_the_new_file(tmp_path):
    assert cmp.suggest_constraint(["dev-main", "2.1.0-beta", "2.0.3", "1.0"]) == "^2.0"
    assert cmp.suggest_constraint(["0.4.1"]) == "^0.4"
    assert cmp.suggest_constraint(["dev-main"]) is None
    new = cmp.NewProject("acme/shop", namespace="Acme\\Shop")
    data = new.json()
    assert data["require"] == {"php": ">=8.0", "divengine/div": "^6.1"}
    assert data["autoload"] == {"psr-4": {"Acme\\Shop\\": "src/"}}
    assert json.loads(new.text()) == data
    assert cmp.NewProject("Acme Shop").problems() and cmp.NewProject("acme/x", namespace="9a").problems()
    assert cmp.suggest_name(tmp_path / "My Shop") .endswith("/my-shop")


def test_finding_composer(tmp_path, monkeypatch):
    monkeypatch.delenv(cmp.ENV, raising=False)
    (tmp_path / "composer.phar").write_text("")
    assert cmp.find(tmp_path)[-1] == str(tmp_path / "composer.phar")
    chosen = tmp_path / "mine"
    chosen.write_text("")
    assert cmp.find(tmp_path, str(chosen)) == [str(chosen)]


async def test_run_streams_and_stops(tmp_path, fake):
    (tmp_path / "composer.json").write_text("{}")
    command = cmp.find(tmp_path)
    seen: list[str] = []
    result = await cmp.run(command, ["install"], tmp_path, seen.append)
    assert result.ok and seen == ["Installing dependencies from lock file", "Generating autoload files"]
    assert not (await cmp.run(command, ["validate"], tmp_path)).ok
    task = asyncio.ensure_future(cmp.run(command, ["slow"], tmp_path))
    await asyncio.sleep(1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [f.name for f in await cmp.search(command, "acme", tmp_path)] == ["acme/tables", "acme/forms"]
    assert (await cmp.versions(command, "acme/tables", tmp_path))[1] == "2.1.0"
    assert await cmp.outdated(command, tmp_path) == {"divengine/div": "7.0.0"}


# ------------------------------------------------------------------ the window
async def test_a_new_composer_json_and_install(tmp_path, fake):
    project = tmp_path / "my-shop"
    project.mkdir()
    app = Divide(project, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await app.open_composer()
        await until(pilot, lambda: isinstance(app.screen, DialogScreen))
        dialog = app.screen.dialog
        assert isinstance(dialog, NewComposerDialog)
        assert dialog.inputs["name"].data.endswith("/my-shop")
        dialog.inputs["name"].data = "acme/shop"
        dialog.inputs["namespace"].data = "Acme\\Shop"
        dialog.end_modal(Command.OK)
        await close_progress(pilot, app)
        data = json.loads((project / "composer.json").read_text())
        assert data["name"] == "acme/shop" and data["require"]["divengine/div"] == "^6.1"
        assert (project / "src").is_dir()
        assert calls(fake)[-1] == ["install"]
        log = next(w for w in app.windows() if isinstance(w, ComposerLogWindow))
        assert "Generating autoload files" in log.lines
        win = next(w for w in app.windows() if isinstance(w, ComposerWindow))
        assert any("divengine/div" in row for row in win.packages.items)


async def test_add_remove_and_newer_versions(tmp_path, fake):
    (tmp_path / "composer.json").write_text(json.dumps({"name": "acme/shop", "require": {"divengine/div": "^6.1"}}))
    app = Divide(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await app.open_composer()
        await settle(pilot)
        win = app.active_window()
        assert isinstance(win, ComposerWindow)
        # add: search as you type, the version suggested from the newest stable one
        app.composer_action(win, "add")
        await until(pilot, lambda: isinstance(app.screen, DialogScreen))
        dialog = app.screen.dialog
        assert isinstance(dialog, AddPackageDialog)
        dialog.query_input.focus()
        await pilot.press(*"acme")
        await until(pilot, lambda: dialog.found and dialog.version_input.data == "^2.1")
        assert dialog.chosen == "acme/tables"
        dialog.flags.value = 1  # dev
        dialog.end_modal(Command.OK)
        await close_progress(pilot, app)
        assert ["require", "--dev", "acme/tables:^2.1"] in calls(fake)
        assert json.loads((tmp_path / "composer.json").read_text())["require-dev"] == {"acme/tables": "^2.1"}
        assert any("acme/tables" in row for row in win.packages.items)
        # remove it again
        win.packages.focus_item(next(i for i, p in enumerate(win.project.packages) if p.name == "acme/tables"))
        await settle(pilot)
        app.composer_action(win, "remove")
        await until(pilot, lambda: isinstance(app.screen, DialogScreen))
        await pilot.press("y")
        await close_progress(pilot, app)
        assert ["remove", "--dev", "acme/tables"] in calls(fake)
        assert "acme/tables" not in json.loads((tmp_path / "composer.json").read_text()).get("require-dev", {})
        # newer versions are marked
        app.composer_action(win, "outdated")
        await close_progress(pilot, app)
        assert win.latest == {"divengine/div": "7.0.0"}
        assert win.packages.items[0].startswith("↑")


async def test_a_failure_shows_composer_s_words(tmp_path, fake):
    (tmp_path / "composer.json").write_text('{"name": "acme/shop"}')
    app = Divide(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        await app.open_composer()
        await settle(pilot)
        win = app.active_window()
        app.composer_action(win, "validate")
        await close_progress(pilot, app)
        assert "failed" in win.last
        log = app.active_window()
        assert isinstance(log, ComposerLogWindow) and any("invalid" in line for line in log.lines)
    assert os.environ.get(cmp.ENV)
