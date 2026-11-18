"""Colour themes: one place for every colour, the same roles in every theme,
legible syntax, 16- and 256-colour fallbacks, Options > Colors and its config."""

import dataclasses

import pytest
from rich.color import Color, ColorSystem
from textual_vision.desktop import Background
from textual_vision.themes import THEME_TURBO_C, THEME_TURBO_PASCAL

from divide import config, themes
from divide.app import Divide
from divide.editor.theme import OUTPUT
from divide.ui.windows import EditorWindow, OutputWindow


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    yield
    themes.set_ansi16(False)
    themes.use(themes.DEFAULT)


async def settle(pilot, times: int = 6) -> None:
    for _ in range(times):
        await pilot.pause()


# The syntax colours divide had before the themes were gathered: the Borland
# themes keep them, cell for cell. "foreground/background/attributes", in CGA slots.
BORLAND_GOLDEN = {
    "div.replace": "lightcyan//",
    "div.modifier": "lightmagenta//",
    "div.var": "lightcyan//",
    "div.var.builtin": "lightgreen//",
    "div.var.def": "white//b",
    "div.format": "lightmagenta//",
    "div.loop": "white//b",
    "div.cond": "white//b",
    "div.keyword": "white//b",
    "div.capsule": "white//b",
    "div.location": "white//b",
    "div.subparser": "lightred//b",
    "div.multirep": "lightred//b",
    "div.include": "white//b",
    "div.path": "lightgreen//u",
    "div.tplvar": "white//b",
    "div.special": "lightred//",
    "div.comment": "lightgray//",
    "div.doc": "lightgray//b",
    "div.ignored": "lightgray//",
    "div.macro": "lightred//b",
    "div.friendly": "lightgray//",
    "div.property": "white//",
    "div.property.value": "lightcyan//",
    "div.string": "lightgreen//",
    "div.number": "lightmagenta//",
    "div.constant": "lightmagenta//",
    "div.operator": "yellow//",
    "div.function": "white//",
    "div.punct": "yellow//",
    "div.key": "lightcyan//",
    "div.error": "white/red/b",
    "html.tag": "cyan//",
    "html.attr": "cyan//",
    "html.string": "lightgreen//",
    "html.comment": "lightgray//",
    "html.entity": "lightmagenta//",
    "json.key": "white//b",
    "json.string": "lightgreen//",
    "json.number": "lightmagenta//",
    "json.constant": "lightmagenta//",
    "json.ref": "lightcyan//b",
    "json.punct": "yellow//",
    "json.comment": "lightgray//",
    "json.error": "white/red/b",
    "php.tag": "lightred//b",
    "php.keyword": "white//b",
    "php.string": "lightgreen//",
    "php.number": "lightmagenta//",
    "php.comment": "lightgray//",
    "php.variable": "lightcyan//",
    "php.variable.builtin": "lightcyan//b",
    "php.function": "white//",
    "php.function.builtin": "white//",
    "php.function.method": "white//",
    "php.constructor": "white//b",
    "php.type": "lightgreen//",
    "php.type.builtin": "lightgreen//",
    "php.module": "cyan//",
    "php.module.builtin": "cyan//",
    "php.constant": "lightmagenta//",
    "php.constant.builtin": "lightmagenta//b",
    "php.property": "lightcyan//",
    "php.operator": "yellow//",
    "diag.error": "white/red/",
    "dialector.focus": "black/lightcyan/b",
    "trace.new": "black/lightgreen/b",
    "trace.old": "white/red/b",
    "diag.warning": "white/brown/",  # its own colour: brown numbers vanished on it
}


def luminance(hex_: str) -> float:
    def channel(c: int) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("name", ["turbo-pascal", "turbo-c"])
def test_borland_themes_keep_their_colours(name):
    palette = themes.get(name)
    styles = palette.token_styles()
    assert set(BORLAND_GOLDEN) <= set(styles)  # the old kinds keep their colours; new kinds may join
    for kind, spec in BORLAND_GOLDEN.items():
        fg, bg, attrs = spec.split("/")
        style = styles[kind]
        assert (style.color.name.upper() if style.color else "") == (themes.CGA[fg] if fg else ""), kind
        assert (style.bgcolor.name.upper() if style.bgcolor else "") == (themes.CGA[bg] if bg else ""), kind
        assert bool(style.bold) == ("b" in attrs) and bool(style.underline) == ("u" in attrs), kind
    # the chrome is textual-vision's own theme, untouched
    library = {"turbo-pascal": THEME_TURBO_PASCAL, "turbo-c": THEME_TURBO_C}[name]
    theme = palette.textual_theme()
    for f in dataclasses.fields(library):
        if f.name != "variables":
            assert getattr(theme, f.name) == getattr(library, f.name), f.name
    assert library.variables.items() <= theme.variables.items()
    # divide's own colours as they were: desktop, editor, Output window, shadow
    assert (palette.colour("desktop"), palette.colour("desktop-pattern")) == ("#AAAAAA", "#0000AA")
    assert (palette.colour("editor-text"), palette.colour("editor-bg")) == ("#FFFF55", "#0000AA")
    assert (palette.colour("output-text"), palette.colour("output-bg")) == ("#FFFFFF", "#000000")
    assert (palette.colour("shadow-text"), palette.colour("shadow")) == ("#555555", "#000000")


@pytest.mark.parametrize("palette", themes.THEMES.values(), ids=list(themes.THEMES))
def test_every_theme_gives_every_colour(palette):
    assert set(palette.ansi) == set(themes.SLOTS)
    assert set(palette.ui) == set(themes.UI_ROLES)
    assert set(palette.syntax) == set(themes.SYNTAX_ROLES)
    for fg, bg, _ in themes.TOKENS.values():
        assert fg is None or fg in themes.SYNTAX_ROLES
        assert bg is None or bg in themes.SYNTAX_ROLES
    for role in (*themes.UI_ROLES, *themes.SYNTAX_ROLES):
        Color.parse(palette.colour(role))  # a real colour, slot or RGB
    variables = palette.textual_theme().variables
    library_keys = set(THEME_TURBO_PASCAL.variables)
    assert library_keys <= set(variables)  # textual-vision's widgets find theirs


@pytest.mark.parametrize("palette", themes.THEMES.values(), ids=list(themes.THEMES))
def test_syntax_is_legible(palette):
    bg = palette.colour("editor-bg")
    assert contrast(palette.colour("editor-text"), bg) >= 4.5
    for role in ("keyword", "name", "variable", "builtin", "string", "type", "number", "constant",
                 "modifier", "comment", "operator", "punct", "special", "markup", "module"):
        assert contrast(palette.colour(role), bg) >= 3.0, role
    for fg, back in (("error", "error-bg"), ("focus", "focus-bg"), ("inserted", "inserted-bg"), ("deleted", "deleted-bg"),
                     ("info-text", "info-bg"), ("list-focused", "list-focused-bg"),
                     ("history-focused", "history-focused-bg"), ("history-frame", "history-bg")):
        assert contrast(palette.colour(fg), palette.colour(back)) >= 3.0, fg
    # the chosen file of a list elsewhere: Turbo Vision's yellow on cyan is 2.7
    assert contrast(palette.colour("list-selected"), palette.colour("list-bg")) >= 2.5
    for fg, back in (("help-text", "help-bg"), ("debug-text", "debug-bg"), ("output-text", "output-bg"),
                     ("list-text", "list-bg"), ("history-text", "history-bg")):
        assert contrast(palette.colour(fg), palette.colour(back)) >= 4.5, fg


def test_modern_dark_chrome_is_legible():
    theme = themes.get("modern-dark").textual_theme()
    v = theme.variables
    assert contrast(v["text"], theme.surface) >= 4.5  # menus, dialogs
    assert contrast(v["text"], theme.accent) >= 3.0  # the selected menu item
    assert contrast(theme.surface, theme.accent) >= 3.0  # the selected list item
    assert contrast(theme.foreground, theme.background) >= 4.5  # frames
    assert contrast(v["input-fg"], v["input-bg"]) >= 4.5
    assert contrast(v["button-face-fg"], v["button-face-bg"]) >= 4.5


ANSI_INDEX = dict(zip(themes.SLOTS, (0, 4, 2, 6, 1, 5, 3, 7, 8, 12, 10, 14, 9, 13, 11, 15)))
PAIRS = [("editor-text", "editor-bg"), ("help-text", "help-bg"), ("debug-text", "debug-bg"), ("output-text", "output-bg")]


@pytest.mark.parametrize("palette", themes.THEMES.values(), ids=list(themes.THEMES))
def test_16_colours_keep_the_slots(palette):
    themes.set_ansi16(True)
    for slot, rgb in palette.ansi.items():
        assert Color.parse(palette.hex(rgb)).downgrade(ColorSystem.STANDARD).number == ANSI_INDEX[slot], slot
    for fg, bg in PAIRS:  # still two colours, not one
        a, b = (Color.parse(palette.colour(r)).downgrade(ColorSystem.STANDARD).number for r in (fg, bg))
        assert a != b, fg
    themes.set_ansi16(False)
    for fg, bg in PAIRS:  # and in the 256-colour cube
        a, b = (Color.parse(palette.colour(r)).downgrade(ColorSystem.EIGHT_BIT).number for r in (fg, bg))
        assert a != b, fg


async def test_switching_repaints_everything(tmp_path):
    path = tmp_path / "a.tpl"
    path.write_text("{$name}\n", encoding="utf-8")
    app = Divide(tmp_path, [path])
    async with app.run_test(size=(90, 26)) as pilot:
        await settle(pilot)
        editor = next(w for w in app.windows() if isinstance(w, EditorWindow)).editor
        assert app.theme == themes.DEFAULT and editor.theme == "turbo-pascal"
        output = OutputWindow(number=9)
        app.insert_window(output)
        await settle(pilot)
        assert output.view.kind == OUTPUT and output.view.theme == "turbo-pascal-output"
        app.theme = "modern-dark"
        await settle(pilot)
        palette = themes.current()
        assert palette.name == "modern-dark"
        assert editor.theme == "modern-dark" and output.view.theme == "modern-dark-output"
        desktop = app.screen.query_one(Background)
        assert desktop.styles.background.hex.upper() == palette.colour("desktop").upper()
        assert output.styles.background.hex.upper() == palette.colour("output-bg").upper()


async def test_options_colors_previews_and_remembers(tmp_path):
    path = tmp_path / "a.tpl"
    path.write_text("{$name}\n", encoding="utf-8")
    app = Divide(tmp_path, [path])
    async with app.run_test(size=(90, 30)) as pilot:
        await settle(pilot)
        await pilot.press("alt+o", "c")
        await settle(pilot)
        await pilot.press("m")  # Modern dark: previewed at once
        await settle(pilot)
        assert app.theme == "modern-dark"
        await pilot.press("escape")  # Cancel: back to the theme there was, nothing saved
        await settle(pilot)
        assert app.theme == "turbo-pascal" and "palette" not in config.load()
        await pilot.press("alt+o", "c")
        await settle(pilot)
        await pilot.press("f", "enter")  # Free Pascal, OK
        await settle(pilot)
        assert app.theme == "free-pascal"
        assert config.load()["palette"] == "free-pascal" and config.load()["colors"] == "auto"
    # the next start takes it; --palette still wins
    again = Divide(tmp_path, [])
    assert again.theme == "free-pascal"
    assert Divide(tmp_path, [], palette="turbo-c").theme == "turbo-c"


def test_colour_depth_can_be_forced(tmp_path):
    app = Divide(tmp_path, [], colors="16")
    assert app.console.color_system == "standard" and themes.ansi16()
    app = Divide(tmp_path, [], colors="truecolor")
    assert app.console.color_system == "truecolor" and not themes.ansi16()
