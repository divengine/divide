from pathlib import Path

from divide.lang.div.complete import CARET, complete
from divide.lang.div.dialect import DEFAULT_DIALECT, Dialect
from divide.lang.div.lexer import Lexer

DATA = {"title": "T", "site": {"name": "n"}, "products": [{"name": "P", "price": 1}]}


def run(text, dialect=DEFAULT_DIALECT, **kw):
    offset = text.index("|")
    text = text.replace("|", "")
    kw.setdefault("data", DATA)
    return complete(text, offset, Lexer(dialect).tokenize(text), dialect, **kw)


def labels(result):
    return [c.label for c in result.items]


def test_replacement_variables_and_closing_brace():
    r = run("<h1>{$ti|</h1>")
    assert r.context == "var" and r.prefix == "ti" and labels(r) == ["title"]
    assert r.items[0].insert == "title}"
    assert run("{$ti|}").items[0].insert == "title"  # the brace is already there
    assert "site.name" in labels(run("{^$|"))  # after a modifier too


def test_loop_offers_lists_first_and_closes_the_loop():
    r = run("[$|")
    assert r.context == "loop" and labels(r)[0] == "products"
    assert r.items[0].insert == "products]" and r.items[0].after == "[/$products]"
    assert run("[$|\n[/$products]").items[0].after == ""  # already closed further down


def test_loop_scope_and_item_name():
    r = run("[$products]{$|}[/$products]")
    names = labels(r)
    assert names[:3] == ["value", "value.name", "value.price"]
    assert {"name", "price", "_index", "_is_last", "title"} <= set(names)
    named = run("[$products] p => {$p.|")  # unclosed loop, named item
    assert labels(named) == ["p.name", "p.price"]


def test_close_loop_and_conditions():
    assert labels(run("[$products]x[/$|")) == ["products"]
    r = run("?$|")
    assert r.items[0].after == "$title?"
    assert "title" in labels(run("{?( $|"))
    assert run("var x = $|") is None  # not Div: no popup while typing
    assert run("var x = $|", explicit=True).context == "var"


def test_template_variables_and_used_names_are_offered():
    r = run("{= greeting: 'hi' =}{$other}{$|", data=None)
    assert labels(r) == ["greeting", "other"]


def test_tag_snippets_follow_the_dialect():
    r = run("x {?|", explicit=True)
    assert r.context == "tag" and r.prefix == "{?" and r.items[0].insert == f"{{?( {CARET} )?}}{{/?}}"
    loop = run("loop|", explicit=True)
    assert loop.items[0].insert == f"[${CARET}" and loop.items[0].retrigger
    custom = Dialect("x", {**DEFAULT_DIALECT.tags, "DIV_TAG_LOOP_BEGIN_PREFIX": "<<$", "DIV_TAG_LOOP_END_PREFIX": "<</$"})
    assert any(c.insert.startswith("<<$") for c in run("|", custom, explicit=True).items)
    assert run("plain text|") is None


def test_include_paths(tmp_path: Path):
    (tmp_path / "parts").mkdir()
    (tmp_path / "parts" / "menu.tpl").write_text("")
    (tmp_path / "page.tpl").write_text("")
    r = run("{% |", template=tmp_path / "page.tpl")
    assert r.context == "path" and labels(r) == ["parts/", "page"]
    assert r.items[0].retrigger and r.items[1].after == " %}"
    assert labels(run("{% parts/m|", template=tmp_path / "page.tpl")) == ["parts/menu"]
