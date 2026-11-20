"""divide's MCP server over Streamable HTTP: the protocol, the transport, its guards and its life.

Raw HTTP (http.client, sockets) for what a client library would hide: both
eras' requests and errors, Host and Origin, the token, sizes, connections.
The official SDKs' clients for interoperability: Python's (both eras) and,
when MCP_TS_SDK names a folder with ``node_modules/@modelcontextprotocol/sdk``,
TypeScript's (the one most MCP clients are built on). The server's life from
the IDE: Options > MCP server starts, stops, restarts it, a taken port is
said, divide's exit and another folder are followed.
"""

import asyncio
import base64
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from divide import __version__, config
from divide.mcpserver import http as mcp_http
from divide.mcpserver.http import HttpServer, StartError, load_token
from divide.mcpserver.protocol import META_CLIENT, META_SERVER, META_VERSION, SUPPORTED
from divide.run.render import ENV_ENGINE

ENGINE = os.environ.get(ENV_ENGINE)
needs_div = pytest.mark.skipif(
    not (shutil.which("php") and ENGINE and Path(ENGINE).is_file()),
    reason=f"needs php and {ENV_ENGINE} pointing to Div",
)
MODERN = "2026-07-28"


def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir(parents=True)
    (root / "page.tpl").write_text("Hi {$name}!", encoding="utf-8")
    (root / "page.json").write_text('{"name": "Rafa"}', encoding="utf-8")
    return root


@pytest.fixture
def server(tmp_path):
    srv = HttpServer(project(tmp_path), port=0)
    srv.start()
    yield srv
    srv.stop()


def post(srv: HttpServer, body=None, headers=None, *, raw: bytes | None = None, method: str = "POST",
         path: str = "/mcp", port: int | None = None):
    """(status, headers, JSON body or None) of one request on its own connection."""
    conn = http.client.HTTPConnection("127.0.0.1", port or srv.port, timeout=30)
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    sent = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    sent.update(headers or {})
    conn.request(method, path, body=data if method == "POST" else None, headers=sent)
    response = conn.getresponse()
    payload = response.read()
    conn.close()
    return response.status, {k.lower(): v for k, v in response.getheaders()}, json.loads(payload) if payload else None


def modern(method: str, params: dict | None = None, ident=1, **header_changes):
    """A 2026-07-28 request: body and headers."""
    params = dict(params or {})
    params["_meta"] = {META_VERSION: MODERN, "io.modelcontextprotocol/clientCapabilities": {},
                       META_CLIENT: {"name": "raw-check", "version": "1"}}
    headers = {"MCP-Protocol-Version": MODERN, "Mcp-Method": method}
    if method == "tools/call":
        headers["Mcp-Name"] = params["name"]
    for key, value in header_changes.items():
        key = key.replace("_", "-")
        if value is None:
            headers.pop(key, None)
        else:
            headers[key] = value
    return {"jsonrpc": "2.0", "id": ident, "method": method, "params": params}, headers


def legacy(method: str, params: dict | None = None, ident=1):
    body = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if ident is not None:
        body["id"] = ident
    return body


def mcp_threads() -> list[str]:
    return [t.name for t in threading.enumerate() if t.name.startswith("mcp-")]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


# ------------------------------------------------------------------ the 2026-07-28 protocol
def test_modern_discover_list_and_call(server):
    status, headers, body = post(server, *modern("server/discover"))
    result = body["result"]
    assert status == 200 and headers["content-type"] == "application/json"
    assert result["resultType"] == "complete" and result["supportedVersions"] == list(SUPPORTED)
    assert result["_meta"][META_SERVER]["name"] == "divide" and result["_meta"][META_SERVER]["version"] == __version__
    assert result["capabilities"] == {"tools": {"listChanged": False}} and result["cacheScope"] == "private"
    assert "never writes to the project" in result["instructions"]
    status, _h, body = post(server, *modern("tools/list"))
    listed = body["result"]
    assert status == 200 and listed["resultType"] == "complete" and listed["ttlMs"] > 0
    assert [t["name"] for t in listed["tools"]][:2] == ["project_info", "div_check"]
    assert all(t["annotations"]["readOnlyHint"] and t["inputSchema"]["type"] == "object" for t in listed["tools"])
    status, _h, body = post(server, *modern("tools/call", {"name": "div_check", "arguments": {"template": "page.tpl"}}))
    assert status == 200 and body["result"]["resultType"] == "complete"
    assert body["result"]["structuredContent"]["template"] == "page.tpl" and not body["result"].get("isError")
    assert json.loads(body["result"]["content"][0]["text"]) == body["result"]["structuredContent"]
    assert "mcp-session-id" not in {k.lower() for k in _h}
    assert server.clients == {"raw-check": "1"}


def test_modern_errors(server):
    def error(body, headers=None, raw=None):
        status, _h, answer = post(server, body, headers=headers, raw=raw)
        return status, answer["error"]["code"], answer["error"]

    status, code, err = error(*modern("tools/list", MCP_Protocol_Version="2099-01-01", ))
    assert (status, code) == (400, -32020)  # the header does not match _meta
    body, headers = modern("tools/list")
    body["params"]["_meta"][META_VERSION] = "2099-01-01"
    headers["MCP-Protocol-Version"] = "2099-01-01"
    status, code, err = error(body, headers)
    assert (status, code) == (400, -32022) and err["data"] == {"supported": list(SUPPORTED), "requested": "2099-01-01"}
    body, headers = modern("tools/list")
    del body["params"]["_meta"]
    assert error(body, headers)[:2] == (400, -32020)  # the header says 2026-07-28, the body does not
    assert error(*modern("tools/list", MCP_Protocol_Version=None))[:2] == (400, -32020)
    assert error(*modern("tools/list", Mcp_Method="tools/call"))[:2] == (400, -32020)
    assert error(*modern("tools/list", Mcp_Method=None))[:2] == (400, -32020)
    call = {"name": "div_check", "arguments": {"template": "page.tpl"}}
    assert error(*modern("tools/call", call, Mcp_Name=None))[:2] == (400, -32020)
    assert error(*modern("tools/call", call, Mcp_Name="div_render"))[:2] == (400, -32020)
    encoded = "=?base64?" + base64.b64encode(b"div_check").decode() + "?="
    status, _h, ok = post(server, *modern("tools/call", call, Mcp_Name=encoded))
    assert status == 200 and "result" in ok
    assert error(*modern("ping"))[:2] == (404, -32601)  # 2026-07-28 has no ping
    assert error(*modern("resources/list"))[:2] == (404, -32601)
    status, code, err = error(*modern("tools/call", {"name": "rm_rf", "arguments": {}}))
    assert (status, code) == (200, -32602) and "div_render" in err["message"]


def test_tool_arguments_are_checked(server):
    def call(arguments):
        _s, _h, body = post(server, *modern("tools/call", {"name": "div_render", "arguments": arguments}))
        result = body["result"]
        assert result["isError"] is True
        return result["content"][0]["text"]

    assert "missing argument: template" in call({})
    assert "template: a string" in call({"template": 3})
    assert "max_output_chars: an integer" in call({"template": "page.tpl", "max_output_chars": "many"})
    assert "unknown argument: shell" in call({"template": "page.tpl", "shell": "ls"})
    assert "use_data_file: true or false" in call({"template": "page.tpl", "use_data_file": "yes"})


# ------------------------------------------------------------------ the legacy protocol
def test_legacy_initialize_and_calls(server):
    for asked, answered in (("2025-06-18", "2025-06-18"), ("2025-11-25", "2025-11-25"), ("2024-11-05", "2024-11-05"),
                            ("1999-01-01", "2025-11-25"), (MODERN, "2025-11-25")):
        status, headers, body = post(server, legacy("initialize", {
            "protocolVersion": asked, "capabilities": {}, "clientInfo": {"name": "old", "version": "0.1"}}))
        result = body["result"]
        assert status == 200 and result["protocolVersion"] == answered, asked
        assert result["serverInfo"]["name"] == "divide" and result["capabilities"] == {"tools": {"listChanged": False}}
        assert "resultType" not in result and "mcp-session-id" not in headers
    status, _h, body = post(server, legacy("notifications/initialized", ident=None))
    assert (status, body) == (202, None)
    assert post(server, legacy("ping"), headers={"MCP-Protocol-Version": "2025-06-18"})[2]["result"] == {}
    status, _h, body = post(server, legacy("tools/list"))  # no MCP-Protocol-Version: 2025-03-26, as the transport says
    assert status == 200 and len(body["result"]["tools"]) == 7 and "ttlMs" not in body["result"]
    status, _h, body = post(server, legacy("tools/call", {"name": "div_check", "arguments": {"template": "page.tpl"}}),
                            headers={"MCP-Protocol-Version": "2025-11-25"})
    assert status == 200 and body["result"]["structuredContent"]["errors"] == 0
    status, _h, body = post(server, legacy("tools/list"), headers={"MCP-Protocol-Version": "2031-01-01"})
    assert status == 400 and body["error"]["code"] == -32022
    status, _h, body = post(server, legacy("resources/list"), headers={"MCP-Protocol-Version": "2025-11-25"})
    assert status == 200 and body["error"]["code"] == -32601
    status, _h, body = post(server, legacy("server/discover"), headers={"MCP-Protocol-Version": "2025-11-25"})
    assert body["error"]["code"] == -32601 and "2026-07-28" in body["error"]["message"]
    assert server.clients["old"] == "0.1"


def test_invalid_requests(server):
    def bad(raw: bytes):
        status, _h, body = post(server, raw=raw)
        return status, body["error"]["code"]

    assert bad(b"{not json") == (400, -32700)
    assert bad("ñ".encode("latin-1")) == (400, -32700)
    assert bad(b'[{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}]') == (400, -32600)  # no batches
    assert bad(b'"tools/list"') == (400, -32600)
    assert bad(b'{"id": 1, "method": "tools/list"}') == (400, -32600)  # no "jsonrpc": "2.0"
    assert bad(b'{"jsonrpc": "2.0", "id": {"a": 1}, "method": "tools/list"}') == (400, -32600)
    status, _h, body = post(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": [1]})
    assert body["error"]["code"] == -32602
    status, _h, body = post(server, {"jsonrpc": "2.0", "id": 9, "result": {}})  # a response: nothing asked it
    assert (status, body) == (202, None)


def test_the_http_surface(server, monkeypatch):
    status, headers, _b = post(server, method="GET")
    assert status == 405 and headers["allow"] == "POST"
    assert post(server, method="DELETE")[0] == 405
    assert post(server, method="OPTIONS")[0] == 405  # no CORS: a browser cannot post JSON here
    assert post(server, legacy("tools/list"), path="/")[0] == 404
    assert post(server, legacy("tools/list"), path="/mcp/other")[0] == 404
    assert post(server, legacy("tools/list"), path="/mcp?x=1")[0] == 200
    assert post(server, legacy("tools/list"), headers={"Content-Type": "text/plain"})[0] == 415
    assert post(server, legacy("tools/list"), headers={"Accept": "text/html"})[0] == 406
    monkeypatch.setattr(mcp_http, "MAX_BODY", 100)
    status, _h, body = post(server, legacy("tools/call", {"name": "div_check", "arguments": {"template": "x" * 200}}))
    assert status == 413 and "up to 100" in body["error"]["message"]
    with socket.create_connection(("127.0.0.1", server.port), timeout=10) as raw:  # no Content-Length
        raw.sendall(b"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nContent-Type: application/json\r\n"
                    b"Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n" % server.port)
        assert raw.recv(200).startswith(b"HTTP/1.1 411")


# ------------------------------------------------------------------ guards
def test_host_and_origin_are_checked(server):
    port = server.port
    call = legacy("tools/list")
    for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"):
        assert post(server, call, headers={"Host": host})[0] == 200, host
    for host in (f"evil.example:{port}", f"127.0.0.1:{port + 1}", "127.0.0.1", f"192.168.1.10:{port}", ""):
        status, _h, body = post(server, call, headers={"Host": host})
        assert status == 403 and "Host" in body["error"]["message"], host
    assert post(server, call, headers={"Origin": "http://localhost:3000"})[0] == 200
    assert post(server, call, headers={"Origin": f"http://127.0.0.1:{port}"})[0] == 200
    for origin in ("https://evil.example", "null", f"http://evil.example:{port}"):
        status, _h, body = post(server, call, headers={"Origin": origin})
        assert status == 403 and "Origin" in body["error"]["message"], origin
    # DNS rebinding: a page of evil.example whose name now points to 127.0.0.1
    assert post(server, call, headers={"Host": f"evil.example:{port}", "Origin": f"http://evil.example:{port}"})[0] == 403


def test_the_token(tmp_path):
    token = load_token(create=True)
    path = mcp_http.token_path()
    assert len(token) >= 40 and path.read_text().strip() == token and load_token() == token
    if sys.platform != "win32":
        assert path.stat().st_mode & 0o777 == 0o600
    assert load_token(renew=True) != token
    token = load_token()
    srv = HttpServer(project(tmp_path), port=0, token=token)
    srv.start()
    try:
        call = legacy("tools/list")
        status, headers, _b = post(srv, call)
        assert status == 401 and headers["www-authenticate"].startswith("Bearer")
        assert post(srv, call, headers={"Authorization": "Bearer wrong"})[0] == 401
        assert post(srv, call, headers={"Authorization": f"Basic {token}"})[0] == 401
        assert post(srv, call, headers={"Authorization": f"Bearer {token}"})[0] == 200
        assert all(token not in line.text for line in srv.log)  # never logged
    finally:
        srv.stop()
    with pytest.raises(StartError, match="needs a token"):
        HttpServer(project(tmp_path / "b"), host="0.0.0.0", port=0)
    srv = HttpServer(project(tmp_path / "c"), host="0.0.0.0", port=0, token=token)
    srv.start()  # off loopback: any Host (a proxy may name it), the token always
    try:
        assert post(srv, legacy("tools/list"), headers={"Host": "divide.example"})[0] == 401
        assert post(srv, legacy("tools/list"), headers={"Host": "divide.example", "Authorization": f"Bearer {token}"})[0] == 200
    finally:
        srv.stop()


def test_connections_are_bounded(server, monkeypatch):
    monkeypatch.setattr(mcp_http, "MAX_CONNECTIONS", 2)
    idle = [socket.create_connection(("127.0.0.1", server.port), timeout=10) for _ in range(2)]
    try:
        time.sleep(0.3)
        with socket.create_connection(("127.0.0.1", server.port), timeout=10) as third:
            assert third.recv(100).startswith(b"HTTP/1.1 503")
    finally:
        for s in idle:
            s.close()
    for _ in range(50):
        if post(server, legacy("tools/list"))[0] == 200:
            break
        time.sleep(0.1)
    else:
        pytest.fail("the server did not take connections again")


# ------------------------------------------------------------------ life
def test_port_conflicts_stop_and_restart(tmp_path):
    root = project(tmp_path)
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen()
    try:
        srv = HttpServer(root, port=taken.getsockname()[1])
        with pytest.raises(StartError, match="in use"):
            srv.start()
        assert srv.state == "failed" and "in use" in srv.error and mcp_threads() == []
        srv.stop()  # stopping what never started is nothing
    finally:
        taken.close()
    port = free_port()
    srv = HttpServer(root, port=port)
    for _ in range(2):  # start, stop, start again on the same port
        srv.start()
        srv.start()  # a second Start while running: nothing
        assert srv.running and srv.alive() and sorted(mcp_threads()) == ["mcp-http", "mcp-loop"]
        assert post(srv, legacy("tools/list"))[0] == 200
        srv.stop()
        srv.stop()
        assert srv.state == "stopped" and mcp_threads() == []
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=2).close()
    assert "stopped" in [line.text for line in srv.log]


async def test_clients_at_once(tmp_path):
    from mcp import Client

    srv = HttpServer(project(tmp_path), port=0)
    srv.start()
    try:
        async def one(mode: str, n: int):
            async with Client(srv.url, mode=mode) as client:
                results = await asyncio.gather(*(client.call_tool("div_check", {"template": "page.tpl"}) for _ in range(n)))
                return [r.structured_content["template"] for r in results]

        answers = await asyncio.gather(one("legacy", 3), one(MODERN, 3), one("auto", 3),
                                       asyncio.to_thread(lambda: [post(srv, legacy("tools/list"))[0] for _ in range(5)]))
        assert answers[:3] == [["page.tpl"] * 3] * 3 and answers[3] == [200] * 5
        assert srv.requests >= 14 and srv.active == 0
    finally:
        await asyncio.to_thread(srv.stop)


def php_children(pid: int) -> list[str]:
    found = []
    for entry in Path("/proc").iterdir():
        try:
            if entry.name.isdigit() and int((entry / "stat").read_text().rsplit(")", 1)[1].split()[1]) == pid:
                found.append((entry / "cmdline").read_bytes().split(b"\0")[0].decode())
        except (OSError, IndexError, ValueError):
            continue
    return [c for c in found if Path(c).name.startswith("php")]


@needs_div
def test_closing_the_connection_cancels_the_call(tmp_path):
    root = project(tmp_path)
    (root / "slow.tpl").write_text("a(# sleep(8) #)b", encoding="utf-8")
    home = Path(os.environ["DIV_HOME"])  # the user's own setup is trusted: sleep may be called
    home.mkdir(parents=True, exist_ok=True)
    (home / "setup.json").write_text('{"php": {"allowed_functions": ["sleep"]}}', encoding="utf-8")
    srv = HttpServer(root, port=0)
    srv.start()
    linux = sys.platform.startswith("linux")
    try:
        body = json.dumps(legacy("tools/call", {"name": "div_render", "arguments": {"template": "slow.tpl"}})).encode()
        client = socket.create_connection(("127.0.0.1", srv.port), timeout=10)
        client.sendall(b"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nContent-Type: application/json\r\n"
                       b"Content-Length: %d\r\n\r\n%s" % (srv.port, len(body), body))
        for _ in range(100):  # php is running
            if srv.active and (not linux or php_children(os.getpid())):
                break
            time.sleep(0.05)
        assert srv.active == 1
        client.close()  # the client gives up: on HTTP, that is the cancellation
        for _ in range(60):
            if srv.active == 0 and (not linux or not php_children(os.getpid())):
                break
            time.sleep(0.05)
        assert srv.active == 0 and any("the client left" in line.text for line in srv.log)
        if linux:
            assert php_children(os.getpid()) == []
        started = time.monotonic()
        status, _h, answer = post(srv, legacy("tools/call", {"name": "div_render", "arguments": {"template": "page.tpl"}}))
        assert answer["result"]["structuredContent"]["output"] == "Hi Rafa!" and time.monotonic() - started < 6
    finally:
        srv.stop()


# ------------------------------------------------------------------ the IDE
async def test_options_mcp_server_in_the_ide(tmp_path):
    from mcp import Client
    from textual_vision.events import CommandMessage

    from divide.app import CM_MCP_SERVER, Divide
    from divide.ui.mcp import McpServerDialog, mcp_settings

    root = project(tmp_path)
    port = free_port()
    app = Divide(root, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.mcp_server is None  # never started unasked
        app.post_message(CommandMessage(CM_MCP_SERVER))
        for _ in range(40):
            await pilot.pause(0.05)
            dialog = next(iter(app.screen.query(McpServerDialog)), None)
            if dialog is not None and dialog.shown:
                break
        assert dialog is not None and "Stopped" in dialog.shown
        dialog.port_input.data = str(port)

        async def until(condition, what: str) -> None:
            for _ in range(100):
                await pilot.pause(0.05)
                if condition():
                    return
            pytest.fail(what)

        await pilot.press("alt+s")  # Start
        await until(lambda: app.mcp_server is not None and app.mcp_server.running, "the server did not start")
        url = f"http://127.0.0.1:{port}/mcp"
        assert app.mcp_server.url == url and app.mcp_server.root == root
        await until(lambda: url in dialog.shown, "the dialog did not show the address")
        assert mcp_settings()["port"] == port
        async with Client(url, mode="legacy") as client:
            assert (await client.call_tool("div_check", {"template": "page.tpl"})).is_error is False
        await until(lambda: app.mcp_server.clients and "none yet" not in dialog.shown, "the dialog did not show the client")

        await pilot.press("alt+o")  # Stop
        await until(lambda: app.mcp_server is None and mcp_threads() == [], "the server did not stop")
        await until(lambda: "Stopped" in dialog.shown, "the dialog did not say it stopped")

        taken = socket.socket()
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        try:
            dialog.port_input.data = str(taken.getsockname()[1])
            await pilot.press("alt+s")  # a port another program listens on
            await until(lambda: "in use" in dialog.shown, "the dialog did not say why")
            assert app.mcp_server is not None and app.mcp_server.state == "failed" and mcp_threads() == []
        finally:
            taken.close()
        dialog.port_input.data = str(port)
        await pilot.press("alt+s")
        await until(lambda: app.mcp_server is not None and app.mcp_server.running, "the server did not start again")
        await pilot.press("alt+s")  # Restart: a new server on the same port
        await pilot.pause(0.3)
        await until(lambda: app.mcp_server is not None and app.mcp_server.running, "the server did not restart")
        await pilot.press("escape")
        await pilot.pause()

        other = tmp_path / "other"
        other.mkdir()
        assert await app.open_folder(other)  # the server follows the project
        await until(lambda: app.mcp_server is not None and app.mcp_server.running and app.mcp_server.root == other.resolve(),
                    "the server did not follow the folder")
        server = app.mcp_server
    assert server.state == "stopped" and mcp_threads() == []  # divide ended: the server with it
    saved = config.load()["mcp"]
    assert saved == {"host": "127.0.0.1", "port": port, "autostart": False, "token": False}


async def test_start_with_divide(tmp_path):
    from divide.app import Divide

    root = project(tmp_path)
    port = free_port()
    config.set_value("mcp", {"host": "127.0.0.1", "port": port, "autostart": True, "token": False})
    app = Divide(root, [])
    async with app.run_test(size=(120, 40)) as pilot:
        for _ in range(100):
            await pilot.pause(0.05)
            if app.mcp_server is not None and app.mcp_server.running:
                break
        assert app.mcp_server is not None and app.mcp_server.url == f"http://127.0.0.1:{port}/mcp"
        assert post(app.mcp_server, legacy("tools/list"))[0] == 200
    assert mcp_threads() == []


# ------------------------------------------------------------------ other clients
TS_SDK = os.environ.get("MCP_TS_SDK")


@pytest.mark.skipif(not (TS_SDK and shutil.which("node") and (Path(TS_SDK) / "node_modules" / "@modelcontextprotocol" / "sdk").is_dir()),
                    reason="needs node and MCP_TS_SDK (a folder with node_modules/@modelcontextprotocol/sdk)")
@pytest.mark.parametrize("with_token", [False, True])
def test_the_typescript_sdk_client(tmp_path, with_token):
    token = load_token(create=True) if with_token else None
    srv = HttpServer(project(tmp_path), port=0, token=token)
    srv.start()
    try:
        script = Path(__file__).parent / "clients" / "ts_client.mjs"
        args = ["node", str(script), srv.url] + ([token] if token else [])
        done = subprocess.run(args, capture_output=True, text=True, timeout=120, env={**os.environ, "MCP_TS_SDK": TS_SDK})
        assert done.returncode == 0, done.stderr
        seen = json.loads(done.stdout.strip().splitlines()[-1])
    finally:
        srv.stop()
    assert seen["protocolVersion"] == "2025-11-25" and seen["sessionId"] is None
    assert seen["server"]["name"] == "divide" and len(seen["tools"]) == 7 and seen["project"] == "proj"
    assert seen["badError"] is True and "outside the project" in seen["badText"]
