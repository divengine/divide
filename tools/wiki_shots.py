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
OUT: Path = Path()
SVG_DIR: Path = Path()

from divide.app import Divide  # noqa: E402

def save(app, name):
    svg = app.export_screenshot(title="divide")
    svg = re.sub(r'font-family:[^;"]*', "font-family: Liberation Mono; letter-spacing: 0.2px", svg)
    # rsvg drops a span's leading no-break space: plain spaces, preserved
    svg = svg.replace("&#160;", " ").replace("<svg ", '<svg xml:space="preserve" ', 1)
    tmp = SVG_DIR / f"{name}.svg"
    tmp.write_text(svg)
    subprocess.run(["rsvg-convert", str(tmp), "-o", str(OUT / f"{name}.png")], check=True)
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
        await pilot.press("alt+f9"); await settle(pilot)
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
        await pilot.press("f"); await settle(pilot)
        await pilot.press(*"badge.tpl"); await settle(pilot)
        save(app, "project-new-file")

@shot
async def menus():
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        await pilot.press("alt+r"); await settle(pilot)
        save(app, "menu-run")

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
    app = Divide(DEMO, [DEMO / "index.tpl", DEMO / "components" / "card.tpl"], palette="turbo-c")
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        app.toggle_project(); await settle(pilot)
        app.desktop.tile(); await settle(pilot)
        save(app, "window-tile")
        await pilot.press("alt+w"); await settle(pilot)
        save(app, "palette-turbo-c")

@shot
async def dialector():
    app = Divide(DEMO, [DEMO / "erb.dialect"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        await pilot.press("alt+t", "d"); await settle(pilot)
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
        await pilot.press("alt+t", "t"); await settle(pilot)
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
        await pilot.press("alt+t", "d"); await settle(pilot)
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


@shot
async def php():
    app = Divide(DEMO, [DEMO / "index.php"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot, 10)
        ed = app.active_editor().editor
        ed.move_cursor((13, 0))
        ed.insert("$data['cart'] = ['items' => count($data['products'])\n")
        await until(pilot, lambda: bool(ed.diagnostics))
        await pilot.press("alt+f9"); await settle(pilot, 10)
        app.raise_window(app.window_for(DEMO / "index.php"))
        app.window_for(DEMO / "index.php").editor.move_cursor((13, 20))
        await settle(pilot, 6)
        save(app, "php")


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
    os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()  # no personal settings in the pictures
    OUT = args.out.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    SVG_DIR = Path(tempfile.mkdtemp())
    asyncio.run(run(set(args.shots)))


if __name__ == "__main__":
    main()
