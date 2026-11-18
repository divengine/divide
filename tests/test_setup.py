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
    file.write_text(text if isinstance(text, str) else json.dumps(text), encoding="utf-8")
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
    (tmp_path / "vendor" / "autoload.php").write_text("<?php\n", encoding="utf-8")
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
    root = tmp_path.resolve().as_posix()  # Div gets folders with /, Windows too
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
    assert "not a file" in lines[5]  # the dialect file
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
    assert setup.include_paths == ((home / "lib").resolve().as_posix() + "/",)


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
    assert setup.include_paths == ((project / "b").resolve().as_posix() + "/", (home / "a").resolve().as_posix() + "/")
    write_setup(project, {"paths": {"include": None}, "files": None})
    setup = div_setup.load(project)
    assert setup.include_paths == () and "DIV_DEFAULT_TPL_FILE_EXT" not in setup.constants


def test_engine_order(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_ENGINE, raising=False)
    mine, chosen = tmp_path / "mine.php", tmp_path / "chosen.php"
    mine.write_text("<?php\n", encoding="utf-8")
    chosen.write_text("<?php\n", encoding="utf-8")
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
    (tmp_path / "tpls" / "part.html").write_text("from packages", encoding="utf-8")
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "box.html").write_text("from an include path", encoding="utf-8")
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
    page.write_text("Hi", encoding="utf-8")
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


# ------------------------------------------------------------------ the rest of the setup
def test_every_section_read_and_merged(tmp_path, monkeypatch):
    home = tmp_path / "home"
    write_setup(home, {"data": {"globals": {"site": "Mine", "year": 2020}, "system_vars": ["server"],
                                "defaults": [{"search": None, "replace": "user"}]},
                       "php": {"allowed_functions": ["md5"], "modifiers": {"up:": "strtoupper"}},
                       "request": {"server": {"HTTP_HOST": "mine.test", "LANG": "es"}}})
    monkeypatch.setenv("DIV_HOME", str(home / ".div"))
    project = tmp_path / "shop"
    project.mkdir()
    (project / "erb.dialect").write_text('{"DIV_TAG_REPLACEMENT_PREFIX": "<%= ", "DIV_TAG_REPLACEMENT_SUFFIX": " %>", name: "erb"}', encoding="utf-8")
    write_setup(project, {
        "dialect": "erb.dialect",
        "data": {"globals": {"site": "Shop"}, "system_vars": ["div.ascii", "now"],
                 "defaults": [{"search": None, "replace": "-"}, {"search": 0, "replace": "zero"}],
                 "defaults_by_var": [{"var": "price", "search": 0, "replace": "free"}]},
        "request": {"get": {"page": 2}, "server": {"HTTP_HOST": "shop.test"}, "session": {"user": "rafa"}},
    })
    setup = div_setup.load(project)
    assert setup.problems == ()
    assert setup.dialect_tags == {"DIV_TAG_REPLACEMENT_PREFIX": "<%= ", "DIV_TAG_REPLACEMENT_SUFFIX": " %>"}
    assert setup.dialect.name == "erb" and setup.dialect["DIV_TAG_REPLACEMENT_PREFIX"] == "<%= "
    assert setup.dialect["DIV_TAG_LOOP_BEGIN_PREFIX"] == "[$"  # Div's for the rest
    assert setup.globals == {"site": "Shop", "year": 2020}
    assert setup.system_vars == ("ascii", "server")  # "now" is always on
    assert setup.defaults == ((None, "-"), (0, "zero"))
    assert setup.defaults_by_var == (("price", 0, "free"),)
    assert setup.allowed_functions == ("md5",) and setup.modifiers == {"up:": "strtoupper"}  # the user's: trusted
    assert setup.request == {"get": {"page": 2}, "server": {"HTTP_HOST": "shop.test", "LANG": "es"},
                             "session": {"user": "rafa"}}
    bridge = setup.bridge()
    assert bridge["constants"]["DIV_TAG_REPLACEMENT_PREFIX"] == "<%= "
    assert "DIV_TAG_REPLACEMENT_PREFIX" not in setup.bridge(dialect=False).get("constants", {})
    variables = setup.variables()
    assert variables["site"] == "Shop" and variables["div.server"]["HTTP_HOST"] == "shop.test"


def test_bad_parts_of_sections(tmp_path):
    (tmp_path / "x.dialect").write_text('{"DIV_TAG_NOPE": "x", "DIV_TAG_EMPTY": true}', encoding="utf-8")
    write_setup(tmp_path, {
        "dialect": "x.dialect",
        "data": {"globals": [1], "system_vars": ["cookies"], "defaults": [{"search": 1}],
                 "defaults_by_var": [{"search": 1, "replace": 2}]},
        "php": {"allowed_functions": ["system()"], "modifiers": {"x:": "not a function"}},
        "request": {"get": "page=1", "files": {}},
    })
    texts = " / ".join(p.text for p in div_setup.load(tmp_path).problems)
    for expected in ("DIV_TAG_NOPE", "DIV_TAG_EMPTY must be text", "data.globals", "div.cookies",
                     "data.defaults:", "data.defaults_by_var", "system()", '"x:"', "request.get", "request.files"):
        assert expected in texts, expected


def test_a_projects_php_waits_for_trust(tmp_path):
    file = write_setup(tmp_path, {"php": {"allowed_functions": ["md5"], "modifiers": {"rev:": "strrev"}}})
    setup = div_setup.load(tmp_path)
    assert setup.allowed_functions == () and setup.modifiers == {}
    assert setup.untrusted is not None and setup.untrusted.functions == ("md5",)
    assert any("trust" in p.text for p in setup.problems)
    div_setup.trust(setup.untrusted)
    trusted = div_setup.load(tmp_path)
    assert trusted.untrusted is None and trusted.allowed_functions == ("md5",) and trusted.modifiers == {"rev:": "strrev"}
    write_setup(tmp_path, {"php": {"allowed_functions": ["md5", "exec"]}})  # changed: asked again
    again = div_setup.load(tmp_path)
    assert again.untrusted is not None and again.allowed_functions == ()
    assert file.exists()


def test_the_editor_marks_a_setup_files_problems(tmp_path):
    file = tmp_path / ".div" / "setup.json"
    problems = div_setup.check_text(file, '{"parser": {"max_cycles": 0}}')
    assert len(problems) == 1 and "max_cycles" in problems[0].text
    assert div_setup.is_setup_file(file) and not div_setup.is_setup_file(tmp_path / "setup.json")


def test_the_projects_extensions(tmp_path):
    from divide import lang as languages
    from divide.ui import icons
    try:
        languages.set_project_extensions(".html", ".data")
        assert languages.language_of(tmp_path / "page.html") == "div"
        assert languages.language_of(tmp_path / "page.data") == "json"
        assert languages.language_of(tmp_path / "page.tpl") == "div"
        assert ".html" in languages.template_extensions()
        assert icons.mark_for(tmp_path / "page.html")[0] == "{"
    finally:
        languages.set_project_extensions()
    assert languages.language_of(tmp_path / "page.html") == "html"


def test_include_completion_with_the_projects_extension(tmp_path):
    from divide.lang.div.complete import template_paths
    (tmp_path / "parts").mkdir()
    (tmp_path / "parts" / "menu.html").write_text("", encoding="utf-8")
    (tmp_path / "parts" / "old.tpl").write_text("", encoding="utf-8")
    names = [c.label for c in template_paths("parts/", None, [tmp_path], ".html")]
    assert names == ["parts/menu"]


def test_a_template_dialect_is_completed_with_the_projects():
    from divide.lang.div.dialect import Dialect
    project = Dialect.from_overrides({"DIV_TAG_REPLACEMENT_PREFIX": "<%= ", "DIV_TAG_REPLACEMENT_SUFFIX": " %>"})
    own = Dialect.from_overrides({"DIV_TAG_LOOP_BEGIN_PREFIX": "<% each "}, base=project)
    assert own["DIV_TAG_REPLACEMENT_PREFIX"] == "<%= " and own["DIV_TAG_LOOP_BEGIN_PREFIX"] == "<% each "


@needs_div
async def test_div_takes_the_whole_setup(tmp_path):
    (tmp_path / "erb.dialect").write_text('{"DIV_TAG_REPLACEMENT_PREFIX": "<%= ", "DIV_TAG_REPLACEMENT_SUFFIX": " %>"}', encoding="utf-8")
    file = write_setup(tmp_path, {
        "dialect": "erb.dialect",
        "data": {"globals": {"site": "Shop"}, "system_vars": ["server"],
                 # text: Div's jsonDecode() makes numbers floats, and Div matches defaults by serialize()
                 "defaults_by_var": [{"var": "price", "search": "0", "replace": "free"}]},
        "php": {"modifiers": {"rev:": "strrev"}, "allowed_functions": ["str_repeat"]},
        "request": {"get": {"page": "2"}, "server": {"HTTP_HOST": "shop.test"}},
    })
    div_setup.trust(div_setup.load(tmp_path).untrusted)
    page = tmp_path / "page.tpl"
    code = "<%= $site %>|<%= $price %>|<%= rev:site %>|<%= $div.get.page %>|<%= $div.server.HTTP_HOST %>|(# str_repeat('a', 3) #)"
    result = await render(Path(ENGINE), page, code, '{"price": "0"}', cwd=tmp_path)
    assert result.output == "Shop|free|pohS|2|shop.test|aaa", result.messages
    check = await render_mod.check_setup(Path(ENGINE), cwd=tmp_path)
    assert check.dialect is None and check.functions == {"str_repeat": True} and check.modifiers == {"rev:": True}
    assert file.exists()


@needs_div
async def test_a_dialect_div_rejects_is_left_out(tmp_path):
    (tmp_path / "bad.dialect").write_text('{"DIV_TAG_EMPTY": "@break@"}', encoding="utf-8")  # the same as DIV_TAG_BREAK
    write_setup(tmp_path, {"dialect": "bad.dialect"})
    result = await render(Path(ENGINE), tmp_path / "p.tpl", "{$x}", '{"x": "ok"}', cwd=tmp_path)
    assert result.output == "ok" and not result.fatal
    assert any(m.level == "SETUP" and "rejects" in m.text for m in result.messages)


@needs_div
async def test_div_reports_what_php_lacks(tmp_path):
    write_setup(tmp_path, {"php": {"allowed_functions": ["no_such_function_x"], "modifiers": {"z:": "no_such_fn_y"}}})
    div_setup.trust(div_setup.load(tmp_path).untrusted)
    check = await render_mod.check_setup(Path(ENGINE), cwd=tmp_path)
    assert check.functions == {"no_such_function_x": False} and check.modifiers == {"z:": False}
    assert sum(m.level == "SETUP" for m in check.messages) == 2
