import pytest

from divide.app import Divide
from divide.lang.divjson import DivJsonError, Ref, dumps, has_extensions, loads, references, tokenize
from divide.ui.windows import EditorWindow

SAMPLE = """// data
{name: 'Rafa', "copy": $name, "who": $person.name, "l": [1, 2.5, TRUE, null,], /* c */ "s": "a\\"b"}"""


def test_loads_div_extensions():
    assert loads(SAMPLE) == {
        "name": "Rafa",
        "copy": Ref("name"),
        "who": Ref("person.name"),
        "l": [1, 2.5, True, None],
        "s": 'a"b',
    }
    assert references(SAMPLE) == ["name", "person.name"]
    assert has_extensions(SAMPLE)
    assert not has_extensions('{"a": $b}')


def test_dumps_round_trip_keeps_refs_bare():
    value = loads(SAMPLE)
    text = dumps(value)
    assert '"copy": $name' in text and '"who": $person.name' in text
    assert loads(text) == value


@pytest.mark.parametrize(
    "bad, where",
    [('{"a": 1', (1, 8)), ('{"a" 1}', (1, 6)), ("[1 2]", (1, 4)), ('{\n "a": $}', (2, 7)), ('{"a": "x}', (1, 7))],
)
def test_errors_have_positions(bad, where):
    with pytest.raises(DivJsonError) as info:
        loads(bad)
    assert (info.value.line, info.value.column) == where


def test_tokens():
    kinds = {SAMPLE[t.start : t.end]: t.kind for t in tokenize(SAMPLE)}
    assert kinds["name"] == "json.key" and kinds['"copy"'] == "json.key"
    assert kinds["$person.name"] == "json.ref"
    assert kinds["TRUE"] == "json.constant" and kinds["'Rafa'"] == "json.string"
    assert kinds["/* c */"] == "json.comment"


async def test_json_editor_highlights_and_validates(tmp_path):
    f = tmp_path / "page.json"
    f.write_text('{"a": $b}')
    app = Divide(tmp_path, [f])
    async with app.run_test() as pilot:
        for _ in range(3):
            await pilot.pause()
        ed = app.query_one(EditorWindow).editor
        assert ed.lang == "json" and ed.json_error is None
        assert (6, 8, "json.ref") in ed._highlights[0]
        assert app.status_line._hint_text == "JSON ok · 1 $ref"
        ed.move_cursor((0, 9))
        await pilot.press("x")
        for _ in range(3):
            await pilot.pause()
        assert ed.json_error is not None
        assert app.status_line._hint_text.startswith("JSON [!] line 1, col 10")
