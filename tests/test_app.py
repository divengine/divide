import shutil
from pathlib import Path

from divide.app import Divide, EditorPane

ROOT = Path(__file__).resolve().parents[1]


async def test_open_edit_save(tmp_path):
    tpl = tmp_path / "showcase.tpl"
    shutil.copy(ROOT / "examples" / "showcase.tpl", tpl)
    app = Divide(tmp_path, [tpl])
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        pane = app.query_one(EditorPane)
        ed = pane.editor
        assert ed.div_enabled
        assert any(ed._highlights.values()), "no highlights built"
        names = {h[2] for line in ed._highlights.values() for h in line}
        assert {"div.loop", "div.var", "div.tplvar", "div.comment"} <= names
        ed.move_cursor((0, 0))
        await pilot.press("X")
        assert pane.dirty
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert tpl.read_text().startswith("X<!--{")
        assert not pane.dirty


async def test_dialect_detected(tmp_path):
    (tmp_path / "angle.dialect").write_text("{'DIV_TAG_REPLACEMENT_PREFIX': '<<', 'DIV_TAG_REPLACEMENT_SUFFIX': '>>'}")
    tpl = tmp_path / "a.tpl"
    tpl.write_text("@_DIALECT = angle.dialect\nHello <<$name>>\n")
    app = Divide(tmp_path, [tpl])
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app.query_one(EditorPane).editor
        assert ed.dialect.name == "angle"
        assert (6, 8, "div.replace") in ed._highlights[1]


async def test_close_dirty_tab_asks(tmp_path):
    f = tmp_path / "x.tpl"
    f.write_text("{$a}")
    app = Divide(tmp_path, [f])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("Z")
        await pilot.press("ctrl+w")
        await pilot.pause()
        await pilot.click("#discard")
        await pilot.pause()
        assert not list(app.query(EditorPane))
        assert f.read_text() == "{$a}"
