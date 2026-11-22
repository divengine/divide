"""Screenshots of the wiki manual, taken from the real app on examples/shop.

    .venv/bin/python tools/wiki_shots.py --out ../divide.wiki/images [shot ...]

Each shot drives divide with Textual's pilot, exports an SVG and converts it
to PNG with rsvg-convert. Needs:

- a Div engine: --engine or DIVIDE_DIV_PHP (a composer vendor/autoload.php, or
  a Div checkout's src/div.php with its vendor/ installed), and php;
- rsvg-convert (librsvg) and the Liberation Mono font.

Two fixes are applied to the SVG so that it rasterises like the terminal:
Liberation Mono advances 12.0px per cell where Textual lays out 12.2px, hence
letter-spacing 0.2px; and librsvg drops a text span's leading no-break space,
hence plain spaces with xml:space="preserve".

Shots never save files: the example project is left as it is.
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "shop"
SIZE = (120, 34)
PALETTE = "free-pascal"  # the manual's pictures, unless a shot shows another theme
OUT: Path = Path()
SVG_DIR: Path = Path()

LANGUAGE = os.environ.setdefault("DIVIDE_LANGUAGE", "en")  # the manual is in English (es: help-divide-es)
# the menu hotkeys the shots press, in the interface's language
_KEYS = {
    "en": {"run": "alt+r", "window": "alt+w", "options": "alt+o", "tools": "alt+t", "help": "alt+h",
           "help-search": "s", "language": "g", "help-query": "include templ", "new-file": "f", "yes": "y",
           "div-setup": "e", "composer": "c", "marks": "f", "tile": "t", "cascade": "a", "colors": "c", "git": "alt+g", "file": "alt+f", "mcp": "m"},
    "es": {"run": "alt+j", "window": "alt+v", "options": "alt+o", "tools": "alt+h", "help": "alt+y",
           "help-search": "b", "language": "i", "help-query": "incluir plantil", "new-file": "n", "yes": "s",
           "div-setup": "f", "composer": "c", "marks": "m", "tile": "s", "cascade": "c", "colors": "c", "git": "alt+g", "file": "alt+a", "mcp": "p"},
}


def key(name: str) -> str:
    return _KEYS.get(LANGUAGE, _KEYS["en"])[name]

from divide.app import Divide  # noqa: E402
from divide.ui.progress import ProgressScreen  # noqa: E402

def rasterise(svg: str, png: Path, work: Path) -> None:
    """Textual's SVG screenshot as a PNG, drawn as the terminal draws it (see above)."""
    svg = re.sub(r'font-family:[^;"]*', "font-family: Liberation Mono; letter-spacing: 0.2px", svg)
    # rsvg drops a span's leading no-break space: plain spaces, preserved
    svg = svg.replace("&#160;", " ").replace("<svg ", '<svg xml:space="preserve" ', 1)
    tmp = work / (png.stem + ".svg")
    tmp.write_text(svg, encoding="utf-8")
    subprocess.run(["rsvg-convert", str(tmp), "-o", str(png)], check=True)


def save(app, name):
    svg = app.export_screenshot(title="divide")
    if os.environ.get("DIVIDE_SHOT_KEEP_SVG"):
        (Path(os.environ["DIVIDE_SHOT_KEEP_SVG"]) / f"{name}.svg").write_text(svg, encoding="utf-8")
    rasterise(svg, OUT / f"{name}.png", SVG_DIR)
    print("saved", name)

async def settle(pilot, n=6):
    for _ in range(n):
        await pilot.pause()

async def until(pilot, pred, tries=100):
    for _ in range(tries):
        if pred():
            return
        await pilot.pause(0.05)
    raise SystemExit("timed out waiting for the app")

async def close_box(pilot, app):
    """Wait for the progress box's verdict and close it, as a key would."""
    await until(pilot, lambda: isinstance(app.screen, ProgressScreen) and not app.screen.dialog.running, tries=200)
    await pilot.press("escape")
    await settle(pilot)

def shot(fn):
    SHOTS.append(fn)
    return fn
SHOTS = []

@shot
async def hero():
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=(150, 36)) as pilot:
        await settle(pilot)
        app.toggle_project(); await settle(pilot)
        tree = app.project_window().project_tree
        await tree.reveal(DEMO / "components" / "card.tpl"); await settle(pilot)
        app.raise_window(app.window_for(DEMO / "index.tpl")); await settle(pilot)
        await pilot.press("ctrl+f9")
        await close_box(pilot, app)
        await until(pilot, lambda: app.output_window() is not None and app.output_window().view.text)
        app.raise_window(app.window_for(DEMO / "index.tpl"))
        app.window_for(DEMO / "index.tpl").editor.move_cursor((10, 4))
        await settle(pilot)
        save(app, "hero")

async def typing_shot(name, keys, cursor=(10, 31), explicit=False):
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        ed = app.window_for(DEMO / "index.tpl").editor
        ed.move_cursor(cursor)
        await pilot.press("enter", *keys)
        await settle(pilot, 10)
        save(app, name)

@shot
async def completion_vars():
    await typing_shot("completion-variables", list("<b>{$"))

@shot
async def completion_tags():
    await typing_shot("completion-tags", ["{", "ctrl+@"])

@shot
async def completion_includes():
    await typing_shot("completion-includes", list("{% "))

@shot
async def diagnostics():
    app = Divide(DEMO, [DEMO / "checkout.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        ed = app.window_for(DEMO / "checkout.tpl").editor
        await until(pilot, lambda: ed.include_targets)
        await pilot.press("alt+f9"); await close_box(pilot, app)
        app.raise_window(app.window_for(DEMO / "checkout.tpl"))
        ed.move_cursor((6, 3)); await settle(pilot)
        save(app, "diagnostics")

@shot
async def data_tree():
    app = Divide(DEMO, [DEMO / "index.json"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+t"); await settle(pilot)
        win = app.active_window(); tree = win.json_tree
        for node in list(tree.root.children):
            node.expand()
        await settle(pilot)
        first = tree.root.children[3].children[0]
        first.expand(); await settle(pilot)
        tree.move_cursor(first.children[1]); await settle(pilot)
        save(app, "data-tree")
        await pilot.press("enter"); await settle(pilot)
        save(app, "data-tree-edit")

@shot
async def data_code():
    app = Divide(DEMO, [DEMO / "index.json"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        ed = app.active_editor().editor
        ed.move_cursor((5, 47)); await pilot.press("backspace"); await settle(pilot)
        save(app, "data-code")

@shot
async def project():
    app = Divide(DEMO, [])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        app.open_file(DEMO / "components" / "card.tpl"); await settle(pilot)
        tree = app.project_window().project_tree
        await tree.reveal(DEMO / "layout" / "header.tpl")
        await tree.reveal(DEMO / "components" / "card.tpl"); await settle(pilot)
        app.raise_window(app.project_window()); tree.focus(); await settle(pilot)
        await pilot.press("alt+f10"); await settle(pilot)
        save(app, "project-menu")
        await pilot.press(key("new-file")); await settle(pilot)
        await pilot.press(*"badge.tpl"); await settle(pilot)
        save(app, "project-new-file")

@shot
async def marks():
    """Options > File type marks in the project window (set on the tree only: no config written)."""
    app = Divide(DEMO, [])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        tree = app.project_window().project_tree
        await tree.reveal(DEMO / "components" / "card.tpl")
        await tree.reveal(DEMO / "layout" / "header.tpl"); await settle(pilot)
        tree.set_icons("marks"); await settle(pilot)
        save(app, "project-marks")

@shot
async def menus():
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        await pilot.press(key("run")); await settle(pilot)
        save(app, "menu-run")
        await pilot.press("escape", "alt+d"); await settle(pilot)
        save(app, "menu-debug")

@shot
async def find():
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        ed = app.active_editor().editor
        ed.move_cursor((10, 16)); await settle(pilot)
        await pilot.press("ctrl+r"); await settle(pilot)
        save(app, "replace")

@shot
async def turbo_c():
    """Window > Tile in the manual's theme, then Turbo C's colours with the Window menu."""
    for palette in (None, "turbo-c"):
        app = Divide(DEMO, [DEMO / "index.tpl", DEMO / "components" / "card.tpl"], palette=palette)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            app.toggle_project(); await settle(pilot)
            app.desktop.tile(); await settle(pilot)
            if palette is None:
                save(app, "window-tile")
                continue
            await pilot.press(key("window")); await settle(pilot)
            save(app, "palette-turbo-c")

@shot
async def colors():
    """Options > Colors previewing modern-dark, then the desktop in modern-dark and turbo-pascal
    (free-pascal is in every other picture)."""
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        await pilot.press(key("options"), "c"); await settle(pilot)
        await pilot.press("m"); await settle(pilot, 10)  # the whole desktop previews it
        save(app, "colors-dialog")
        await pilot.press("escape"); await settle(pilot)
    for name in ("modern-dark", "turbo-pascal"):
        app = Divide(DEMO, [DEMO / "index.tpl", DEMO / "components" / "card.tpl"], palette=name)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            app.toggle_project(); await settle(pilot)
            app.desktop.tile(); await settle(pilot, 10)
            save(app, f"theme-{name}")

@shot
async def open_file():
    """File > Open as Turbo Pascal's, then the history of its name line."""
    from divide.ui import history
    for name in ("components/card.tpl", "*.php", "index.tpl"):
        history.add("file", name)  # the temporary config of the shots
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        await pilot.press("f3"); await settle(pilot)
        await pilot.press("tab", "down", "down"); await settle(pilot)
        save(app, "open-file")
        await pilot.press("shift+tab", "down"); await settle(pilot)
        save(app, "open-history")

@shot
async def palette():
    """Go to file (Ctrl+P), the command palette (a > in it) and Find in files with its window."""
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+p"); await settle(pilot)
        await pilot.press(*"card"); await settle(pilot)
        save(app, "go-to-file")
        await pilot.press("ctrl+a", ">", *"run"); await settle(pilot)
        save(app, "command-palette")
        await pilot.press("escape"); await settle(pilot)
        await pilot.press("shift+f2"); await settle(pilot)
        await pilot.press("ctrl+a", *"product"); await settle(pilot)
        save(app, "find-in-files-dialog")
        await pilot.press("enter")
        await until(pilot, lambda: app.find_results_window() is not None)
        await settle(pilot)
        await pilot.press("down"); await settle(pilot)
        save(app, "find-in-files")


@shot
async def dialector():
    app = Divide(DEMO, [DEMO / "erb.dialect"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        await pilot.press(key("tools"), "d"); await settle(pilot)
        win = app.active_window()
        await until(pilot, lambda: win.verdict is not None)
        await pilot.press("down", "down", "down", "down"); await settle(pilot)  # Loops and iterations
        save(app, "dialector")
        await pilot.press("enter"); await settle(pilot, 10)
        await pilot.pause(1.2); await settle(pilot)
        save(app, "dialector-section")
        await pilot.press("escape"); await settle(pilot)
        await pilot.press("alt+f10"); await settle(pilot)
        save(app, "dialector-menu")


@shot
async def translate():
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        await pilot.press(key("tools"), "t"); await settle(pilot)
        dialog = app.screen.dialog
        await until(pilot, lambda: dialog.text is not None)
        await pilot.click(dialog.target_input)
        await pilot.press(*"erb.dialect", "enter")
        await until(pilot, lambda: "<% each" in (dialog.text or ""))
        await settle(pilot)
        save(app, "translate")



@shot
async def help():
    app = Divide(DEMO, [DEMO / "erb.dialect"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        await pilot.press(key("tools"), "d"); await settle(pilot)
        win = app.active_window()
        await until(pilot, lambda: win.verdict is not None)
        await pilot.press("f1"); await settle(pilot, 10)
        await pilot.press("tab", "tab"); await settle(pilot)
        save(app, "help")
        await pilot.press("shift+f1"); await settle(pilot, 10)
        save(app, "help-index")
        app.help_window().open("div:02.10 Lists (loops)"); await settle(pilot, 10)
        save(app, "help-div")
        app.help_window().open("_Books"); await settle(pilot, 10)
        save(app, "help-books")
        await pilot.press(key("help"), key("help-search")); await settle(pilot)
        await pilot.press(*key("help-query")); await settle(pilot)
        await pilot.press("down"); await settle(pilot)
        save(app, "help-search")


@shot
async def php():
    app = Divide(DEMO, [DEMO / "index.php"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot, 10)
        ed = app.active_editor().editor
        ed.move_cursor((13, 0))
        ed.insert("$data['cart'] = ['items' => count($data['products'])\n")
        await until(pilot, lambda: bool(ed.diagnostics))
        await pilot.press("alt+f9"); await close_box(pilot, app)
        app.raise_window(app.window_for(DEMO / "index.php"))
        app.window_for(DEMO / "index.php").editor.move_cursor((13, 20))
        await settle(pilot, 6)
        save(app, "php")


@shot
async def outline():
    """Search > Outline on Div's own class (needs composer install in examples/shop)."""
    div = DEMO / "vendor" / "divengine" / "div" / "src" / "div.php"
    if not div.exists():
        print("skipped outline: composer install in examples/shop")
        return
    app = Divide(DEMO, [div])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot, 10)
        await pilot.press("ctrl+o")
        await settle(pilot)
        window = app.outline_window()
        index = next(i for i, line in enumerate(window.lines) if "parseMatches(" in line)
        window.focus_row(index)
        await pilot.press("enter")
        await settle(pilot)
        app.raise_window(window)
        await settle(pilot)
        save(app, "outline")


@shot
async def outline_tpl():
    """Search > Outline on the shop's home page, on the products loop."""
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot, 10)
        await pilot.press("ctrl+o")
        await settle(pilot)
        window = app.outline_window()
        index = next(i for i, line in enumerate(window.lines) if "[$products]" in line)
        window.focus_row(index)
        await pilot.press("enter")
        await settle(pilot)
        app.raise_window(window)
        await settle(pilot)
        save(app, "outline_tpl")


@shot
async def lsp():
    """Completion and signatures from a real language server, on Div's classes:
    DIVIDE_SHOT_LSP="name command…" (for example "phpactor phpactor language-server"),
    with `composer install` done in examples/shop; skipped without it."""
    spec = os.environ.get("DIVIDE_SHOT_LSP", "").split()
    if len(spec) < 2:
        print("skipped lsp: set DIVIDE_SHOT_LSP")
        return
    name, command = spec[0], spec[1:]
    import json
    config_home = Path(tempfile.mkdtemp())
    (config_home / "divide").mkdir()
    (config_home / "divide" / "config.json").write_text(
        json.dumps({"palette": PALETTE, "lsp": {"php": name}, "lsp_commands": {name: command}}), encoding="utf-8")
    old = os.environ.get("XDG_CONFIG_HOME")
    os.environ["XDG_CONFIG_HOME"] = str(config_home)
    try:
        app = Divide(DEMO, [DEMO / "index.php"])
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 10)
            await until(pilot, lambda: app.lsp_session("php") is not None, tries=600)
            await settle(pilot, 10)
            await until(pilot, lambda: not app.lsp_working, tries=1200)  # indexing
            ed = app.active_editor().editor
            # completion of a Div method, with its documentation beside the list
            ed.move_cursor((16, len("echo new div('index.tpl', $data);")))
            ed.insert("\n$tpl = new div('index.tpl', $data);\n$tpl->")
            await settle(pilot, 4)
            await pilot.press("p", "a", "r")
            await until(pilot, lambda: ed.completing and ed._doc is not None and ed._doc.display, tries=400)
            await settle(pilot, 6)
            save(app, "lsp")
            # the signature over the line, the parameter being typed marked
            await pilot.press("escape")
            ed.insert("se(")
            await until(pilot, lambda: ed.signature_shown, tries=200)
            await pilot.press("t", "r", "u", "e", ",", "space")
            await until(pilot, lambda: ed.signature_shown and ed._signature.mark is not None and ed._signature.mark[1] > 20, tries=200)
            await settle(pilot, 6)
            save(app, "lsp-signature")
            await app.lsp_stop_all()
    finally:
        if old is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = old


@shot
async def render_box():
    """The progress box of Ctrl+F9 on a template, with its verdict."""
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot, 10)
        await pilot.press("ctrl+f9")
        await until(pilot, lambda: isinstance(app.screen, ProgressScreen) and not app.screen.dialog.running, tries=200)
        await settle(pilot, 6)
        save(app, "render-box")


@shot
async def progress_running():
    """The progress box while a job runs and cannot say how far it is: the block going back and forth."""
    import asyncio
    from divide.ui.progress import ProgressDialog, run_with_progress
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        dialog = ProgressDialog("Rendering", [("Template", "index.tpl"), ("Data", "index.json"), ("Engine", "Div 6.1.2")])
        never = asyncio.Event()
        app.run_worker(run_with_progress(app, dialog, never.wait(), lambda r: ("Success", True, [])))
        await until(pilot, lambda: dialog.is_mounted)
        await pilot.pause(1.2)
        dialog.rows["Time"] = "1.2 s"  # the picture's own clock
        dialog._phase = 14
        dialog._show()
        await settle(pilot)
        save(app, "progress-running")
        never.set()

@shot
async def run_php():
    """Ctrl+F9 on a PHP script: the box, the output behind it (needs composer install in examples/shop)."""
    if not (DEMO / "vendor" / "autoload.php").is_file():
        print("skipped run_php: composer install in examples/shop")
        return
    app = Divide(DEMO, [DEMO / "index.php"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot, 10)
        await pilot.press("ctrl+f9")
        await until(pilot, lambda: isinstance(app.screen, ProgressScreen) and not app.screen.dialog.running, tries=200)
        await settle(pilot, 6)
        save(app, "run-php")


@shot
async def debug():
    """The debugger paused on a breakpoint, with Watches and the Call stack:
    DIVIDE_SHOT_XDEBUG=path/xdebug.so (or Xdebug in php.ini) and composer install in examples/shop."""
    import json
    xdebug = os.environ.get("DIVIDE_SHOT_XDEBUG", "")
    if not (DEMO / "vendor" / "autoload.php").is_file():
        print("skipped debug: composer install in examples/shop")
        return
    config_home = Path(os.environ["XDG_CONFIG_HOME"])
    (config_home / "divide").mkdir(parents=True, exist_ok=True)
    (config_home / "divide" / "config.json").write_text(json.dumps({"palette": PALETTE, "xdebug": xdebug or None}), encoding="utf-8")
    app = Divide(DEMO, [DEMO / "index.php"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot, 10)
        ed = app.active_editor().editor
        ed.move_cursor((15, 0))  # echo new div(...)
        await pilot.press("ctrl+f8")
        await pilot.press("f8")
        await until(pilot, lambda: app.paused, tries=400)
        await pilot.press("ctrl+f9")
        await until(pilot, lambda: app.paused and ed.execution_row == 15, tries=400)
        app.watches.append("count($data['products'])")
        app.show_watches()
        app.show_call_stack()
        await app.refresh_debug_windows()
        app.raise_window(app.window_for(DEMO / "index.php"))
        await settle(pilot, 8)
        save(app, "debug")
        await app.debug_reset()

@shot
async def web():
    """Run > Web server, then a request of php -S paused on a breakpoint
    (same needs as the debug shot)."""
    import json
    import socket
    from divide.ui.webserver import WebServerDialog
    xdebug = os.environ.get("DIVIDE_SHOT_XDEBUG", "")
    if not (DEMO / "vendor" / "autoload.php").is_file():
        print("skipped web: composer install in examples/shop")
        return
    config_home = Path(os.environ["XDG_CONFIG_HOME"])
    (config_home / "divide").mkdir(parents=True, exist_ok=True)
    (config_home / "divide" / "config.json").write_text(json.dumps({"palette": PALETTE, "xdebug": xdebug or None}), encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = Divide(DEMO, [DEMO / "index.php"])
    app.open_url = lambda url, **kw: None  # no browser in a screenshot
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot, 10)
        ed = app.active_editor().editor
        await pilot.press(key("run"), "w")
        await until(pilot, lambda: isinstance(getattr(app.screen, "dialog", None), WebServerDialog), tries=200)
        app.screen.dialog.address_input.data = "localhost:8000"
        await settle(pilot)
        save(app, "web-server-dialog")
        app.screen.dialog.address_input.data = f"127.0.0.1:{port}"
        await pilot.press("enter")
        await until(pilot, lambda: app.serving, tries=200)
        ed.move_cursor((13, 0))  # $data['today'] = ...
        await pilot.press("ctrl+f8")
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /?page=2 HTTP/1.0\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        await until(pilot, lambda: app.paused, tries=400)
        await settle(pilot, 10)
        app._web_tick()
        await settle(pilot, 4)
        save(app, "web-debug")
        await pilot.press("ctrl+f9")
        await reader.read()
        writer.close()
        await app.web_stop()

@shot
async def mcp():
    """Options > MCP server, running, after an agent's first calls. The server listens on a free
    port; the picture shows the default one, 8765 (another divide may be using it)."""
    import http.client
    import json
    import socket
    from divide.ui.mcp import McpServerDialog
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot, 10)
        await pilot.press(key("options"), key("mcp"))
        await until(pilot, lambda: isinstance(getattr(app.screen, "dialog", None), McpServerDialog), tries=200)
        dialog = app.screen.dialog
        dialog.port_input.data = str(port)
        await pilot.press("enter")
        await until(pilot, lambda: app.mcp_server is not None and app.mcp_server.running, tries=200)

        def agent() -> None:  # what a coding agent asks first
            for body in ({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                             "protocolVersion": "2025-11-25", "capabilities": {},
                             "clientInfo": {"name": "coding-agent", "version": "1.0"}}},
                         {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                         {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                          "params": {"name": "div_check", "arguments": {"template": "index.tpl"}}}):
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
                conn.request("POST", "/mcp", json.dumps(body), {"Content-Type": "application/json"})
                conn.getresponse().read()
                conn.close()

        await asyncio.to_thread(agent)
        app.mcp_server.port = 8765  # shown as the default: no request comes after this
        dialog.port_input.data = "8765"
        dialog.show_state()
        await settle(pilot, 6)
        save(app, "mcp-server")
        await app.mcp_stop()

@shot
async def flow():
    """Run > Run on the Runner Flows of examples/runner (composer install there), in a copy of it
    (the checkpoints go to its .div/runner/): the Run Flow dialog before the first run, the paused
    run's report, the dialog with that paused run saved; then, in a new window layout, a run that
    fails (invoice.yml without its function root) in Output and Messages."""
    import tempfile as _tempfile
    from divide.ui.flow import FlowDialog
    example = ROOT / "examples" / "runner"
    if not (example / "vendor" / "divengine" / "runner" / "bin" / "run.php").is_file():
        print("skipped flow: composer install in examples/runner")
        return
    with _tempfile.TemporaryDirectory() as work:
        root = Path(work) / "runner"
        shutil.copytree(example, root, ignore=shutil.ignore_patterns("*.context.json", ".div"))
        flow = root / "flows" / "order.yml"
        app = Divide(root, [flow])
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 10)
            await pilot.press("ctrl+f9")
            await until(pilot, lambda: isinstance(getattr(app.screen, "dialog", None), FlowDialog), tries=200)
            dialog = app.screen.dialog
            dialog.context_input.data = "order.json"
            dialog.root_input.data = "functions"
            dialog.root_input.focus()
            await settle(pilot, 6)
            save(app, "run-flow-new")
            await pilot.press("enter")
            await until(pilot, lambda: app.output_window() is not None and "approval.ask" in app.output_window().view.text, tries=400)
            await settle(pilot, 4)
            await pilot.press("escape")  # the progress box
            await settle(pilot, 4)
            save(app, "run-flow")
            app.raise_window(app.window_for(flow))
            await settle(pilot)
            await pilot.press("ctrl+f9")
            await until(pilot, lambda: isinstance(getattr(app.screen, "dialog", None), FlowDialog), tries=200)
            await settle(pilot, 6)
            save(app, "run-flow-dialog")
            await pilot.press("escape")
        invoice = root / "flows" / "invoice.yml"
        app = Divide(root, [invoice])
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 10)
            await pilot.press("ctrl+f9")
            await until(pilot, lambda: isinstance(getattr(app.screen, "dialog", None), FlowDialog), tries=200)
            await pilot.press("enter")  # no function root: billing:total is not found
            await until(pilot, lambda: app.messages_window() is not None and app.output_window() is not None
                        and "State: error" in app.output_window().view.text, tries=400)
            await settle(pilot, 4)
            await pilot.press("escape")  # the progress box
            await settle(pilot, 6)
            save(app, "run-flow-error")

@shot
async def flowmodel():
    """Ctrl+T on a Runner Flow of examples/runner (composer install there), in a copy of it: the Flow
    window on approval.ask (its attributes and where they lead), the Step dialog, then a Flow with a
    missing target and a missing function in the tree and in Messages (Alt+F9)."""
    import tempfile as _tempfile
    from divide.ui.flow import save_flow_settings
    from divide.ui.flowmodel import FlowWindow, StepDialog
    example = ROOT / "examples" / "runner"
    if not (example / "vendor" / "divengine" / "runner" / "bin" / "run.php").is_file():
        print("skipped flowmodel: composer install in examples/runner")
        return
    with _tempfile.TemporaryDirectory() as work:
        root = Path(work) / "runner"
        shutil.copytree(example, root, ignore=shutil.ignore_patterns("*.context.json", ".div"))
        flow = root / "flows" / "order.yml"
        save_flow_settings(flow.resolve(), {"context": "order.json", "root": "functions", "save": ""})
        app = Divide(root, [flow])
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 10)
            await pilot.press("ctrl+t")
            await until(pilot, lambda: isinstance(app.active_window(), FlowWindow), tries=200)
            window = app.active_window()
            await until(pilot, lambda: id(window.source.editor) in app._flow_checks, tries=200)  # Runner answered (any language)
            window.select(("step", "approval", "ask"))
            await settle(pilot, 6)
            save(app, "flow-window")
            await pilot.press("enter")
            await until(pilot, lambda: isinstance(getattr(app.screen, "dialog", None), StepDialog), tries=200)
            await settle(pilot, 6)
            save(app, "flow-step")
            await pilot.press("escape")
        broken = flow.read_text().replace("call: approval.ask", "call: approval.confirm").replace(
            "activity: format_receipt", "activity: format_reciept")
        flow.write_text(broken)
        app = Divide(root, [flow])
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 10)
            await pilot.press("ctrl+t")
            await until(pilot, lambda: isinstance(app.active_window(), FlowWindow), tries=200)
            window = app.active_window()
            await until(pilot, lambda: id(window.source.editor) in app._flow_checks, tries=200)
            await pilot.press("alt+f9")
            await until(pilot, lambda: app.messages_window() is not None, tries=200)
            await settle(pilot, 4)
            await pilot.press("escape")  # the Check box
            app.raise_window(window)
            window.select(("step", "review", "approve"))
            window.flow_tree.focus()
            await settle(pilot, 6)
            app.update_status()  # the Flow window's keys, not the Check box's folder
            await settle(pilot, 4)
            save(app, "flow-problems")

@shot
async def designer():
    """The Flow Designer on examples/generator's generate_php_dto.yml (composer install there), in a
    copy of it: the board at 160 and 120 columns (main.current selected, its jump over generation chosen)
    and 80 (main.validate's call), choosing that jump's target, the Block dialog, a Step's context, a phosphor theme, and the
    last good design kept read-only while the YAML does not parse."""
    import tempfile as _tempfile
    from divide.app import CM_FLOW_DESIGN
    from divide.ui.flow import save_flow_settings
    from divide.ui.flowboard import BlockDialog, FlowDesignWindow
    example = ROOT / "examples" / "generator"
    if not (example / "vendor" / "divengine" / "runner" / "bin" / "run.php").is_file():
        print("skipped designer: composer install in examples/generator")
        return

    async def opened(app, pilot):
        await settle(pilot, 10)
        app.run_command(CM_FLOW_DESIGN)
        await until(pilot, lambda: isinstance(app.active_window(), FlowDesignWindow), tries=200)
        window = app.active_window()
        await until(pilot, lambda: id(window.source.editor) in app._flow_checks, tries=300)  # Runner answered (any language)
        await settle(pilot, 8)
        return window

    with _tempfile.TemporaryDirectory() as work:
        root = Path(work) / "generator"
        shutil.copytree(example, root, ignore=shutil.ignore_patterns("*.context.json", ".div", "build"))
        flow = root / "flows" / "generate_php_dto.yml"
        save_flow_settings(flow.resolve(), {"context": "generate.json", "root": "functions", "save": ""})
        for width, height in ((160, 44), (120, 34), (80, 24)):
            app = Divide(root, [flow])
            async with app.run_test(size=(width, height)) as pilot:
                window = await opened(app, pilot)
                window.select(("step", "main", "validate" if width == 80 else "current"))  # 80: its call, near the top
                await settle(pilot, 4)
                await pilot.press("tab")
                await settle(pilot, 6)
                app.update_status()
                await settle(pilot, 4)
                save(app, f"flow-designer-{width}")
                if width == 120:
                    await pilot.press("escape")
                    window.select(("step", "main", "current"))
                    await settle(pilot, 4)
                    await pilot.press("j", "down", "down")  # from the Step itself to main.verify
                    await settle(pilot, 6)
                    save(app, "flow-designer-connect")
                    await pilot.press("escape")
                    window.select(("block", "generate"))
                    await pilot.press("enter")
                    await until(pilot, lambda: isinstance(getattr(app.screen, "dialog", None), BlockDialog), tries=200)
                    await settle(pilot, 6)
                    save(app, "flow-designer-block")
                    await pilot.press("escape")
                    window.select(("step", "main", "current"))
                    await pilot.press("x")  # the context as a tree, a new item in the JSON editor's dialog
                    from divide.ui.jsontree import EditItemDialog
                    await settle(pilot, 6)
                    await pilot.press("insert")
                    await until(pilot, lambda: isinstance(getattr(app.screen, "dialog", None), EditItemDialog), tries=200)
                    dialog = app.screen.dialog
                    dialog.key_input.data, dialog.value_input.data = "reason", "outputs current"
                    await settle(pilot, 6)
                    save(app, "flow-designer-context")
                    await pilot.press("escape")
                    await settle(pilot, 4)
                    await pilot.press("escape")
        app = Divide(root, [flow], palette="phosphor-green")
        async with app.run_test(size=(120, 34)) as pilot:
            window = await opened(app, pilot)
            window.select(("step", "main", "validate"))
            await settle(pilot, 4)
            await pilot.press("tab")
            await settle(pilot, 6)
            save(app, "flow-designer-phosphor")
        app = Divide(root, [flow])
        async with app.run_test(size=(120, 34)) as pilot:
            window = await opened(app, pilot)
            window.select(("step", "generate", "readme"))
            ed = window.source.editor
            at = ed.text.index("      readme:") + len("      readme:")
            ed.insert(" [", ed.document.get_location_from_index(at))  # typed in the code: no longer YAML
            await until(pilot, lambda: window.read_only, tries=200)
            await settle(pilot, 10)
            save(app, "flow-designer-readonly")


@shot
async def trace():
    """Debug > Render trace on the shop: the row where Div decides the condition."""
    from divide.ui.tracer import TraceWindow
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot, 10)
        app.run_worker(app.trace_render_command())
        await close_box(pilot, app)
        await until(pilot, lambda: isinstance(app.active_window(), TraceWindow), tries=200)
        window = app.active_window()
        row = next(i for i, m in enumerate(window.rows) if "is true" in m.label)
        window.list.focus_item(row)
        await settle(pilot, 6)
        save(app, "trace")
        window.toggle_before()
        await settle(pilot, 6)
        save(app, "trace-before")


OTHER_FILES = {  # a few files of a PHP project besides templates and PHP (written to a temporary folder)
    "README.md": "# Shop\n\nA *small* shop rendered with [Div](https://github.com/divengine/div).\n\n"
                 "## Run it\n\n- `composer install`\n- open `index.tpl` and press **Ctrl+F9**\n\n"
                 "```php\n$div = new div('index.tpl', 'index.json');\n```\n",
    "phpunit.xml.dist": '<?xml version="1.0" encoding="UTF-8"?>\n<!-- the unit tests -->\n'
                        '<phpunit bootstrap="vendor/autoload.php" colors="true">\n  <testsuites>\n'
                        '    <testsuite name="unit">\n      <directory>tests</directory>\n    </testsuite>\n'
                        '  </testsuites>\n</phpunit>\n',
    "php.ini": "; settings for php -S\n[PHP]\nmemory_limit = 256M\ndisplay_errors = On\n"
               "error_log = \"logs/php.log\"  ; next to the project\n\n[xdebug]\nxdebug.mode = debug\n"
               "xdebug.start_with_request = trigger\n",
    "products.csv": 'id,name,price,stock,category\n1,"Potato, red",1.50,120,vegetables\n2,Tomato,2.25,80,vegetables\n'
                    '3,Apple,0.90,200,fruit\n4,"Cheese ""aged""",7.40,15,dairy\n5,Bread,1.10,40,bakery\n',
}


@shot
async def other_files():
    """Other files of a project, each in its colours: Markdown, XML, INI and CSV, tiled."""
    with tempfile.TemporaryDirectory() as work:
        root = Path(work) / "shop"
        root.mkdir()
        for name, text in OTHER_FILES.items():
            (root / name).write_text(text, encoding="utf-8")
        app = Divide(root, [root / name for name in OTHER_FILES])
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 10)
            app.desktop.tile(); await settle(pilot, 10)
            app.raise_window(app.window_for(root / "README.md")); await settle(pilot)
            save(app, "other-files")


@shot
async def language():
    """Options > Language (the interface's language), in English."""
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        await pilot.press(key("options"), key("language")); await settle(pilot)
        save(app, "language-dialog")


SHOP_SETUP = {  # the Div setup of the shop's copy in the Div setup shots
    "paths": {"include": ["components"]},
    "parser": {"max_cycles": 50, "error_reporting": "E_ALL & ~E_DEPRECATED"},
    "data": {"globals": {"site": "The divide shop", "currency": "EUR"}, "system_vars": ["server"]},
    "php": {"allowed_functions": ["number_format"], "modifiers": {"rev:": "strrev"}},
    "request": {"get": {"page": 2}, "server": {"HTTP_HOST": "shop.test"}},
}


DEMO_COPY = Path(tempfile.gettempdir()) / "divide-demo"  # a name that reads well in the pictures (composer shows it)


def shop_copy(work: Path, setup: dict | None = None) -> Path:
    """The shop in a temporary folder (with its vendor/): shots that save, or need a .div/, leave the example alone.
    It is /tmp/divide-demo/shop, made anew for each shot and removed when the program ends (``work``, the
    caller's temporary folder, is kept for the callers; the copy does not go in it)."""
    root = DEMO_COPY / "shop"
    shutil.rmtree(DEMO_COPY, ignore_errors=True)
    shutil.copytree(DEMO, root, symlinks=True)
    atexit.register(shutil.rmtree, DEMO_COPY, True)
    if setup is not None:
        (root / ".div").mkdir()
        (root / ".div" / "setup.json").write_text(json.dumps(setup, indent=2) + "\n", encoding="utf-8")
    return root


class own_engine:
    """The project's own Div (vendor/) instead of $DIVIDE_DIV_PHP: the setup window shows it relative."""
    def __enter__(self):
        self.saved = os.environ.pop("DIVIDE_DIV_PHP", None)
    def __exit__(self, *exc):
        if self.saved:
            os.environ["DIVIDE_DIV_PHP"] = self.saved


@shot
async def div_setup():
    """Options > Div setup on a copy of the shop: the trust question first, the window, a section's dialog, its menu;
    then setup.json in the editor with two entries divide leaves out."""
    from divide.ui.dialogs import DialogScreen
    from divide.ui.divsetup import DivSetupWindow
    with tempfile.TemporaryDirectory() as work, own_engine():
        root = shop_copy(Path(work), SHOP_SETUP)
        app = Divide(root, [root / "index.tpl"])
        async with app.run_test(size=SIZE) as pilot:
            await until(pilot, lambda: isinstance(app.screen, DialogScreen), tries=200)
            await settle(pilot)
            save(app, "div-setup-trust")
            await pilot.press(key("yes"))
            await until(pilot, lambda: not isinstance(app.screen, DialogScreen))
            await pilot.pause(2.5); await settle(pilot)  # the "trusted" notice goes
            await app.open_div_setup(); await settle(pilot, 10)
            win = app.active_window()
            assert isinstance(win, DivSetupWindow)
            await until(pilot, lambda: win.check is not None, tries=300)
            win.sections.focus_item(4); await settle(pilot)  # Data
            save(app, "div-setup")
            win.edit_section(4)
            await until(pilot, lambda: isinstance(app.screen, DialogScreen))
            await pilot.pause(0.5); await settle(pilot)
            save(app, "div-setup-dialog")
            await pilot.press("escape"); await settle(pilot)
            await pilot.press("alt+f10"); await settle(pilot)
            save(app, "div-setup-menu")
        wrong = {**SHOP_SETUP, "paths": {"include": ["components", "partials"]},
                 "parser": {**SHOP_SETUP["parser"], "max_cycles": 0}}
        (root / ".div" / "setup.json").write_text(json.dumps(wrong, indent=2) + "\n", encoding="utf-8")
        app = Divide(root, [root / ".div" / "setup.json"])
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 10)
            if isinstance(app.screen, DialogScreen):  # trusted already: no question
                await pilot.press("escape"); await settle(pilot)
            ed = app.window_for(root / ".div" / "setup.json").editor
            await until(pilot, lambda: ed.diagnostics, tries=200)
            ed.move_cursor((8, 8)); await settle(pilot, 10)  # on max_cycles: the status bar says why
            save(app, "div-setup-json")


@shot
async def composer():
    """Tools > Composer packages on a copy of the shop (the real composer: the search asks Packagist),
    the add assistant, composer's words in its window, and the assistant of a new composer.json."""
    from divide.ui.composer import ComposerLogWindow, ComposerWindow
    from divide.ui.dialogs import DialogScreen
    with tempfile.TemporaryDirectory() as work:
        root = shop_copy(Path(work))
        app = Divide(root, [root / "index.tpl"])
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            await app.open_composer(); await settle(pilot, 10)
            win = app.active_window()
            assert isinstance(win, ComposerWindow)
            save(app, "composer")
            app.composer_action(win, "add")
            await until(pilot, lambda: isinstance(app.screen, DialogScreen))
            dialog = app.screen.dialog
            dialog.query_input.focus()
            await pilot.press(*"divengine")
            await until(pilot, lambda: dialog.found and dialog.version_input.data, tries=600)
            await settle(pilot)
            save(app, "composer-add")
            await pilot.press("escape"); await settle(pilot)
            app.composer_action(win, "validate")
            await until(pilot, lambda: any(isinstance(w, ComposerLogWindow) and w.lines for w in app.windows()), tries=600)
            await until(pilot, lambda: all(w.is_finished for w in app.workers if w.group == "composer"), tries=600)
            if isinstance(app.screen, ProgressScreen):
                await pilot.press("escape")
            await settle(pilot, 10)
            save(app, "composer-log")
        root = Path(work) / "acme" / "my-shop"  # the name it suggests: acme/my-shop
        root.mkdir(parents=True)
        app = Divide(root, [])
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            app.run_worker(app.open_composer())
            await until(pilot, lambda: isinstance(app.screen, DialogScreen))
            app.screen.dialog.inputs["namespace"].data = "Acme\\Shop"
            await settle(pilot)
            save(app, "composer-new")
            await pilot.press("escape"); await settle(pilot)


@shot
async def filtering():
    """The filter line over the project window: what holds "tpl", in every folder (The-Desktop.md)."""
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        app.toggle_project(); await settle(pilot)
        tree = app.project_window().project_tree
        app.raise_window(app.project_window()); tree.focus(); await settle(pilot)
        await pilot.press(*"tpl")
        await until(pilot, lambda: tree.cursor_node is not None and "tpl" in tree.cursor_node.label.plain, tries=200)
        await pilot.pause(0.5); await settle(pilot, 10)
        save(app, "filter")


@shot
async def spanish():
    """The Run menu in Spanish: a process of its own, the interface's language is chosen at start."""
    if os.environ["DIVIDE_LANGUAGE"] != "es":  # (the module's default is English)
        env = {**os.environ, "DIVIDE_LANGUAGE": "es"}
        subprocess.run([sys.executable, __file__, "--out", str(OUT), "spanish"], env=env, check=True)
        return
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot, 10)
        await pilot.press("alt+j"); await settle(pilot)
        save(app, "interface-spanish")


@shot
async def welcome():
    """divide alone: the Welcome window, with folders and files opened lately; then the File menu."""
    from divide import recent
    with tempfile.TemporaryDirectory() as work:
        root = shop_copy(Path(work))
        blog = root.parent / "blog"
        (blog / "posts").mkdir(parents=True)
        (blog / "posts" / "hello.tpl").write_text("<h1>{$title}</h1>\n", encoding="utf-8")
        for path in (root / "index.json", blog / "posts" / "hello.tpl", root / "components" / "card.tpl",
                     root / "index.tpl"):
            recent.add("files", path)
        for path in (blog, root):
            recent.add("folders", path)
        app = Divide(None, [])
        async with app.run_test(size=SIZE) as pilot:
            await until(pilot, lambda: app.welcome_window() is not None)
            win = app.welcome_window()
            await until(pilot, lambda: win.git_tree.last_line > 8)
            win.git_tree.put_bar(f"folders:{root}")
            await settle(pilot, 10)
            save(app, "welcome")
            await pilot.press(key("file")); await settle(pilot)
            save(app, "file-menu")


@shot
async def phosphor():
    """The five phosphor themes (Options > Colors), each on the shop as a repository: the editor with Git's
    marks in its margin, a breakpoint and the execution line, beside the project window; the checkout with
    its errors in Messages; a diff; a Runner Flow with problems (when examples/runner has its vendor/).
    Each also with 16 colours (as the terminal's ANSI colours) and at 80x24. Not in the manual by default:
    a review set (``phosphor``)."""
    from divide import themes
    from divide.ui import git as gitui
    names = [n for n, p in themes.THEMES.items() if p.monochrome]
    runner = ROOT / "examples" / "runner"
    with tempfile.TemporaryDirectory() as work:
        root = git_shop(Path(work) / "shop")
        flows = None
        if (runner / "vendor" / "divengine" / "runner" / "bin" / "run.php").is_file():
            flows = Path(work) / "runner"
            shutil.copytree(runner, flows, ignore=shutil.ignore_patterns("*.context.json", ".div"))
            (flows / "flows" / "order.yml").write_text((flows / "flows" / "order.yml").read_text()
                .replace("call: approval.ask", "call: approval.confirm").replace("activity: format_receipt", "activity: format_reciept"))
            from divide.ui.flow import save_flow_settings
            save_flow_settings((flows / "flows" / "order.yml").resolve(), {"context": "order.json", "root": "functions", "save": ""})
        for name in names:
            for depth, size, suffix in (("truecolor", SIZE, ""), ("16", SIZE, "-16"), ("truecolor", (80, 24), "-80x24")):
                app = Divide(root, [], palette=name, colors=depth)
                async with app.run_test(size=size) as pilot:
                    await settle(pilot, 10)
                    if app.project_window() is None:
                        app.toggle_project(); await settle(pilot)
                    app.open_file(root / "index.tpl"); await settle(pilot, 10)
                    tree = app.project_window().project_tree
                    await tree.reveal(root / "layout" / "footer.tpl")
                    ed = app.window_for(root / "index.tpl").editor
                    await until(pilot, lambda: tree.git_files and ed.change_rows, tries=200)
                    ed.set_debug_marks({3}, 6)  # a breakpoint and the line about to run, as when debugging
                    app.raise_window(app.window_for(root / "index.tpl")); ed.move_cursor((9, 4)); await settle(pilot, 10)
                    save(app, f"theme-{name}{suffix}")
                    if suffix:
                        continue
                    app.open_file(root / "checkout.tpl"); await settle(pilot, 10)
                    await pilot.press("alt+f9")
                    await close_box(pilot, app)
                    await settle(pilot, 10)
                    save(app, f"theme-{name}-errors")
                    for w in list(app.windows()):
                        app._remove_window(w)
                    await settle(pilot)
                    await app.git_command(gitui.CM_GIT_CHANGES)
                    win = _git_window(app, gitui.GitChangesWindow)
                    await _git_bar_on(pilot, win.git_tree, _on_change("index.tpl"))
                    await until(pilot, lambda: win.diff.rows_text(), tries=200)
                    win.diff.side_by_side = True; win.diff._build(); await settle(pilot, 10)
                    save(app, f"theme-{name}-diff")
            if flows is not None:
                from divide.ui.flowmodel import FlowWindow
                flow = flows / "flows" / "order.yml"
                app = Divide(flows, [flow], palette=name)
                async with app.run_test(size=SIZE) as pilot:
                    await settle(pilot, 10)
                    app.raise_window(app.window_for(flow))
                    await pilot.press("ctrl+t")
                    await until(pilot, lambda: isinstance(app.active_window(), FlowWindow), tries=200)
                    window = app.active_window()
                    await until(pilot, lambda: id(window.source.editor) in app._flow_checks, tries=200)
                    await pilot.press("alt+f9")
                    await until(pilot, lambda: app.messages_window() is not None, tries=200)
                    await settle(pilot, 4)
                    await pilot.press("escape")
                    app.raise_window(window)
                    window.select(("step", "review", "approve")); window.flow_tree.focus()
                    await settle(pilot, 6); app.update_status(); await settle(pilot, 4)
                    save(app, f"theme-{name}-flow")
                    await pilot.press(key("run")); await settle(pilot)
                    save(app, f"theme-{name}-menu")
                    await pilot.press("escape"); await settle(pilot)
                    app.run_worker(app.choose_colors()); await settle(pilot, 10)
                    save(app, f"theme-{name}-colors")
                    await pilot.press("escape"); await settle(pilot)


# ------------------------------------------------------------------ git
def _git(root: Path, *args: str, day: int = 0) -> str:
    """git in the copy, as Ana Div, at a fixed time (the same history, the same pictures)."""
    when = f"2026-11-{10 + day:02d}T{9 + day % 5}:30:00+00:00"
    env = {**os.environ, "GIT_AUTHOR_NAME": "Ana Div", "GIT_AUTHOR_EMAIL": "ana@example.com",
           "GIT_COMMITTER_NAME": "Ana Div", "GIT_COMMITTER_EMAIL": "ana@example.com",
           "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when, "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True, text=True).stdout


def _edit(path: Path, *pairs: tuple[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        assert old in text, (path, old)
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def git_shop(work: Path) -> Path:
    """The shop as a repository with a history: a merged branch, one still open, a stash, and changes of
    every kind (index.tpl changed, the footer staged, coupon.json new). Made anew, as shop_copy is."""
    root = shop_copy(work)
    later = {p: p.read_text(encoding="utf-8") for p in (root / "checkout.tpl", root / "components" / "card.tpl")}
    (root / ".gitignore").write_text("vendor/\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "config", "user.name", "Ana Div")  # a commit made in the pictures is hers too, never the
    _git(root, "config", "user.email", "ana@example.com")  # identity of whoever takes them
    for path in later:
        path.unlink()
    home = root / "index.tpl"
    cart = "  {?( {$cart.items} > 0 )?}\n  <a href=\"/cart\">Cart: {$cart.items} items</a>\n  {/?}\n"
    whole = home.read_text(encoding="utf-8")
    home.write_text(whole.replace(cart, "", 1), encoding="utf-8")  # the cart comes with the checkout
    _git(root, "add", ".gitignore", "README.md", "composer.json", "composer.lock", "index.json", "index.tpl",
         "index.php", "erb.dialect")
    _git(root, "commit", "-qm", "The home page", day=0)
    footer = root / "layout" / "footer.tpl"
    _git(root, "add", "layout")
    _git(root, "commit", "-qm", "Header and footer layouts", day=1)
    _git(root, "switch", "-qc", "feature/cards", day=2)
    (root / "components" / "card.tpl").write_text(later[root / "components" / "card.tpl"], encoding="utf-8")
    _git(root, "add", "components")
    _git(root, "commit", "-qm", "A card per product", day=2)
    _git(root, "switch", "-q", "main", day=3)
    (root / "checkout.tpl").write_text(later[root / "checkout.tpl"], encoding="utf-8")
    home.write_text(whole, encoding="utf-8")
    _git(root, "add", "checkout.tpl", "index.tpl")
    _git(root, "commit", "-qm", "Checkout page (broken on purpose)", day=3)
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "feature/cards", day=4)
    _git(root, "switch", "-qc", "coupons", day=5)
    (root / "coupon.tpl").write_text('<p class="coupon">{$coupon}</p>\n', encoding="utf-8")
    _git(root, "add", "coupon.tpl")
    _git(root, "commit", "-qm", "A coupon box", day=5)
    _git(root, "switch", "-q", "main", day=6)
    _edit(root / "layout" / "header.tpl", ("<body>", '<body class="dark">'))
    _git(root, "stash", "push", "-qm", "A darker header", day=6)
    _edit(footer, ("<footer", "<!-- the footer -->\n<footer"))
    _git(root, "add", "layout/footer.tpl")
    _edit(root / "index.tpl",
          ("<h1>{^^title}</h1>", '<h1 class="title">{^^title}</h1>'),
          ("<p>{$tagline}</p>", '<p class="tagline">{$tagline}</p>\n  <p class="note">Prices include taxes</p>'),
          ("Nothing on sale today.", "Nothing on sale today. Come back tomorrow!"),
          ("  </section>\n", ""))
    (root / "coupon.json").write_text('{"coupon": "DIV10"}\n', encoding="utf-8")
    return root


def _git_window(app, kind):
    return next(w for w in app.windows() if isinstance(w, kind))


async def _git_bar_on(pilot, tree, pred):
    """The bar on the first row ``pred(row)`` holds (a Row: its kind and its item)."""
    await until(pilot, lambda: tree.last_line > 0, tries=200)
    for line in range(tree.last_line + 1):
        node = tree.get_node_at_line(line)
        if node is not None and node.data is not None and pred(node.data):
            tree.move_cursor(node)
            await settle(pilot, 10)
            return
    raise SystemExit("no such row in the git window")


def _on_change(path):
    return lambda row: row.kind == "change" and row.item.path == path


@shot
async def git():
    """Git: the menu; the changes with a diff (unified, side by side); the commit; the history; the branches;
    blame; the marks in the project window and the editor's margin. On a repository made for the pictures."""
    from divide.ui import git as gitui
    from divide.ui.dialogs import DialogScreen
    with tempfile.TemporaryDirectory() as work:
        root = git_shop(Path(work))
        app = Divide(root, [])
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 10)
            if app.project_window() is None:
                app.toggle_project(); await settle(pilot)
            app.open_file(root / "index.tpl"); await settle(pilot, 10)  # beside the project window
            tree = app.project_window().project_tree
            await tree.reveal(root / "layout" / "footer.tpl")
            ed = app.window_for(root / "index.tpl").editor
            await until(pilot, lambda: tree.git_files and ed.change_rows, tries=200)
            app.raise_window(app.window_for(root / "index.tpl")); ed.move_cursor((9, 4)); await settle(pilot, 10)
            save(app, "git-marks")
            await pilot.press(key("git")); await settle(pilot)
            save(app, "git-menu")
            await pilot.press("escape"); await settle(pilot)
            app._remove_window(app.project_window()); await settle(pilot)  # room for the diff

            await app.git_command(gitui.CM_GIT_CHANGES)
            win = _git_window(app, gitui.GitChangesWindow)
            await _git_bar_on(pilot, win.git_tree, _on_change("index.tpl"))
            await until(pilot, lambda: win.diff.rows_text(), tries=200)
            win.diff.side_by_side = False; win.diff._build(); await settle(pilot, 10)
            save(app, "git-changes")
            win.diff.side_by_side = True; win.diff._build(); await settle(pilot, 10)
            save(app, "git-diff-split")
            win.git_tree.focus(); await settle(pilot)
            await pilot.press("ctrl+k")
            await until(pilot, lambda: isinstance(app.screen, DialogScreen), tries=200)
            await pilot.press(*"Classes on the home page"); await settle(pilot, 10)
            save(app, "git-commit")
            app.screen.action_cancel()
            await until(pilot, lambda: not isinstance(app.screen, DialogScreen)); await settle(pilot, 10)

            await app.git_command(gitui.CM_GIT_HISTORY)
            hist = _git_window(app, gitui.GitHistoryWindow)
            await _git_bar_on(pilot, hist.git_tree, lambda row: row.kind == "commit" and "Checkout" in row.item.subject)
            await pilot.pause(0.5); await settle(pilot, 15)
            save(app, "git-history")

            await app.git_command(gitui.CM_GIT_BRANCHES)
            branches = _git_window(app, gitui.GitBranchesWindow)
            await _git_bar_on(pilot, branches.git_tree, lambda row: row.kind == "branch" and row.item.name == "coupons")
            await pilot.pause(0.5); await settle(pilot, 15)
            save(app, "git-branches")

            app.raise_window(app.window_for(root / "index.tpl")); await settle(pilot)
            await app.git_command(gitui.CM_GIT_BLAME)
            await until(pilot, lambda: any(isinstance(w, gitui.BlameWindow) for w in app.windows()), tries=200)
            blame = _git_window(app, gitui.BlameWindow)
            await pilot.pause(0.5); await settle(pilot, 10)
            blame.view.move_cursor((17, 0)); await settle(pilot, 10)
            save(app, "git-blame")


FAKE_GH = r"""
import json, os, sys
answers = json.loads(os.environ["DIVIDE_SHOT_GH"])
print(answers.get(" ".join(sys.argv[1:3]), ""))
"""


@shot
async def forge():
    """Git > Pull requests and issues, from a stand-in for gh that answers as GitHub would (nothing leaves)."""
    from divide.run import forge as forgerun
    from divide.ui import forge as forgeui
    pulls = [{"number": 12, "title": "A card per product", "author": {"login": "ana"}, "headRefName": "feature/cards",
              "baseRefName": "main", "state": "OPEN", "url": "https://github.com/acme/shop/pull/12", "isDraft": False,
              "updatedAt": "2026-11-18T10:00:00Z"},
             {"number": 14, "title": "A coupon box", "author": {"login": "bo"}, "headRefName": "coupons",
              "baseRefName": "main", "state": "OPEN", "url": "https://github.com/acme/shop/pull/14", "isDraft": True,
              "updatedAt": "2026-11-18T12:30:00Z"}]
    issues = [{"number": 9, "title": "The footer breaks on phones", "author": {"login": "carla"}, "state": "OPEN",
               "url": "https://github.com/acme/shop/issues/9", "labels": [{"name": "bug"}, {"name": "css"}],
               "updatedAt": "2026-11-17T09:00:00Z"},
              {"number": 11, "title": "Prices with taxes", "author": {"login": "ana"}, "state": "OPEN",
               "url": "https://github.com/acme/shop/issues/11", "labels": [], "updatedAt": "2026-11-16T09:00:00Z"}]
    with tempfile.TemporaryDirectory() as work:
        root = git_shop(Path(work))
        _git(root, "remote", "add", "origin", "git@github.com:acme/shop.git")
        script = Path(work) / "gh.py"
        script.write_text(FAKE_GH, encoding="utf-8")
        os.environ["DIVIDE_SHOT_GH"] = json.dumps({"pr list": json.dumps(pulls), "issue list": json.dumps(issues)})
        saved, forgerun.COMMANDS = forgerun.COMMANDS, {"github": [sys.executable, str(script)], "gitea": None}
        try:
            app = Divide(root, [])
            async with app.run_test(size=SIZE) as pilot:
                await settle(pilot, 10)
                await app.open_forge()
                win = _git_window(app, forgeui.ForgeWindow)
                await _git_bar_on(pilot, win.git_tree,
                                  lambda row: getattr(row.item, "number", None) == 9)
                await pilot.pause(0.5); await settle(pilot, 10)
                save(app, "git-forge")
        finally:
            forgerun.COMMANDS = saved


async def run(names: set[str]) -> None:
    for fn in SHOTS:
        if not names or fn.__name__ in names:
            await fn()


def main() -> None:
    global OUT, SVG_DIR
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True, type=Path, help="folder for the PNGs (the wiki's images/)")
    parser.add_argument("--engine", help="Div engine (default: $DIVIDE_DIV_PHP)")
    parser.add_argument("shots", nargs="*", help="only these: " + ", ".join(fn.__name__ for fn in SHOTS))
    args = parser.parse_args()
    engine = args.engine or os.environ.get("DIVIDE_DIV_PHP")
    if not engine or not Path(engine).is_file():
        sys.exit("A Div engine is needed: --engine or DIVIDE_DIV_PHP (vendor/autoload.php or src/div.php)")
    for tool in ("php", "rsvg-convert"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found in PATH")
    unknown = set(args.shots) - {fn.__name__ for fn in SHOTS}
    if unknown:
        sys.exit(f"unknown shots: {', '.join(sorted(unknown))}")
    os.environ["DIVIDE_DIV_PHP"] = str(Path(engine).resolve())
    OUT = args.out.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:  # removed afterwards: /tmp is often in RAM
        os.environ["XDG_CONFIG_HOME"] = str(Path(work) / "config")  # no personal settings in the pictures
        os.environ["DIV_HOME"] = str(Path(work) / "div-home")  # nor the user's Div setup, nor what they trust
        (Path(work) / "config" / "divide").mkdir(parents=True)
        (Path(work) / "config" / "divide" / "config.json").write_text(f'{{"palette": "{PALETTE}"}}', encoding="utf-8")
        SVG_DIR = Path(work)
        asyncio.run(run(set(args.shots)))


if __name__ == "__main__":
    main()
