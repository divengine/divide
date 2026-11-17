"""A selected block is drawn in the selection's colours, over the syntax colours (as Borland's editors do)."""

from textual.widgets.text_area import Selection

from divide.app import Divide


async def settle(pilot, n=10):
    for _ in range(n):
        await pilot.pause()


async def test_a_selection_hides_the_syntax_colours(tmp_path):
    page = tmp_path / "page.tpl"
    page.write_text("<p>{$title}</p>\n[$products] product =>\n[/$products]\n")
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        ed = app.window_for(page).editor
        ed.selection = Selection((1, 0), (1, 11))  # [$products]
        await settle(pilot)
        strip = ed.render_line(1 - ed.scroll_offset.y)
        theme_selection = ed._theme.selection_style
        texts = [(seg.text, seg.style) for seg in strip if seg.text.strip()]
        chosen = "".join(t for t, s in texts if s and s.bgcolor == theme_selection.bgcolor)
        assert "[$products]" in chosen
        for text, style in texts:
            if style and style.bgcolor == theme_selection.bgcolor and text.strip() in "[$products]":
                assert style.color == theme_selection.color, (text, style)
        ed.selection = Selection((1, 3), (1, 3))
        await settle(pilot)
        strip = ed.render_line(1 - ed.scroll_offset.y)
        assert not any(seg.style and seg.style.bgcolor == theme_selection.bgcolor for seg in strip)
