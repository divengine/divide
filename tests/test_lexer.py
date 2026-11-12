from pathlib import Path

import pytest

from divide.lang.div import Dialect, resolve_dialect, tokenize
from divide.lang.div.dialect import lenient_json

ROOT = Path(__file__).resolve().parents[1]


def kinds(src: str, dialect: Dialect | None = None, html: bool = False) -> list[tuple[str, str]]:
    return [(t.kind, src[t.start : t.end]) for t in tokenize(src, dialect, html=html)]


def has(src: str, kind: str, text: str, **kw) -> bool:
    return (kind, text) in kinds(src, **kw)


def test_simple_replacement_and_modifiers():
    k = kinds("{$name} {^^title} {%%body} {html:x} {upper:x}")
    assert ("div.var", "name") in k
    assert ("div.modifier", "^^") in k
    assert ("div.modifier", "%%") in k
    assert ("div.modifier", "html:") in k
    assert ("div.modifier", "upper:") in k  # custom modifier


def test_submatch_kinds():
    k = kinds("{$b:~25}{$b:/30}{$b:0,11}{$v:%1$04d}")
    assert [x for x in k if x[0] in ("div.modifier", "div.format")] == [
        ("div.modifier", "~25"), ("div.modifier", "/30"), ("div.modifier", "0,11"), ("div.format", "%1$04d"),
    ]


def test_multi_modifiers():
    k = kinds("{$word|0,3|_|^|}")
    assert [t for kd, t in k if kd == "div.modifier"] == ["0,3", "_", "^"]


def test_aggregate():
    assert has("{$min:blocks-weight}", "div.function", "min")
    assert has("{$min:blocks-weight}", "div.var", "blocks-weight")


def test_loop_with_item_and_builtins():
    k = kinds("[$products] p => {$_index}{$p.name} @empty@ [/$products]")
    assert ("div.var.def", "p") in k
    assert ("div.var.builtin", "_index") in k
    assert ("div.keyword", "@empty@") in k
    assert k[-1] == ("div.loop", "]")


def test_orphan_and_unclosed_loops_are_errors():
    assert has("[/$x]", "div.error", "[/$x]")
    assert has("[$x] never closed", "div.error", "[$")


def test_conditional_parts_longest_key_with_close():
    # From divengine/div tests/cases/conditional-parts: no spaces between key and body.
    k = kinds("?$showYES@else@NO$show?|!$hideYES@else@NO$hide!")
    assert ("div.var", "show") in k and ("div.var", "hide") in k
    assert k.count(("div.keyword", "@else@")) == 2


def test_conditional_without_close_is_text():
    assert kinds("a ?$b c") == []


def test_conditions_expression_with_quoted_replacement():
    k = kinds('{?( "{$role}" === "admin" )?}x{/?}')
    assert ("div.var", "role") in k
    assert ("div.string", "admin") in k
    assert ("div.operator", "===") in k


def test_tplvar():
    k = kinds('{= *p: {name: "Potato", n: 4, ok: true} =}{= s: ->sum(1,2) =}{= c: $p =}')
    assert ("div.operator", "*") in k
    assert ("div.var.def", "p") in k
    assert ("div.key", "name") in k
    assert ("div.constant", "true") in k
    assert ("div.function", "->sum") in k
    assert ("div.var", "$p") in k


def test_tplvar_value_is_template_code():
    k = kinds("{= digits: [[:0,8:]{$value},[/]9] =}")
    assert ("div.loop", "[:") in k and ("div.loop", "[/]") in k
    assert ("div.var.builtin", "value") in k


def test_formula_with_format():
    k = kinds("(# {$price} + {$tax} :2. #)")
    assert ("div.format", "2.") in k
    assert ("div.operator", "+") in k


def test_includes_and_locations_and_capsules():
    k = kinds("{% layout %}{%% part %%}(( header )){{header H header}}[[product {$name} product]]")
    assert ("div.path", "layout") in k and ("div.path", "part") in k
    assert ("div.var.def", "header") in k
    assert ("div.location", "{{") in k and ("div.location", "}}") in k
    assert ("div.capsule", "[[") in k and ("div.capsule", "]]") in k


def test_subparser_and_multireplacement():
    k = kinds("{parse:beforeParse} {$n} {/parse:beforeParse}{:tags}x{:/tags}")
    assert ("div.subparser", "parse") in k
    assert ("div.constant", "beforeParse") in k
    assert ("div.multirep", "{:/") in k


def test_ignore_comment_macro():
    k = kinds("{ignore}{$x}{/ignore}<!--{ @name T\n @vars: x }--><? $i = 1; ?>")
    assert ("div.ignored", "{$x}") in k
    assert ("div.doc", "@name") in k
    assert ("div.var", "$i") in k


def test_special_and_property():
    k = kinds("@_DIALECT = x.dialect\n{\\n}{\\$}")
    assert ("div.property", "@_DIALECT") in k
    assert ("div.special", "{\\n}") in k


def test_html_strings_survive_div_tags():
    k = kinds('<option value="{$val}">{$text}</option>', html=True)
    assert ("html.attr", "value") in k
    assert ("div.var", "val") in k
    assert ("html.tag", "</option") in k


def test_dialect_overrides():
    d = Dialect.from_overrides({
        "DIV_TAG_REPLACEMENT_PREFIX": "<<", "DIV_TAG_REPLACEMENT_SUFFIX": ">>",
        "DIV_TAG_LOOP_BEGIN_PREFIX": "<%", "DIV_TAG_LOOP_BEGIN_SUFFIX": "%>",
        "DIV_TAG_LOOP_END_PREFIX": "</%", "DIV_TAG_LOOP_END_SUFFIX": "%>",
    })
    k = kinds("<%items%><<$value>></%items%>", d)
    assert ("div.loop", "<%") in k and ("div.var.builtin", "value") in k and ("div.loop", "</%") in k
    assert kinds("{$value}", d) == []


def test_lenient_dialect_json():
    assert lenient_json("{'DIV_TAG_COMMENT_BEGIN': '{*', DIV_TAG_COMMENT_END: '*}',}") == {
        "DIV_TAG_COMMENT_BEGIN": "{*", "DIV_TAG_COMMENT_END": "*}",
    }


def test_resolve_dialect_relative_to_template(tmp_path):
    (tmp_path / "angle.dialect").write_text('{"DIV_TAG_REPLACEMENT_PREFIX": "<<", "DIV_TAG_REPLACEMENT_SUFFIX": ">>"}')
    tpl = tmp_path / "a.tpl"
    text = "@_DIALECT = angle.dialect\nHello <<$name>>"
    d = resolve_dialect(text, tpl)
    assert d.name == "angle" and d.error is None
    missing = resolve_dialect("@_DIALECT = nope.dialect\n", tpl)
    assert missing.error


@pytest.mark.parametrize("path", sorted((ROOT / "examples").glob("*.tpl")))
def test_examples_tokens_are_sane(path):
    text = path.read_text()
    toks = tokenize(text)
    assert toks or not text.strip()
    prev_end = 0
    for t in toks:
        assert 0 <= t.start < t.end <= len(text)
        assert t.start >= prev_end, f"overlap at {t}"
        prev_end = t.end
