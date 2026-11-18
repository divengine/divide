"""The interface in other languages (divide.i18n): catalogues, hotkeys, placeholders, glyphs."""

import ast
import string
from collections import Counter
from pathlib import Path

import pytest
from babel.messages.pofile import read_po
from rich.cells import cell_len

from divide import i18n
from divide.app import Divide
from divide.ui.dialogs import DialogScreen

SRC = Path(i18n.__file__).parent
CATALOGUES = sorted(i18n.LOCALE_DIR.glob("*/LC_MESSAGES/divide.po"))
HOTKEY = "~"


def messages(po: Path):
    for m in read_po(po.open("rb")):
        if m.id:
            ids = m.id if isinstance(m.id, tuple) else (m.id,)
            strs = m.string if isinstance(m.string, tuple) else (m.string,)
            yield m, ids, strs


def fields(text: str) -> Counter:
    try:
        return Counter(f for _, f, _, _ in string.Formatter().parse(text) if f is not None)
    except ValueError:  # Div code in the text ({= ... =}): kept as it is
        return Counter(c for c in text if c in "{}")


@pytest.fixture
def spanish():
    i18n.use("es")
    yield
    i18n.use("en")


def test_catalogues_exist():
    assert {p.parent.parent.name for p in CATALOGUES} == {"es"}
    assert "es" in i18n.available() and i18n.available()[0] == "en"
    pot = {m.id for m in read_po((i18n.LOCALE_DIR / "divide.pot").open("rb")) if m.id}
    for po in CATALOGUES:
        assert {m.id for m, _, _ in messages(po)} == pot, f"{po}: tools/i18n.py update"
        assert po.with_suffix(".mo").stat().st_mtime >= po.stat().st_mtime - 1, f"{po}: tools/i18n.py compile"


@pytest.mark.parametrize("po", CATALOGUES, ids=lambda p: p.parent.parent.name)
def test_every_text_is_translated_and_keeps_its_marks(po):
    for message, ids, strs in messages(po):
        assert all(strs) and not message.fuzzy, f"untranslated: {ids[0]!r}"
        for msgid, msgstr in zip(ids * len(strs), strs):
            assert fields(msgid) == fields(msgstr), f"placeholders differ: {msgid!r} -> {msgstr!r}"
            assert msgid.count(HOTKEY) == msgstr.count(HOTKEY), f"hotkey marks: {msgid!r} -> {msgstr!r}"
            if HOTKEY in msgstr:
                hot = msgstr.split(HOTKEY)[1]
                assert hot and (len(hot) == 1 or hot.startswith(("F", "Alt+"))), f"one letter: {msgstr!r}"


@pytest.mark.parametrize("po", CATALOGUES, ids=lambda p: p.parent.parent.name)
def test_translations_are_single_width(po):
    """A grid of cells: every character one cell wide (Latin-1 letters and CP437, no emoji)."""
    for _, _, strs in messages(po):
        for text in strs:
            bad = [c for c in text if c != "\n" and cell_len(c) != 1]
            assert not bad, f"{text!r}: {bad}"


def unique_hotkeys(items: list[str], where: str) -> None:
    keys = [t.split(HOTKEY)[1].lower() for t in items if t.count(HOTKEY) >= 2]
    repeated = [k for k, n in Counter(keys).items() if n > 1]
    assert not repeated, f"{where}: {repeated} in {items}"


@pytest.mark.parametrize("language", ["en", "es"])
def test_menu_hotkeys_are_unique(language):
    i18n.use(language)
    try:
        bar = Divide.__new__(Divide).init_menu_bar()
        unique_hotkeys([m.name for m in bar.items], "menu bar")
        for menu in bar.items:
            unique_hotkeys([i.name for i in menu.sub_menu.items if not i.is_separator], menu.plain_name)
    finally:
        i18n.use("en")


def dialog_texts(dialog) -> list[str]:
    texts = []
    for widget in dialog.walk_children():
        if isinstance(getattr(widget, "_text", None), str):
            texts.append(widget._text)
        items = getattr(widget, "_items", None)
        if isinstance(items, list) and all(isinstance(i, str) for i in items):
            texts.extend(items)
    return texts


def test_dialogs_in_spanish():
    """divide started in Spanish (texts are made at import, so in a process of its own)."""
    import os
    import subprocess
    import sys

    env = {**os.environ, "DIVIDE_LANGUAGE": "es"}
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", __file__, "-k", "spanish_process"],
                          env=env, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout[-3000:]


@pytest.mark.skipif(i18n.current != "es", reason="run by test_dialogs_in_spanish, in a process started in Spanish")
async def test_spanish_process(tmp_path):
    """The main dialogs open in Spanish, each with its own hotkeys."""
    page = tmp_path / "page.tpl"
    page.write_text("{$title}\n", encoding="utf-8")
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(110, 34)) as pilot:
        for _ in range(8):
            await pilot.pause()
        for keys in (["f3"], ["ctrl+f"], ["ctrl+r"], ["shift+f2"], ["ctrl+g"], ["alt+o", "c"], ["alt+o", "i"]):
            await pilot.press(*keys)
            for _ in range(8):
                await pilot.pause()
            screen = app.screen
            assert isinstance(screen, DialogScreen), keys
            texts = dialog_texts(screen.dialog)
            assert texts and any(t != i18n.SOURCE for t in texts)
            unique_hotkeys(texts, f"{keys}: {screen.dialog.title}")
            await pilot.press("escape")
            for _ in range(6):
                await pilot.pause()
        assert app.menu_bar.menu.items[0].name == "~A~rchivo"


def test_language_choice(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG", "DIVIDE_LANGUAGE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    assert i18n.system_language() == "es" and i18n.chosen() == "es"
    monkeypatch.setenv("LANGUAGE", "fr_FR:en")
    assert i18n.system_language() == "fr"
    (tmp_path / "divide").mkdir()
    (tmp_path / "divide" / "config.json").write_text('{"language": "en"}', encoding="utf-8")
    assert i18n.chosen() == "en"  # Options > Language over the system's
    monkeypatch.setenv("DIVIDE_LANGUAGE", "es")
    assert i18n.chosen() == "es"  # the environment over all
    assert i18n.argv_language(["/usr/bin/divide", "--language", "es"]) == "es"
    assert i18n.argv_language(["divide", "--language=en", "x"]) == "en"
    assert i18n.argv_language(["pytest", "--language", "es"]) is None
    try:
        assert i18n.use("fr") == "en"  # no catalogue: English
        assert i18n.use("es_ES") == "es" and i18n._("Cancel") == "Cancelar"
    finally:
        i18n.use("en")


def test_no_local_underscore_hides_gettext():
    """``x, _ = ...`` in a function that also calls ``_("...")`` breaks it at run time."""
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = [n for stmt in fn.body for n in ast.walk(stmt)]
            comps = {id(n) for c in body if isinstance(c, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp))
                     for n in ast.walk(c)}
            stores = [n.lineno for n in body if isinstance(n, ast.Name) and n.id == "_"
                      and isinstance(n.ctx, ast.Store) and id(n) not in comps]
            calls = any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_" for n in body)
            assert not (stores and calls), f"{path.name}:{fn.name} assigns _ at {stores}"
