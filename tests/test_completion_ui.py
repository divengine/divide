from divide.app import Divide
from divide.ui.windows import EditorWindow


async def settle(pilot, n=4):
    for _ in range(n):
        await pilot.pause()


async def test_popup_while_typing_and_accept(tmp_path):
    (tmp_path / "page.tpl").write_text("")
    (tmp_path / "page.json").write_text('{"title": "T", "products": [{"name": "a", "price": 2}]}')
    app = Divide(tmp_path, [tmp_path / "page.tpl"])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        ed = app.query_one(EditorWindow).editor
        await pilot.press("[", "$")
        await settle(pilot)
        assert ed.completing and [c.label for c in ed._popup.items] == ["products", "title"]
        await pilot.press("enter")
        await settle(pilot)
        assert ed.text == "[$products][/$products]" and ed.cursor_location == (0, 11)

        await pilot.press("{", "$", "p", "r")
        await settle(pilot)
        assert [c.label for c in ed._popup.items][:2] == ["price", "products"]
        await pilot.press("tab")
        await settle(pilot)
        assert ed.text == "[$products]{$price}[/$products]" and not ed.completing

        await pilot.press("ctrl+@")  # Ctrl+Space: Div tags
        await settle(pilot)
        assert ed.completing and ed._popup.result.context == "tag"
        await pilot.press("escape")
        await settle(pilot)
        assert not ed.completing and ed.text == "[$products]{$price}[/$products]"


async def test_snippet_reopens_the_list(tmp_path):
    (tmp_path / "page.tpl").write_text("")
    (tmp_path / "parts").mkdir()
    (tmp_path / "parts" / "menu.tpl").write_text("")
    app = Divide(tmp_path, [tmp_path / "page.tpl"])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        ed = app.query_one(EditorWindow).editor
        await pilot.press("{", "%", "ctrl+@")
        await settle(pilot)
        assert ed._popup.result.context == "tag"
        assert ed._popup.selected.detail == "include"
        await pilot.press("enter")  # {% , then the paths
        await settle(pilot)
        assert ed.text == "{% " and ed._popup.result.context == "path"
        await pilot.press("enter")  # parts/ , then its templates
        await settle(pilot)
        assert ed.text == "{% parts/" and ed.completing
        await pilot.press("enter")
        await settle(pilot)
        assert ed.text == "{% parts/menu %}"
