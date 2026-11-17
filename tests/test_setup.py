"""The project's Div setup (.div/setup.json and ~/.div/setup.json) and how every
request to Div carries it."""

import json
import os
import shutil
from pathlib import Path

import pytest

from divide.run import render as render_mod
from divide.run import setup as div_setup
from divide.run.render import ENV_ENGINE, find_engine, render
from divide.run.trace import trace_render

ENGINE = os.environ.get(ENV_ENGINE)
needs_div = pytest.mark.skipif(
    not (shutil.which("php") and ENGINE and Path(ENGINE).is_file()),
    reason=f"needs php and {ENV_ENGINE} pointing to Div",
)


def write_setup(folder: Path, text: str | dict) -> Path:
    (folder / ".div").mkdir(parents=True, exist_ok=True)
    file = folder / ".div" / "setup.json"
    file.write_text(text if isinstance(text, str) else json.dumps(text))
    return file


# ------------------------------------------------------------------ reading
def test_no_setup_is_div_as_it_comes(tmp_path):
    setup = div_setup.load(tmp_path)
    assert setup.files == () and setup.bridge() == {} and setup.problems == ()
    assert setup.template_ext == ".tpl" and setup.data_ext == ".json" and setup.engine is None


def test_a_project_setup_relative_to_its_root(tmp_path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "shared").mkdir()
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "autoload.php").write_text("<?php\n")
    write_setup(tmp_path, """{
        // comments are fine: Div JSON
        engine: 'vendor/autoload.php',
        "paths": {"packages": "templates", "repository": "templates", "include": "shared"},
        "files": {"template_ext": ".html", "data_ext": "data"},
        "parser": {"max_cycles": 7, "max_filename": 300, "error_reporting": "E_ALL & ~E_NOTICE & ~E_DEPRECATED"}
    }""")
    sub = tmp_path / "pages" / "deep"
    sub.mkdir(parents=True)
    setup = div_setup.load(sub)  # found walking up
    assert setup.problems == ()
    assert setup.engine == tmp_path.resolve() / "vendor" / "autoload.php"
    root = str(tmp_path.resolve())
    assert setup.bridge() == {
        "constants": {
            "PACKAGES": f"{root}/templates/", "DIV_REPO": f"{root}/templates/",
            "DIV_DEFAULT_TPL_FILE_EXT": "html", "DIV_DEFAULT_DATA_FILE_EXT": "data",
            "DIV_MAX_PARSE_CYCLES": 7, "DIV_MAX_FILENAME_SIZE": 300,
        },
        "include_paths": [f"{root}/shared/"],
        "error_reporting": 32767 & ~8 & ~8192,
    }
    assert setup.template_ext == ".html" and setup.data_ext == ".data"


def test_invalid_entries_are_left_out_with_their_place(tmp_path):
    text = """{
  "paths": {"packages": "missing", "include": ["missing-too"]},
  "files": {"template_ext": "t p l"},
  "parser": {"max_cycles": 0, "error_reporting": "E_ALL & ~E_NOPE", "colour": 1},
  "dialect": "erb.dialect",
  "stuff": true,
  "engine": "nope.php"
}"""
    file = write_setup(tmp_path, text)
    setup = div_setup.load(tmp_path)
    assert setup.bridge() == {} and setup.engine is None
    lines: dict[int, str] = {}
    for problem in setup.problems:
        line = text.count("\n", 0, problem.offset) + 1
        lines[line] = lines.get(line, "") + problem.text + " / "
    assert all(p.file == file for p in setup.problems)
    assert lines[2].count("not a folder") == 2
    assert "extension" in lines[3]
    assert "max_cycles" in lines[4] and "E_NOPE" in lines[4] and "parser.colour" in lines[4]
    assert "not applied yet" in lines[5]
    assert "unknown setting" in lines[6]
    assert "not a file" in lines[7]


def test_a_broken_file_says_where(tmp_path):
    write_setup(tmp_path, '{"paths": {"packages": }')
    [problem] = div_setup.load(tmp_path).problems
    assert problem.offset == len('{"paths": {"packages": ')


def test_read_again_when_the_file_changes(tmp_path):
    write_setup(tmp_path, {"parser": {"max_cycles": 5}})
    assert div_setup.load(tmp_path).constants == {"DIV_MAX_PARSE_CYCLES": 5}
    write_setup(tmp_path, {"parser": {"max_cycles": 50}})
    assert div_setup.load(tmp_path).constants == {"DIV_MAX_PARSE_CYCLES": 50}


# ------------------------------------------------------------------ the user's and the project's
def test_the_users_setup_counts_for_every_project(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "lib").mkdir(parents=True)
    write_setup(home, {"parser": {"max_cycles": 9}, "paths": {"include": "lib"}})  # relative to home
    monkeypatch.setenv("DIV_HOME", str(home / ".div"))
    project = tmp_path / "shop"
    project.mkdir()
    setup = div_setup.load(project)
    assert setup.constants == {"DIV_MAX_PARSE_CYCLES": 9}
    assert setup.include_paths == (str((home / "lib").resolve()) + "/",)


def test_the_users_div_is_never_a_projects(tmp_path, monkeypatch):
    home = tmp_path / "home"
    write_setup(home, {"parser": {"max_cycles": 9}})
    monkeypatch.setenv("DIV_HOME", str(home / ".div"))
    project = home / "projects" / "shop"
    project.mkdir(parents=True)
    assert div_setup.project_dir(project) is None
    setup = div_setup.load(project)
    assert setup.files == (home / ".div" / "setup.json",)  # once, as the user's


def test_the_project_wins_and_null_means_divs_default(tmp_path, monkeypatch):
    home = tmp_path / "home"
    for name in ("a", "b"):
        (home / name).mkdir(parents=True)
    write_setup(home, {"parser": {"max_cycles": 9, "max_filename": 99}, "paths": {"include": ["a"]},
                       "files": {"template_ext": "html"}})
    monkeypatch.setenv("DIV_HOME", str(home / ".div"))
    project = tmp_path / "shop"
    (project / "b").mkdir(parents=True)
    write_setup(project, {"parser": {"max_cycles": None, "max_filename": 120}, "paths": {"include": ["b"]}})
    setup = div_setup.load(project)
    assert setup.files[0] == project / ".div" / "setup.json"
    assert setup.constants == {"DIV_MAX_FILENAME_SIZE": 120, "DIV_DEFAULT_TPL_FILE_EXT": "html"}
    assert setup.include_paths == (str((project / "b").resolve()) + "/", str((home / "a").resolve()) + "/")
    write_setup(project, {"paths": {"include": None}, "files": None})
    setup = div_setup.load(project)
    assert setup.include_paths == () and "DIV_DEFAULT_TPL_FILE_EXT" not in setup.constants


def test_engine_order(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_ENGINE, raising=False)
    mine, chosen = tmp_path / "mine.php", tmp_path / "chosen.php"
    mine.write_text("<?php\n")
    chosen.write_text("<?php\n")
    assert find_engine([tmp_path], str(chosen), mine) == mine.resolve()
    assert find_engine([tmp_path], str(chosen), None) == chosen.resolve()
    monkeypatch.setenv(ENV_ENGINE, str(chosen))
    assert find_engine([tmp_path], None, mine) == chosen.resolve()


def test_error_levels():
    assert div_setup.error_level("E_ALL") == 32767
    assert div_setup.error_level("E_ERROR | E_WARNING") == 3
    assert div_setup.error_level("E_ALL & ~E_NOTICE | E_NOTICE") == 32767
    with pytest.raises(ValueError):
        div_setup.error_level("E_EVERYTHING")


# ------------------------------------------------------------------ no request without it
class FakeProcess:
    returncode = 0
    requests: list = []

    async def communicate(self, data: bytes):
        FakeProcess.requests.append(json.loads(data))
        return json.dumps({"messages": [], "valid": True, "translated": "", "resolved": {}}).encode(), b""

    def kill(self):
        pass

    async def wait(self):
        return 0


@pytest.fixture
def requests(monkeypatch):
    FakeProcess.requests = []

    async def fake_exec(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(render_mod.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(render_mod.shutil, "which", lambda name: "/usr/bin/php")
    return FakeProcess.requests


async def every_operation(root: Path):
    engine, page = root / "div.php", root / "page.tpl"
    await render(engine, page, "x", None, cwd=root)
    await trace_render(engine, page, "x", None, cwd=root)
    await render_mod.resolve_includes(engine, page, ["a"], cwd=root)
    await render_mod.check_dialect(engine, {}, cwd=root)
    await render_mod.translate_template(engine, "x", {}, {}, cwd=root)
    await render_mod.load_dialect(engine, cwd=root, file=root / "x.dialect")


async def test_every_operation_carries_the_setup(tmp_path, requests):
    write_setup(tmp_path, {"parser": {"max_cycles": 3}})
    await every_operation(tmp_path)
    ops = [r.get("op", "render") for r in requests]
    assert ops == ["render", "trace", "resolve", "dialect_validate", "translate", "dialect_load"]
    assert all(r["setup"] == {"constants": {"DIV_MAX_PARSE_CYCLES": 3}} for r in requests)


async def test_without_a_setup_requests_are_as_before(tmp_path, requests):
    await every_operation(tmp_path)
    assert len(requests) == 6 and not any("setup" in r for r in requests)


async def test_left_out_settings_reach_the_messages(tmp_path, requests):
    file = write_setup(tmp_path, {"parser": {"max_cycles": "many"}})
    result = await render(tmp_path / "div.php", tmp_path / "p.tpl", "x", None, cwd=tmp_path)
    [message] = result.messages
    assert message.level == "SETUP" and message.path == file and "max_cycles" in message.text
    assert result.serious == [message]


# ------------------------------------------------------------------ Div itself
@needs_div
async def test_div_finds_templates_where_the_setup_says(tmp_path):
    (tmp_path / "tpls").mkdir()
    (tmp_path / "tpls" / "part.html").write_text("from packages")
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "box.html").write_text("from an include path")
    (tmp_path / "pages").mkdir()
    page = tmp_path / "pages" / "page.html"
    code = "[{% part %}] [{% box %}]"
    plain = await render(Path(ENGINE), page, code, None, cwd=tmp_path)
    assert "from packages" not in plain.output and "from an include path" not in plain.output
    write_setup(tmp_path, {"paths": {"packages": "tpls", "include": ["shared"]}, "files": {"template_ext": "html"}})
    result = await render(Path(ENGINE), page, code, None, cwd=tmp_path)
    assert result.output.strip() == "[from packages] [from an include path]", result.messages
    found = await render_mod.resolve_includes(Path(ENGINE), page, ["part", "box"], cwd=tmp_path)
    assert found["part"].file == (tmp_path / "tpls" / "part.html").resolve()
    assert found["box"].file == (tmp_path / "shared" / "box.html").resolve()


@needs_div
async def test_a_left_out_setting_in_the_messages_window_goes_to_its_place(tmp_path):
    from divide.app import Divide
    from divide.ui.windows import MessagesWindow

    page = tmp_path / "page.tpl"
    page.write_text("Hi")
    text = '{\n  "parser": {"max_cycles": "many"}\n}\n'
    file = write_setup(tmp_path, text)
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(120, 40)) as pilot:
        for _ in range(10):
            await pilot.pause()
        await pilot.press("ctrl+f9")
        for _ in range(100):
            if isinstance(app.messages_window(), MessagesWindow):
                break
            await pilot.pause(0.05)
        messages = app.messages_window()
        assert isinstance(messages, MessagesWindow)
        [index] = [i for i, item in enumerate(messages.items) if item.text.startswith("SETUP:")]
        assert ".div/setup.json" in messages.items[index].text and "max_cycles" in messages.items[index].text
        messages.activate(index)
        for _ in range(10):
            await pilot.pause()
        editor = app.active_editor()
        assert editor is not None and editor.path == file.resolve()
        assert editor.editor.cursor_location[0] == 1  # the line of "max_cycles"
