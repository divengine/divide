"""divide's MCP server (``divide --mcp PROJECT``), through MCP clients.

Most tests talk to the server over stdio, as an agent does: the official SDK's
client starts ``divide --mcp`` as a process. Some speak JSON-RPC by hand on the
process's pipes (a clean stdout, cancellation), a few connect the SDK's client
in-process to change a limit. Rendering needs php and a Div engine
(DIVIDE_DIV_PHP, as in test_render); those tests are skipped without them.
"""

import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import Client  # noqa: E402
from mcp.client.stdio import StdioServerParameters  # noqa: E402

from divide import __version__, mcpserver  # noqa: E402
from divide.app import Divide, main  # noqa: E402
from divide.run import children, workbench  # noqa: E402
from divide.run.render import ENV_ENGINE, render  # noqa: E402

ENGINE = os.environ.get(ENV_ENGINE)
needs_div = pytest.mark.skipif(
    not (shutil.which("php") and ENGINE and Path(ENGINE).is_file()),
    reason=f"needs php and {ENV_ENGINE} pointing to Div",
)
START = "import sys; from divide.app import main; sys.argv[0] = 'divide'; main()"
PASSED = (ENV_ENGINE, "XDG_CONFIG_HOME", "DIV_HOME", "DIVIDE_LANGUAGE", "PATH", "SYSTEMROOT", "HOME", "USERPROFILE", "TMP", "TEMP")


def server_env(**changes) -> dict[str, str]:
    env = {k: os.environ[k] for k in PASSED if k in os.environ}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(Path(__file__).parents[1] / "src"), os.environ.get("PYTHONPATH")]))
    for key, value in changes.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def stdio(root: Path, **env) -> Client:
    return Client(StdioServerParameters(command=sys.executable, args=["-c", START, "--mcp", str(root)], env=server_env(**env)))


def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "parts").mkdir(parents=True)
    (root / "parts" / "greet.tpl").write_text("Hi {$name}!", encoding="utf-8")
    (root / "page.tpl").write_text("{% parts/greet %}|[$items]<{$value}>[/$items]", encoding="utf-8")
    (root / "page.json").write_text('// data for page.tpl\n{"name": "Rafa", "items": [1, 2]}\n', encoding="utf-8")
    return root


async def call(client: Client, name: str, **arguments):
    result = await client.call_tool(name, arguments)
    return result


def content(result) -> dict:
    assert not result.is_error, result.content
    return result.structured_content


def error(result) -> str:
    assert result.is_error, result.structured_content
    return result.content[0].text


def snapshot(*folders: Path) -> dict:
    out = {}
    for folder in folders:
        for path in sorted(folder.rglob("*")):
            stat = path.lstat()
            out[str(path)] = (stat.st_size, stat.st_mtime_ns)
    return out


# ------------------------------------------------------------------ protocol
async def test_initialization_and_the_tools(tmp_path):
    async with stdio(project(tmp_path)) as client:
        info = client.server_info
        assert (info.name, info.version) == ("divide", __version__)
        assert "never writes to the project" in client.instructions
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"project_info", "div_check", "div_render", "div_trace", "div_trace_page",
                          "div_trace_mutation", "div_check_dialect"}
    render_schema = tools["div_render"].input_schema
    assert render_schema["required"] == ["template"]
    assert {"data_file", "source", "data", "use_data_file", "max_output_chars", "timeout_seconds"} <= set(render_schema["properties"])
    assert all(t.annotations.read_only_hint and not t.annotations.open_world_hint for t in tools.values())


def rpc_lines(proc_out: bytes) -> list[dict]:
    return [json.loads(line) for line in proc_out.decode("utf-8").splitlines() if line.strip()]


async def raw_server(root: Path, **env):
    return await asyncio.create_subprocess_exec(
        sys.executable, "-c", START, "--mcp", str(root), env=server_env(**env),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)


async def send(proc, message: dict) -> None:
    proc.stdin.write((json.dumps(message) + "\n").encode())
    await proc.stdin.drain()


async def reply(proc, ident: int, timeout: float = 30) -> dict:
    while True:
        line = await asyncio.wait_for(proc.stdout.readline(), timeout)
        assert line, "the server closed stdout"
        message = json.loads(line)  # every line on stdout is a protocol message
        if message.get("id") == ident:
            return message


async def handshake(proc) -> None:
    await send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}})
    assert (await reply(proc, 1))["result"]["serverInfo"]["name"] == "divide"
    await send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})


@needs_div
async def test_stdout_carries_only_the_protocol(tmp_path):
    root = project(tmp_path)
    (root / "noisy.tpl").write_text("<?php echo 'stray'; ?>{$x}(# 1/0 #)", encoding="utf-8")
    proc = await raw_server(root)
    await handshake(proc)
    for n, (name, args) in enumerate([("project_info", {}), ("div_render", {"template": "noisy.tpl"}),
                                      ("div_trace", {"template": "noisy.tpl"}), ("div_check", {"template": "page.tpl"})]):
        await send(proc, {"jsonrpc": "2.0", "id": 10 + n, "method": "tools/call", "params": {"name": name, "arguments": args}})
        await reply(proc, 10 + n)
    proc.stdin.close()
    out, err = await asyncio.wait_for(proc.communicate(), 30)
    assert all(m.get("jsonrpc") == "2.0" for m in rpc_lines(out))
    assert proc.returncode == 0, err


# ------------------------------------------------------------------ tools
@needs_div
async def test_render_is_the_ides_render(tmp_path):
    root = project(tmp_path)
    async with stdio(root) as client:
        got = content(await call(client, "div_render", template="page.tpl"))
    assert got["status"] == "ok" and got["output"] == "Hi Rafa!|<1><2>"
    assert (got["template"], got["data_file"], got["data"], got["source"]) == ("page.tpl", "page.json", "file", "file")
    page = root / "page.tpl"
    direct = await render(workbench.engine_for(root, page), page, page.read_text(encoding="utf-8"),
                          (root / "page.json").read_text(encoding="utf-8"), cwd=root)
    assert got["output"] == direct.output and got["div"] == direct.version
    app = Divide(root, [page])  # and as divide shows it after Ctrl+F9
    async with app.run_test(size=(120, 40)) as pilot:
        for _ in range(4):
            await pilot.pause()
        await pilot.press("ctrl+f9")
        for _ in range(100):
            if (out := app.output_window()) is not None and out.view.text:
                break
            await pilot.pause(0.05)
        assert app.output_window().view.text == got["output"]


@needs_div
async def test_render_takes_source_and_data_unsaved(tmp_path):
    root = project(tmp_path)
    async with stdio(root) as client:
        got = content(await call(client, "div_render", template="page.tpl", source="X{% parts/greet %}", data='{name: "Ana"}'))
        assert (got["output"], got["source"], got["data"], got["data_file"]) == ("XHi Ana!", "argument", "argument", None)
        new = content(await call(client, "div_render", template="drafts.tpl", source="{$name}", data_file="page.json"))
        assert new["output"] == "Rafa" and new["data_file"] == "page.json"
        bare = content(await call(client, "div_render", template="page.tpl", use_data_file=False))
        assert bare["data"] == "none" and bare["output"].startswith("Hi {$name}!")
    assert not (root / "drafts.tpl").exists()


@needs_div
async def test_render_reports_div_messages_and_fatal(tmp_path):
    root = project(tmp_path)
    (root / "bad.json").write_text('{"name": ', encoding="utf-8")
    async with stdio(root) as client:
        got = content(await call(client, "div_render", template="page.tpl", data_file="bad.json"))
    assert got["status"] == "warnings"
    assert any(m["level"] == "DATA" for m in got["messages"])


@needs_div
async def test_check_is_the_editors(tmp_path):
    root = project(tmp_path)
    (root / "broken.tpl").write_text("{% parts/greet %}\n{% nowhere %}\n[$items]{$value}\n", encoding="utf-8")
    async with stdio(root) as client:
        got = content(await call(client, "div_check", template="broken.tpl"))
        fine = content(await call(client, "div_check", template="broken.tpl", source="{% parts/greet %}"))
    assert got["div_consulted"] and got["includes"] == {"nowhere": None, "parts/greet": "parts/greet.tpl"}
    found = {(d["severity"], d["line"], d["message"]) for d in got["diagnostics"]}
    assert ("warning", 2, "Div cannot find the template nowhere") in found
    assert any(sev == "error" and line == 3 for sev, line, _ in found)  # the loop never closes
    assert got["errors"] >= 1 and fine["diagnostics"] == []
    path = root / "broken.tpl"
    app = Divide(root, [path])  # the same findings as divide's editor, once Div answered
    async with app.run_test(size=(120, 40)) as pilot:
        win = app.window_for(path.resolve())
        for _ in range(100):
            if win.editor.include_targets:
                break
            await pilot.pause(0.05)
        editor = [(d.start, d.end, d.severity, d.message) for d in win.editor.diagnostics]
    assert editor == [(d["start"], d["end"], d["severity"], d["message"]) for d in got["diagnostics"]]


@needs_div
async def test_trace_pages_and_mutations(tmp_path):
    root = project(tmp_path)
    async with stdio(root) as client:
        got = content(await call(client, "div_trace", template="page.tpl", limit=2))
        assert got["output"] == "Hi Rafa!|<1><2>" and got["status"] == "ok"
        summary = got["summary"]
        assert summary["runs"] >= 1 and summary["changes"] >= 2 and summary["fixed_points"]
        assert [m["index"] for m in got["mutations"]] == [0, 1] and got["next_offset"] == 2
        assert got["mutations"][0]["kind"] == "start" and got["mutations"][0]["run"] == 1
        changes = content(await call(client, "div_trace_page", trace_id=got["trace_id"], kind="change", limit=200))
        assert changes["total"] == summary["changes"] and all(m["kind"] == "change" for m in changes["mutations"])
        first = changes["mutations"][0]
        assert {"removed", "inserted", "delta", "label", "level", "cycle"} <= set(first)
        whole = content(await call(client, "div_trace_mutation", trace_id=got["trace_id"], index=first["index"]))
        assert len(whole["after"]) == first["size"] and whole["causes"]
        assert "unknown trace_id" in error(await call(client, "div_trace_page", trace_id="nope"))
        assert "index" in error(await call(client, "div_trace_mutation", trace_id=got["trace_id"], index=10_000))


@needs_div
async def test_project_info_and_dialects(tmp_path):
    root = project(tmp_path)
    (root / ".div").mkdir()
    (root / "erb.dialect").write_text('{"DIV_TAG_REPLACEMENT_PREFIX": "<%", "DIV_TAG_REPLACEMENT_SUFFIX": "%>"}', encoding="utf-8")
    (root / "bad.dialect").write_text('{"DIV_TAG_REPLACEMENT_PREFIX": "", "DIV_TAG_REPLACEMENT_SUFFIX": ""}', encoding="utf-8")
    (root / ".div" / "setup.json").write_text(
        '{"dialect": "erb.dialect",\n "parser": {"max_cycles": "many"},\n "request": {"cookie": {"token": "s3cret"}}}', encoding="utf-8")
    async with stdio(root) as client:
        info = content(await call(client, "project_info"))
        mine = content(await call(client, "div_check_dialect"))
        bad = content(await call(client, "div_check_dialect", dialect_file="bad.dialect"))
        tags = content(await call(client, "div_check_dialect", tags={"DIV_TAG_REPLACEMENT_PREFIX": "[["}))
    assert info["project"]["name"] == "proj" and info["php"]["found"] and info["engine"]["origin"] == ENV_ENGINE
    assert info["setup"]["files"] == [".div/setup.json"] and info["dialect"]["source"] == "erb.dialect"
    assert info["div"]["checked"] and info["div"]["dialect"] == "valid"
    problem = info["problems"][0]
    assert (problem["file"], problem["line"]) == (".div/setup.json", 2)
    assert info["setup"]["request"] == {"cookie": ["token"]} and "s3cret" not in json.dumps(info)
    assert mine["valid"] and mine["source"] == "erb.dialect"
    assert bad["valid"] is False and bad["reason"]
    assert tags["valid"] is True


# ------------------------------------------------------------------ trust and confinement
@needs_div
async def test_untrusted_php_settings_stay_left_out(tmp_path):
    root = project(tmp_path)
    (root / ".div").mkdir()
    (root / ".div" / "setup.json").write_text('{"php": {"modifiers": {"up:": "strtoupper"}}}', encoding="utf-8")
    (root / "up.tpl").write_text("{up:name}", encoding="utf-8")
    (root / "up.json").write_text('{"name": "rafa"}', encoding="utf-8")
    home = Path(os.environ["DIV_HOME"])
    async with stdio(root) as client:
        info = content(await call(client, "project_info"))
        got = content(await call(client, "div_render", template="up.tpl"))
    assert info["untrusted_php"]["modifiers"] == {"up:": "strtoupper"} and "Options > Div setup" in info["untrusted_php"]["how"]
    assert got["output"] != "RAFA" and got["untrusted_php"] is not None
    assert any(m["level"] == "SETUP" and "trust" in m["text"] for m in got["messages"])
    assert not (home / "trust.json").exists()


async def test_paths_stay_in_the_project(tmp_path):
    root = project(tmp_path)
    outside = tmp_path / "secret.tpl"
    outside.write_text("{$x}", encoding="utf-8")
    links = True
    try:
        (root / "link.tpl").symlink_to(outside)
        (root / "away").symlink_to(tmp_path, target_is_directory=True)
    except OSError:  # Windows without the right to make links
        links = False
    async with stdio(root) as client:
        for name, args in [("div_check", {"template": "../secret.tpl"}), ("div_check", {"template": str(outside)}),
                           ("div_render", {"template": "../secret.tpl"}),
                           ("div_render", {"template": "page.tpl", "data_file": "../secret.tpl"}),
                           ("div_trace", {"template": "parts/../../secret.tpl"}),
                           ("div_check_dialect", {"dialect_file": "../secret.tpl"})]:
            assert "outside the project" in error(await call(client, name, **args)), (name, args)
        if links:
            assert "outside the project" in error(await call(client, "div_check", template="link.tpl"))
            assert "outside the project" in error(await call(client, "div_render", template="away/secret.tpl"))
        assert "no such file" in error(await call(client, "div_check", template="missing.tpl"))
        assert "relative to the project" in error(await call(client, "div_check", template=""))


@needs_div
async def test_nothing_is_written(tmp_path):
    root = project(tmp_path)
    (root / "page.php").write_text("<?php echo 1;", encoding="utf-8")
    watched = (root, Path(os.environ["DIV_HOME"]), Path(os.environ["XDG_CONFIG_HOME"]))
    before = snapshot(*watched)
    async with stdio(root) as client:
        content(await call(client, "project_info"))
        content(await call(client, "div_check", template="page.tpl"))
        content(await call(client, "div_render", template="page.tpl"))
        content(await call(client, "div_render", template="page.tpl", source="{$name}"))
        trace = content(await call(client, "div_trace", template="page.tpl"))
        content(await call(client, "div_trace_mutation", trace_id=trace["trace_id"], index=1))
        content(await call(client, "div_check_dialect"))
    assert snapshot(*watched) == before


# ------------------------------------------------------------------ no PHP, no Div
async def test_without_php(tmp_path):
    root = project(tmp_path)
    empty = tmp_path / "bin"
    empty.mkdir()
    async with stdio(root, PATH=str(empty)) as client:
        info = content(await call(client, "project_info"))
        assert info["php"] == {"found": False, "version": None} and info["div"]["checked"] is False
        assert "php not found" in error(await call(client, "div_render", template="page.tpl"))
        assert "php not found" in error(await call(client, "div_trace", template="page.tpl"))
        check = content(await call(client, "div_check", template="page.tpl"))  # divide's checks still run
        assert check["div_consulted"] is False and check["note"]


@pytest.mark.skipif(not shutil.which("php"), reason="needs php")
async def test_without_div(tmp_path):
    root = project(tmp_path)
    async with stdio(root, **{ENV_ENGINE: None}) as client:
        info = content(await call(client, "project_info"))
        assert info["engine"] is None and info["div"]["reason"] == "Div was not found"
        message = error(await call(client, "div_render", template="page.tpl"))
    assert "Div was not found" in message and "composer require divengine/div" in message


# ------------------------------------------------------------------ bounds, timeouts, cancellation
@needs_div
async def test_bounded_outputs_and_arguments(tmp_path, monkeypatch):
    root = project(tmp_path)
    (root / "big.tpl").write_text("[$items]{$value}-[/$items]", encoding="utf-8")
    (root / "big.json").write_text(json.dumps({"items": list(range(3000))}), encoding="utf-8")
    async with Client(mcpserver.build(root)) as client:  # in-process: a limit can be changed
        got = content(await call(client, "div_render", template="big.tpl", max_output_chars=10))
        assert got["output_truncated"] and len(got["output"]) == 10 and got["output_chars"] > 10_000
        trace = content(await call(client, "div_trace", template="big.tpl", limit=3, max_output_chars=5))
        assert len(trace["mutations"]) == 3 and trace["next_offset"] == 3 and trace["output_truncated"]
        assert all(len(m.get("inserted", {}).get("text", "")) <= mcpserver.EXCERPT for m in trace["mutations"])
        one = content(await call(client, "div_trace_mutation", trace_id=trace["trace_id"], index=trace["summary"]["mutations"] - 1, max_chars=7))
        assert len(one["after"]) <= 7 and one["after_truncated"]
        monkeypatch.setattr(mcpserver, "MAX_INPUT", 100)
        assert "more than 100" in error(await call(client, "div_render", template="page.tpl", source="x" * 101))
        assert "between 1" in error(await call(client, "div_render", template="page.tpl", max_output_chars=0))
        assert "between 1" in error(await call(client, "div_render", template="page.tpl", timeout_seconds=1000))
        assert "between 1" in error(await call(client, "div_trace", template="page.tpl", limit=10_000))


def slow_project(tmp_path: Path) -> Path:
    root = project(tmp_path)
    (root / "slow.tpl").write_text("a(# sleep(8) #)b", encoding="utf-8")
    home = Path(os.environ["DIV_HOME"])  # the user's own setup is trusted: sleep may be called
    home.mkdir(parents=True, exist_ok=True)
    (home / "setup.json").write_text('{"php": {"allowed_functions": ["sleep"]}}', encoding="utf-8")
    return root


@needs_div
async def test_a_render_that_takes_too_long_is_stopped(tmp_path):
    root = slow_project(tmp_path)
    async with stdio(root) as client:
        started = time.monotonic()
        message = error(await call(client, "div_render", template="slow.tpl", timeout_seconds=1))
        assert "longer than 1s" in message and time.monotonic() - started < 6
        assert content(await call(client, "div_render", template="page.tpl"))["output"] == "Hi Rafa!|<1><2>"


def php_children(pid: int) -> list[str]:
    """The php processes under ``pid`` (Linux: /proc)."""
    found = []
    for entry in Path("/proc").iterdir():
        try:
            if entry.name.isdigit() and int((entry / "stat").read_text().rsplit(")", 1)[1].split()[1]) == pid:
                found.append((entry / "cmdline").read_bytes().split(b"\0")[0].decode())
        except (OSError, IndexError, ValueError):
            continue
    return [c for c in found if Path(c).name.startswith("php")]


@needs_div
async def test_a_cancelled_call_stops_php(tmp_path):
    root = slow_project(tmp_path)
    proc = await raw_server(root)
    await handshake(proc)
    await send(proc, {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                      "params": {"name": "div_render", "arguments": {"template": "slow.tpl"}}})
    linux = sys.platform.startswith("linux")
    for _ in range(100):  # php is running
        if not linux or php_children(proc.pid):
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.3)
    await send(proc, {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 7, "reason": "test"}})
    started = time.monotonic()
    await send(proc, {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                      "params": {"name": "div_render", "arguments": {"template": "page.tpl"}}})
    answer = await reply(proc, 8, timeout=20)
    assert answer["result"]["structuredContent"]["output"] == "Hi Rafa!|<1><2>" and time.monotonic() - started < 6
    if linux:
        assert php_children(proc.pid) == []
    proc.stdin.close()
    await asyncio.wait_for(proc.communicate(), 30)
    assert children.running() == []


# ------------------------------------------------------------------ the command line
def test_the_command_line(tmp_path, capsys, monkeypatch):
    root = project(tmp_path)
    for argv in (["--mcp"], ["--mcp", str(root / "page.tpl")], ["--mcp", str(root), str(root / "parts")]):
        with pytest.raises(SystemExit) as stop:
            main(argv)
        assert stop.value.code == 2
        assert "--mcp takes one project folder" in capsys.readouterr().err
    with pytest.raises(SystemExit) as stop:
        main(["--help"])
    assert stop.value.code == 0 and "--mcp" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["--version"])
    assert capsys.readouterr().out.strip() == f"divide {__version__}"
    import divide

    monkeypatch.delattr(divide, "mcpserver")  # the mcp extra not installed
    monkeypatch.setitem(sys.modules, "divide.mcpserver", None)
    with pytest.raises(SystemExit) as stop:
        main(["--mcp", str(root)])
    assert stop.value.code == 2 and "pip install 'divide[mcp]'" in capsys.readouterr().err
