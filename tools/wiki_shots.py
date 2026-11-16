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
           "help-search": "s", "language": "g", "help-query": "include templ", "new-file": "f"},
    "es": {"run": "alt+j", "window": "alt+v", "options": "alt+o", "tools": "alt+h", "help": "alt+y",
           "help-search": "b", "language": "i", "help-query": "incluir plantil", "new-file": "n"},
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
    tmp.write_text(svg)
    subprocess.run(["rsvg-convert", str(tmp), "-o", str(png)], check=True)


def save(app, name):
    svg = app.export_screenshot(title="divide")
    if os.environ.get("DIVIDE_SHOT_KEEP_SVG"):
        (Path(os.environ["DIVIDE_SHOT_KEEP_SVG"]) / f"{name}.svg").write_text(svg)
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
        json.dumps({"palette": PALETTE, "lsp": {"php": name}, "lsp_commands": {name: command}}))
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
    (config_home / "divide" / "config.json").write_text(json.dumps({"palette": PALETTE, "xdebug": xdebug or None}))
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
    (config_home / "divide" / "config.json").write_text(json.dumps({"palette": PALETTE, "xdebug": xdebug or None}))
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
            (root / name).write_text(text)
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
        (Path(work) / "config" / "divide").mkdir(parents=True)
        (Path(work) / "config" / "divide" / "config.json").write_text(f'{{"palette": "{PALETTE}"}}')
        SVG_DIR = Path(work)
        asyncio.run(run(set(args.shots)))


if __name__ == "__main__":
    main()
