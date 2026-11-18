"""The web server (php -S) and debugging its requests with Xdebug.

As in test_run.py, the debugger tests need Xdebug (php.ini or DIVIDE_XDEBUG).
"""

import asyncio
import json
import socket
from pathlib import Path

import pytest

from divide.app import Divide
from divide.run.server import ServerError, WebServer, check_address, server_messages
from divide.ui.dialogs import FileDialog, shown_path
from divide.ui.webserver import ServerLogWindow, WebServerDialog

from test_run import XDEBUG, needs_php, needs_xdebug, settle, until

PAGE = """<?php
$name = $_GET['name'] ?? 'world';
$greeting = "Hello $name";
echo $greeting . "\\n";
echo $missing;
echo "bye\\n";
"""


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    settings = {"lsp": {"php": "off"}}
    if XDEBUG:
        settings["xdebug"] = XDEBUG
    (home / "divide").mkdir(parents=True)
    (home / "divide" / "config.json").write_text(json.dumps(settings), encoding="utf-8")


def free_address() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"127.0.0.1:{s.getsockname()[1]}"


async def get(address: str, path: str) -> str:
    host, _, port = address.rpartition(":")
    reader, writer = await asyncio.open_connection(host, int(port))
    writer.write(f"GET {path} HTTP/1.0\r\nHost: {address}\r\n\r\n".encode())
    await writer.drain()
    answer = (await reader.read()).decode()
    writer.close()
    return answer.split("\r\n\r\n", 1)[-1]


def site(tmp_path: Path) -> Path:
    root = tmp_path / "public"
    root.mkdir()
    (root / "index.php").write_text(PAGE, encoding="utf-8")
    return root


def test_server_log_messages_and_addresses(tmp_path):
    log = (
        "[Sat Nov 14 14:53:53 2026] PHP 8.5.4 Development Server (http://127.0.0.1:8000) started\n"
        "[Sat Nov 14 14:53:53 2026] 127.0.0.1:55766 Accepted\n"
        "[Sat Nov 14 14:53:54 2026] PHP Warning:  Undefined variable $x in /w/index.php on line 4\n"
        "[Sat Nov 14 14:53:54 2026] 127.0.0.1:55766 [200]: GET /index.php\n"
        "[Sat Nov 14 14:53:55 2026] PHP Fatal error:  Uncaught Exception: boom in /w/a.php:3\n"
        "Stack trace:\n#0 {main}\n  thrown in /w/a.php on line 3\n"
        "[Sat Nov 14 14:53:55 2026] 127.0.0.1:55770 Closing\n"
    )
    found = server_messages(log)
    assert [(m.level, m.text, m.file, m.line) for m in found] == [
        ("warning", "Warning: Undefined variable $x", Path("/w/index.php"), 4),
        ("error", "Fatal error: Uncaught Exception: boom", Path("/w/a.php"), 3),
    ]
    assert check_address("127.0.0.1:8000") is None and check_address("localhost:80") is None
    assert check_address("8000") and check_address("host:") and check_address("h:99999")

    root = tmp_path / "public"
    server = WebServer("0.0.0.0:8080", root)
    assert server.url == "http://127.0.0.1:8080/"
    assert server.url_of(root / "index.php") == "http://127.0.0.1:8080/"
    assert server.url_of(root / "shop" / "cart.php") == "http://127.0.0.1:8080/shop/cart.php"
    assert server.serves(root / "a.php") and not server.serves(tmp_path / "cli.php")
    routed = WebServer("127.0.0.1:8080", root, tmp_path / "router.php")
    assert routed.url_of(root / "a.php") == "http://127.0.0.1:8080/" and routed.serves(tmp_path / "lib.php")


@needs_php
async def test_serves_without_debugger_and_reports_a_taken_port(tmp_path):
    root = site(tmp_path)
    address = free_address()
    server = WebServer(address, root)
    await server.start()
    try:
        assert server.running and not server.debugging
        assert (await get(address, "/?name=web")).startswith("Hello web\n")
        assert await soon(lambda: "GET /?name=web" in server.log)
        other = WebServer(address, root)
        with pytest.raises(ServerError, match="Address already in use"):
            await other.start()
        assert not other.running
    finally:
        await server.stop()
    assert not server.running


async def soon(pred) -> bool:  # the log arrives a moment after the answer
    for _ in range(150):
        if pred():
            return True
        await asyncio.sleep(0.02)
    return pred()


async def test_folder_dialog(tmp_path):
    project = tmp_path / "site"
    (project / "public" / "css").mkdir(parents=True)
    (project / "public" / "index.php").write_text("<?php\n", encoding="utf-8")
    app = Divide(project, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        dialog = FileDialog("Folder", project, folders=True)
        app.run_worker(app.run_dialog(dialog))
        await settle(pilot)
        assert dialog._entries == ["..", "public/"]
        dialog.accept("public")
        await settle(pilot)
        assert dialog._entries == ["..", "css/"] and dialog.input.data == "."
        dialog.accept(".")
        await settle(pilot)
        assert dialog.chosen == (project / "public").resolve()


@needs_xdebug
async def test_debug_web_requests(tmp_path, monkeypatch):
    root = site(tmp_path)
    page = root / "index.php"
    address = free_address()
    opened: list[str] = []
    app = Divide(tmp_path, [page])
    monkeypatch.setattr(app, "open_url", lambda url, **kw: opened.append(url))
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        page = page.resolve()

        # Run > Web server: the dialog, then the server and its log window
        app.run_command(app_command("CM_WEB_SERVER"))
        assert await until(pilot, lambda: isinstance(getattr(app.screen, "dialog", None), WebServerDialog))
        dialog = app.screen.dialog
        assert dialog.root_input.data == shown_path(tmp_path) and "Xdebug found" in dialog.hint  # (~: Windows keeps temp in the home)
        dialog.address_input.data = address
        dialog.root_input.data = "public"  # relative to the project
        await pilot.press("enter")
        assert await until(pilot, lambda: app.serving, tries=300)
        assert app.web.root == root.resolve() and app.web.debugging
        assert opened == [f"http://{address}/"]  # "Open in the browser" was on
        assert isinstance(app.server_log_window(), ServerLogWindow)
        saved = json.loads((tmp_path / "config" / "divide" / "config.json").read_text(encoding="utf-8"))["web"][str(tmp_path)]
        assert saved["address"] == address and saved["root"] == str(root.resolve())

        # no breakpoint: a request runs through
        assert (await get(address, "/?name=fast")).startswith("Hello fast\n")
        assert app.session is None

        # a breakpoint on 'echo $greeting': the request pauses there (the browser waits)
        assert app.active_editor() is app.window_for(page)  # the log opened below it
        ed = app.active_editor().editor
        ed.move_cursor((3, 0))
        await pilot.press("ctrl+f8")
        request = asyncio.ensure_future(get(address, "/index.php?name=Ada"))
        assert await until(pilot, lambda: app.paused and ed.execution_row == 3, tries=300)
        assert app.session.request == "GET /index.php?name=Ada"
        app.update_status()
        assert "(GET /index.php?name=Ada)" in app.status_line._hint_text
        assert (await app.session.evaluate("$greeting")).value == "'Hello Ada'"
        assert not request.done()

        # F8 steps in the request; Ctrl+F9 lets it finish: the browser gets the page
        await pilot.press("f8")
        assert await until(pilot, lambda: app.paused and ed.execution_row == 4)
        await pilot.press("ctrl+f9")
        assert await until(pilot, lambda: app.session is None and request.done())
        assert request.result().startswith("Hello Ada\n") and request.result().rstrip().endswith("bye")
        assert ed.execution_row is None

        # PHP's warning from the log goes to Messages, with its place
        assert await until(pilot, lambda: "Undefined variable $missing" in app.web.log)
        await settle(pilot, 10)
        items = [i for i in app.run_items(None) if i.path is not None]
        assert items and items[0].path == page and "Undefined variable $missing" in items[0].text

        # F8 with no request paused: the next one stops on its first line; Ctrl+F2 ends it
        app.raise_window(app.window_for(page))
        ed.move_cursor((3, 0))
        await pilot.press("ctrl+f8")  # the breakpoint off
        assert app.breakpoints == {}
        await pilot.press("f8")
        assert app.web_next == ("step_into", None) and "the next request stops" in app.web_hint()
        request = asyncio.ensure_future(get(address, "/"))
        assert await until(pilot, lambda: app.paused and ed.execution_row == 1, tries=300)
        await pilot.press("ctrl+f2")
        assert await until(pilot, lambda: app.session is None and request.done())
        assert "Hello" not in request.result()  # stopped before it printed
        assert app.web_next is None

        # Ctrl+F9 on a page the server serves opens it in the browser
        await pilot.press("ctrl+f9")
        await settle(pilot)
        assert opened[-1] == f"http://{address}/" and app.session is None

        # Run > Web server again: Stop
        app.run_command(app_command("CM_WEB_SERVER"))
        assert await until(pilot, lambda: hasattr(getattr(app.screen, "dialog", None), "_buttons"))
        await pilot.press("s")
        assert await until(pilot, lambda: app.web is None)
        assert "(stopped)" in app.server_log_window().title


def app_command(name: str) -> int:
    import divide.app as module

    return getattr(module, name)
