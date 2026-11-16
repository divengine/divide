"""Screencasts of divide: a scene, recorded frame by frame, as a GIF and an MP4.

    .venv/bin/python tools/screencast.py --out DIR [--engine autoload.php] [--music file] [scene]

A scene drives the real app on examples/shop with Textual's pilot, as the
wiki's screenshots do (see wiki_shots.py: same size, palette and drawing).
Each step is a frame with how long it stays on screen; captions are timed
with them. Then ffmpeg makes:

- DIR/<scene>.gif: the captions drawn on the picture (a GIF has no text track),
  a palette of its own and no dithering: a text screen has flat colours;
- DIR/<scene>.mp4: H.264, the captions drawn too, and music under it (--music,
  or a soft chord made by ffmpeg, as a placeholder);
- DIR/<scene>.srt: the captions, for a player or YouTube.

Nothing is saved in the example project. Needs php, a Div engine, rsvg-convert
and ffmpeg (with libass and libx264).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wiki_shots  # noqa: E402  (sets the interface's language before divide is imported)
from wiki_shots import DEMO, SIZE, PALETTE, rasterise, settle  # noqa: E402

from divide.app import Divide  # noqa: E402
from divide.ui.progress import ProgressScreen  # noqa: E402

FONT = "Liberation Sans"


@dataclass
class Recorder:
    """The frames of a scene, each with its time on screen, and the captions."""

    app: Divide
    pilot: object
    work: Path
    frames: list[list] = field(default_factory=list)  # [png, seconds, svg]
    captions: list[list] = field(default_factory=list)  # [start, end, text]
    time: float = 0.0

    async def snap(self, seconds: float, settle_first: int = 4) -> None:
        """The screen as it is now, for ``seconds`` (a frame like the one before only lasts longer)."""
        await settle(self.pilot, settle_first)
        svg = self.app.export_screenshot(title="divide")
        if self.frames and self.frames[-1][2] == svg:
            self.frames[-1][1] += seconds
        else:
            png = self.work / f"f{len(self.frames):04d}.png"
            rasterise(svg, png, self.work)
            self.frames.append([png, seconds, svg])
        self.time += seconds

    async def press(self, *keys: str, hold: float = 0.6) -> None:
        for key in keys:
            await self.pilot.press(key)
            await self.snap(hold)

    async def type(self, text: str, per: float = 0.12) -> None:
        """Typed letter by letter, as a person types."""
        for char in text:
            await self.pilot.press(char)
            await self.snap(per, 3)

    async def until(self, pred, step: float = 0.25, tries: int = 80) -> None:
        """Frames while the app works, until ``pred()``."""
        for _ in range(tries):
            if pred():
                return
            await self.snap(step, 2)
        import inspect
        raise SystemExit(f"timed out waiting for the app: lines {[f.lineno for f in inspect.stack()[1:3]]}, screen {self.app.screen!r}")

    async def go_to_file(self, name: str) -> None:
        """Ctrl+P and the file's name, as a person opens one."""
        await self.pilot.press("ctrl+p")
        await self.snap(0.4)
        await self.type(name, 0.08)
        await self.snap(0.6)
        await self.pilot.press("enter")

    async def box(self, hold: float = 1.2) -> None:
        """The progress box until its verdict, then closed by a key."""
        await self.until(lambda: isinstance(self.app.screen, ProgressScreen) and not self.app.screen.dialog.running)
        await self.snap(hold)
        await self.pilot.press("escape")

    def caption(self, text: str) -> None:
        """From now until the next caption (or the end)."""
        if self.captions and self.captions[-1][1] is None:
            self.captions[-1][1] = self.time
        self.captions.append([self.time, None, text])

    def finish(self) -> None:
        if self.captions and self.captions[-1][1] is None:
            self.captions[-1][1] = self.time


# ------------------------------------------------------------------ scenes
async def outline(rec_dir: Path) -> Recorder:
    """A template: its outline, a jump to its loop, a render, the project window's members."""
    app = Divide(DEMO, [DEMO / "index.tpl"])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot, 10)
        rec = Recorder(app, pilot, rec_dir)
        rec.caption("divide: a Turbo Vision IDE for Div templates and PHP")
        await rec.snap(3.0, 10)

        rec.caption("Ctrl+O: the outline of the template, as a tree")
        await pilot.press("ctrl+o")
        await rec.snap(2.5)
        await rec.press("down", "down", hold=0.7)

        rec.caption("Enter jumps to the tag in the editor")
        await pilot.press("enter")
        await rec.snap(2.5)

        rec.caption("Ctrl+F9 renders the template with Div itself")
        await pilot.press("ctrl+f9")
        for _ in range(40):  # the progress box, while Div works
            await rec.snap(0.25, 2)
            if isinstance(app.screen, ProgressScreen) and not app.screen.dialog.running:
                break
        await rec.snap(1.5)
        await pilot.press("escape")
        rec.caption("The output, beside the template")
        await rec.snap(3.0, 8)

        rec.caption("Ctrl+B: the project window unfolds each file into its members")
        await pilot.press("ctrl+b")
        await rec.snap(1.5, 8)
        tree = app.project_window().project_tree
        target = next(c for c in tree.root.children if c.label.plain == "index.tpl")
        while tree.cursor_node is not target:
            await rec.press("down", hold=0.25)
        await rec.press("right", hold=3.0)
        rec.finish()
        await settle(pilot)
    return rec


async def tour(rec_dir: Path) -> Recorder:
    """The fundamentals, for the README: completion from the data, errors before
    rendering, a render, the render trace, the data tree, the outline, the dialector."""
    from divide.ui.tracer import TraceWindow
    index = DEMO / "index.tpl"
    app = Divide(DEMO, [index])
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot, 10)
        app.toggle_project()
        await settle(pilot)
        app.raise_window(app.window_for(index))
        await settle(pilot, 10)
        rec = Recorder(app, pilot, rec_dir)
        rec.caption("divide: the IDE for Div templates and PHP, in your terminal")
        await rec.snap(3.0, 10)

        rec.caption("Completion from your data: {$ offers the keys of index.json")
        ed = app.window_for(index).editor
        original = ed.text
        ed.move_cursor((8, 21))
        await pilot.press("end", "enter")
        await rec.snap(0.4)
        await rec.type("<p>{$")
        await rec.snap(1.6, 8)
        await rec.press("down", "down", hold=0.5)
        await pilot.press("enter")
        await rec.snap(1.8)
        for _ in range(20):  # back to the template as it was, off camera
            if ed.text == original:
                break
            await pilot.press("ctrl+z")
            await settle(pilot, 2)
        if ed.text != original:
            ed.load_text(original)
        ed.move_cursor((10, 2))

        rec.caption("Errors before you render: checkout.tpl is broken on purpose")
        await rec.go_to_file("checkout")
        await rec.until(lambda: app.window_for(DEMO / "checkout.tpl") is not None)
        await rec.snap(2.0, 10)
        rec.caption("Alt+F9 checks it; Alt+F8 walks through the errors")
        await pilot.press("alt+f9")
        await rec.box()
        await rec.snap(1.5, 6)
        await rec.press("alt+f8", "alt+f8", hold=1.0)

        rec.caption("Ctrl+F9 renders with the real Div engine, unsaved edits included")
        await rec.go_to_file("index.tpl")
        await rec.snap(0.8, 6)
        await pilot.press("ctrl+f9")
        await rec.box()
        await rec.snap(3.0, 8)

        rec.caption("F7: the render trace replays how Div rewrote the template")
        app.raise_window(app.window_for(index))
        await rec.snap(0.5, 6)
        await pilot.press("f7")
        await rec.until(lambda: isinstance(app.active_window(), TraceWindow), tries=120)
        await rec.snap(0.4)
        if isinstance(app.screen, ProgressScreen):
            await rec.box(0.6)
        await rec.snap(1.2, 6)
        await rec.press("f8", "f8", "f8", "f8", hold=0.9)
        await rec.press("space", hold=1.6)

        rec.caption("Ctrl+T: the data, as code or as a tree")
        await rec.go_to_file("index.json")
        await rec.snap(1.2, 8)
        await pilot.press("ctrl+t")
        await rec.snap(0.8, 6)
        await rec.press("down", "down", "down", hold=0.3)
        await rec.press("space", "down", "space", hold=0.6)
        await rec.snap(1.2)

        rec.caption("Ctrl+O: the outline of a template; Enter jumps to it")
        for window in list(app.windows()):  # a tidy desktop again
            if window is not app.window_for(index) and window is not app.project_window():
                app.raise_window(window)
                await settle(pilot, 2)
                await pilot.press("alt+f3")
                await settle(pilot, 4)
        app.raise_window(app.window_for(index))
        await rec.snap(0.5, 6)
        await pilot.press("ctrl+o")
        await rec.snap(1.6, 8)
        await rec.press("down", "down", hold=0.5)
        await pilot.press("enter")
        await rec.snap(1.8)

        rec.caption("Tools > Dialector: your own Div dialect, checked by Div as you build it")
        await rec.go_to_file("erb.dialect")
        await rec.snap(1.0, 8)
        await pilot.press(wiki_shots.key("tools"))
        await rec.snap(0.8)
        await pilot.press("d")
        await rec.snap(0.4, 8)
        win = app.active_window()
        await rec.until(lambda: getattr(win, "verdict", None) is not None)
        await rec.press("down", "down", "down", "down", hold=0.6)
        await rec.snap(3.0, 8)
        rec.finish()
        await settle(pilot)
    return rec


SCENES = {"outline": outline, "tour": tour}


# ------------------------------------------------------------------ output
def _stamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(rec: Recorder, path: Path) -> None:
    lines = []
    for n, (start, end, text) in enumerate(rec.captions, 1):
        lines += [str(n), f"{_stamp(start)} --> {_stamp(end)}", text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_concat(rec: Recorder, path: Path) -> None:
    """ffmpeg's concat list: each frame and how long it stays (the last one twice, as it asks)."""
    lines = []
    for png, seconds, _svg in rec.frames:
        lines += [f"file '{png}'", f"duration {seconds:.3f}"]
    lines.append(f"file '{rec.frames[-1][0]}'")
    path.write_text("\n".join(lines) + "\n")


def ffmpeg(*args: str) -> None:
    subprocess.run(["nice", "-n", "10", "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


BAND = 0.085  # the captions' band below the screen, as a part of the screen's height


def frame_size(png: Path) -> tuple[int, int]:
    data = png.read_bytes()[16:24]  # the PNG's IHDR: width, height
    return int.from_bytes(data[:4], "big"), int.from_bytes(data[4:], "big")


def _ass_time(seconds: float) -> str:
    cs = round(seconds * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def captions_ass(rec: Recorder, width: int, path: Path) -> tuple[int, int, int]:
    """The captions as ASS for a video ``width`` wide: centred in a dark band below
    the screen, never over it. Returns (screen height, band height, video height)."""
    w, h = frame_size(rec.frames[0][0])
    screen = round(h * width / w / 2) * 2
    band = round(screen * BAND / 2) * 2
    size = round(band * 0.5)
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {screen + band}",
             "WrapStyle: 0", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, "
             "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV",
             f"Style: Caption,{FONT},{size},&H00F0F0F0,&H00000000,&H00000000,0,0,1,0,0,2,20,20,{(band - size) // 2}",
             "", "[Events]", "Format: Layer, Start, End, Style, Text"]
    for start, end, text in rec.captions:
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Caption,{text}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return screen, band, screen + band


def captioned(rec: Recorder, width: int, work: Path) -> str:
    """The filters: the screen scaled to ``width``, the band below it, the captions in it."""
    ass = work / f"captions-{width}.ass"
    screen, band, _total = captions_ass(rec, width, ass)
    return (f"scale={width}:{screen}:flags=lanczos,pad={width}:{screen + band}:0:0:color=0x16181d,"
            f"ass={ass}")


def make_gif(rec: Recorder, concat: Path, work: Path, out: Path, width: int = 900, colors: int = 64) -> None:
    # one GIF frame per frame of the scene, each with its own delay: a still screen costs nothing
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-vf",
           f"{captioned(rec, width, work)},"
           f"split[a][b];[a]palettegen=max_colors={colors}:stats_mode=full[p];[b][p]paletteuse=dither=none:diff_mode=rectangle",
           "-fps_mode", "vfr", str(out))


def make_music(seconds: float, out: Path) -> None:
    """A placeholder: a soft A minor chord that breathes, fading in and out."""
    chord = "+".join(f"{a}*sin(2*PI*{f}*t)" for a, f in ((0.10, 110), (0.07, 220), (0.05, 261.63), (0.04, 329.63)))
    ffmpeg("-f", "lavfi", "-i", f"aevalsrc='({chord})*(0.7+0.3*sin(2*PI*0.2*t))':s=44100:d={seconds:.2f}",
           "-af", f"afade=t=in:d=2,afade=t=out:st={max(0.0, seconds - 3):.2f}:d=3,volume=0.6", str(out))


def make_mp4(rec: Recorder, concat: Path, work: Path, music: Path, out: Path, width: int = 1280) -> None:
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(music), "-vf",
           f"fps=25,{captioned(rec, width, work)},format=yuv420p",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-tune", "stillimage",
           "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True, type=Path, help="folder for the GIF, the MP4 and the SRT")
    parser.add_argument("--engine", help="Div engine (default: $DIVIDE_DIV_PHP)")
    parser.add_argument("--music", type=Path, help="music under the video (default: a placeholder chord)")
    parser.add_argument("--gif-width", type=int, default=900, help="the GIF's width in pixels (default 900)")
    parser.add_argument("--gif-colors", type=int, default=64, help="the GIF's palette (default 64 colours)")
    parser.add_argument("scene", nargs="?", default="outline", choices=sorted(SCENES))
    args = parser.parse_args()
    engine = args.engine or os.environ.get("DIVIDE_DIV_PHP")
    if not engine or not Path(engine).is_file():
        sys.exit("A Div engine is needed: --engine or DIVIDE_DIV_PHP (vendor/autoload.php or src/div.php)")
    for tool in ("php", "rsvg-convert", "ffmpeg"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found in PATH")
    os.environ["DIVIDE_DIV_PHP"] = str(Path(engine).resolve())
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work_dir:
        work = Path(work_dir)
        os.environ["XDG_CONFIG_HOME"] = str(work / "config")
        (work / "config" / "divide").mkdir(parents=True)
        (work / "config" / "divide" / "config.json").write_text(f'{{"palette": "{PALETTE}"}}')
        frames = work / "frames"
        frames.mkdir()
        rec = asyncio.run(SCENES[args.scene](frames))
        print(f"{len(rec.frames)} frames, {rec.time:.1f} s")
        srt, concat = out / f"{args.scene}.srt", work / "frames.txt"
        write_srt(rec, srt)
        write_concat(rec, concat)
        make_gif(rec, concat, work, out / f"{args.scene}.gif", args.gif_width, args.gif_colors)
        print("saved", out / f"{args.scene}.gif")
        music = args.music
        if music is None:
            music = work / "music.wav"
            make_music(rec.time, music)
        make_mp4(rec, concat, work, music, out / f"{args.scene}.mp4")
        print("saved", out / f"{args.scene}.mp4")


if __name__ == "__main__":
    main()
