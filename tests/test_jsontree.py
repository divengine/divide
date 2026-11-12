from textual_vision.input_line import InputLine

from divide.app import Divide
from divide.lang.divjson import Ref, loads
from divide.ui.dialogs import DialogScreen, MessageBox
from divide.ui.jsontree import EditItemDialog, JsonTreeWindow
from divide.ui.windows import EditorWindow

DATA = '{\n  "title": "Demo",\n  "products": [\n    {"name": "Potato"}\n  ]\n}\n'


async def settle(pilot, n=4):
    for _ in range(n):
        await pilot.pause()


async def open_tree(pilot, app):
    await pilot.press("ctrl+t")
    await settle(pilot)
    tree_win = app.active_window()
    assert isinstance(tree_win, JsonTreeWindow)
    return tree_win


def goto(tree_win, path):
    tree = tree_win.json_tree

    def find(node):
        if node.data == path:
            return node
        for child in node.children:
            if hit := find(child):
                return hit
        return None

    node = find(tree.root)
    assert node is not None, path
    parent = node.parent
    while parent is not None:
        parent.expand()
        parent = parent.parent
    tree.move_cursor(node)


async def fill_dialog(pilot, app, *, key=None, type_=None, value=None):
    dialog = app.screen.query_one(EditItemDialog)
    if key is not None:
        dialog.key_input.data = key
    if type_ is not None:
        dialog.types.value = 1 << ["String", "Number", "True", "False", "Null", "Reference", "Object", "Array"].index(type_)
    if value is not None:
        dialog.value_input.data = value
    await pilot.click("#ok")
    await settle(pilot)


async def test_tree_edit_add_delete_undo_save(tmp_path):
    f = tmp_path / "page.json"
    f.write_text(DATA)
    app = Divide(tmp_path, [f])
    async with app.run_test(size=(100, 34)) as pilot:
        await settle(pilot)
        code = app.query_one(EditorWindow)
        tree_win = await open_tree(pilot, app)
        assert app.focused is tree_win.json_tree

        # edit: title becomes a reference, renamed to "heading"
        goto(tree_win, ("title",))
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)
        await fill_dialog(pilot, app, key="heading", type_="Reference", value="$site.title")
        assert loads(code.editor.text) == {"heading": Ref("site.title"), "products": [{"name": "Potato"}]}
        assert '"heading": $site.title' in code.editor.text
        assert code.dirty and f.read_text() == DATA

        # add after the cursor: a number member
        await pilot.press("insert")
        await settle(pilot)
        await fill_dialog(pilot, app, key="count", type_="Number", value="3")
        assert list(loads(code.editor.text)) == ["heading", "count", "products"]

        # add into an open array
        goto(tree_win, ("products",))
        await settle(pilot)
        await pilot.press("insert")
        await settle(pilot)
        await fill_dialog(pilot, app, type_="String", value="Tomato")
        assert loads(code.editor.text)["products"] == [{"name": "Potato"}, "Tomato"]

        # move it up, delete it
        await pilot.press("ctrl+up")
        await settle(pilot)
        assert loads(code.editor.text)["products"] == ["Tomato", {"name": "Potato"}]
        await pilot.press("delete")
        await settle(pilot)
        assert loads(code.editor.text)["products"] == [{"name": "Potato"}]

        # undo goes through the code editor's history
        await pilot.press("ctrl+z")
        await settle(pilot)
        assert loads(code.editor.text)["products"] == ["Tomato", {"name": "Potato"}]

        # F2 in the tree saves the file
        await pilot.press("f2")
        await settle(pilot)
        assert loads(f.read_text())["products"] == ["Tomato", {"name": "Potato"}]
        assert not code.dirty


async def test_code_edits_rebuild_tree_and_ctrl_t_flips(tmp_path):
    f = tmp_path / "page.json"
    f.write_text('{"a": 1}')
    app = Divide(tmp_path, [f])
    async with app.run_test(size=(100, 34)) as pilot:
        await settle(pilot)
        code = app.query_one(EditorWindow)
        tree_win = await open_tree(pilot, app)
        await pilot.press("ctrl+t")  # back to the code
        await settle(pilot)
        assert app.active_window() is code
        code.editor.load_text('{"a": 1, "b": [true]}')
        await settle(pilot)
        assert tree_win.value == {"a": 1, "b": [True]}
        code.editor.load_text('{"a": ')
        await settle(pilot)
        assert tree_win.error is not None and "[invalid JSON]" in tree_win.title
        assert tree_win.value == {"a": 1, "b": [True]}  # the last good tree stays
        await pilot.press("ctrl+t")
        await settle(pilot)
        await pilot.press("enter")  # editing is refused while the JSON is broken
        await settle(pilot)
        assert isinstance(app.screen, DialogScreen) and "Fix the JSON" in app.screen.dialog._text


async def test_rewrite_warning_for_div_extensions(tmp_path):
    f = tmp_path / "page.json"
    f.write_text("// comment\n{name: 'x'}")
    app = Divide(tmp_path, [f])
    async with app.run_test(size=(100, 34)) as pilot:
        await settle(pilot)
        code = app.query_one(EditorWindow)
        tree_win = await open_tree(pilot, app)
        goto(tree_win, ("name",))
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)
        assert isinstance(app.screen.dialog, MessageBox)
        await pilot.press("n")  # keep the file as it is
        await settle(pilot)
        assert code.editor.text.startswith("// comment")
        await pilot.press("enter")
        await settle(pilot)
        await pilot.press("y")
        await settle(pilot)
        await fill_dialog(pilot, app, value="y")
        assert code.editor.text == '{\n  "name": "y"\n}\n'


async def test_tree_closes_with_its_code_window(tmp_path):
    f = tmp_path / "page.json"
    f.write_text("{}")
    app = Divide(tmp_path, [f])
    async with app.run_test(size=(100, 34)) as pilot:
        await settle(pilot)
        await open_tree(pilot, app)
        await pilot.press("ctrl+t", "alt+f3")
        await settle(pilot)
        assert not app.tree_windows() and not app.editor_windows()


async def test_template_ctrl_t_opens_its_data_tree(tmp_path):
    tpl = tmp_path / "page.tpl"
    tpl.write_text("{$a}")
    app = Divide(tmp_path, [tpl])
    async with app.run_test(size=(100, 34)) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+t")  # page.json does not exist: created, then its tree
        await settle(pilot)
        tree_win = app.active_window()
        assert isinstance(tree_win, JsonTreeWindow)
        assert tree_win.source.path == (tmp_path / "page.json").resolve()
        assert tree_win.value == {}
        await pilot.press("insert")
        await settle(pilot)
        dialog = app.screen.query_one(EditItemDialog)
        assert app.focused is dialog.query(InputLine).first()  # the key field
        await fill_dialog(pilot, app, key="a", value="hello")
        assert loads(tree_win.source.editor.text) == {"a": "hello"}
