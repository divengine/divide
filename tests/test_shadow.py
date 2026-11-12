from pathlib import Path

from textual.geometry import Region
from textual_vision.menus import MenuBox

from divide.app import Divide
from divide.ui.shadow import SHADOW_STYLE, compute_shadow_spans, shadow_regions


class Fake:
    def __init__(self, name, parent=None, casts=False):
        self.name, self.casts = name, casts
        self.ancestors = ([parent] + parent.ancestors) if parent else []


def test_shadow_regions_offset_two_one():
    assert shadow_regions(Region(10, 5, 20, 8)) == [Region(30, 6, 2, 8), Region(12, 13, 18, 1)]


def test_shadow_hidden_by_front_widgets_but_not_by_own_children():
    screen = Region(0, 0, 80, 25)
    back = Fake("back", casts=True)
    child = Fake("child", parent=back)
    front = Fake("front")
    widgets = [  # front to back
        (front, Region(31, 0, 10, 8), screen),  # covers the shadow's right strip down to row 7
        (child, Region(10, 5, 20, 8), screen),
        (back, Region(10, 5, 20, 8), screen),
    ]
    spans, rects = compute_shadow_spans(widgets, lambda w: w.casts)
    assert spans[6] == [(30, 31)]  # column 31 hidden by `front`
    assert spans[8] == [(30, 32)]
    assert spans[13] == [(12, 32)]
    assert 5 not in spans
    assert len(rects) == 2


def test_shadow_clipped_to_container():
    caster = Fake("w", casts=True)
    spans, _ = compute_shadow_spans([(caster, Region(0, 1, 80, 23), Region(0, 1, 80, 23))], lambda w: w.casts)
    assert spans == {}  # a window filling the desktop has no visible shadow


async def test_menu_casts_shadow_on_screen(tmp_path):
    f = tmp_path / "a.tpl"
    f.write_text("\n".join("x" * 60 for _ in range(30)))
    app = Divide(tmp_path, [f])
    async with app.run_test(size=(100, 30)) as pilot:
        for _ in range(3):
            await pilot.pause()
        await pilot.press("alt+w")
        for _ in range(3):
            await pilot.pause()
        box = app.screen.query_one(MenuBox)
        x, y, w, h = box.region
        strips = app.screen._compositor.render_strips()

        def style_at(cx, cy):
            line = strips[cy].crop(cx, cx + 1)
            return next(iter(line)).style

        shadow = style_at(x + w, y + 2)
        assert shadow.bgcolor == SHADOW_STYLE.bgcolor and shadow.color == SHADOW_STYLE.color
        assert style_at(x + w + 3, y + 2).bgcolor != SHADOW_STYLE.bgcolor
        assert style_at(x + 2, y + h).bgcolor == SHADOW_STYLE.bgcolor
        assert style_at(x + 1, y + h).bgcolor != SHADOW_STYLE.bgcolor  # starts 2 columns in
