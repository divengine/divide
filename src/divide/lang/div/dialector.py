"""The dialector: building blocks of the Div dialect assistant (UI-independent).

A dialect is a set of ``DIV_TAG_*`` overrides (see ``dialect.py``). The
assistant groups the tags in sections; each section has an example snippet
written with ``{ DIV_TAG_X }`` placeholders (the examples come from the
original web dialector, divengine/dialector), so any dialect can be shown
filled in, with the place of every tag known.

Whether a dialect is valid, and whether Div reads it back, is not decided
here: Div answers that (``divide.run.render.check_dialect``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

from divide.lang.div.dialect import DEFAULT_TAGS

PLACEHOLDER = re.compile(r"\{ (DIV_TAG_\w+) \}")


@dataclass(frozen=True)
class Section:
    title: str
    about: str
    fields: tuple[tuple[str, str], ...]  # (DIV_TAG_ key, label)
    example: str

    @property
    def keys(self) -> list[str]:
        return [k for k, _ in self.fields]


def _t(name: str) -> str:
    return "{ DIV_TAG_" + name + " }"


R, S, D = _t("REPLACEMENT_PREFIX"), _t("REPLACEMENT_SUFFIX"), _t("MODIFIER_SIMPLE")


def _var(name: str, modifier: str = D) -> str:
    return f"{R}{modifier}{name}{S}"


SECTIONS: tuple[Section, ...] = (
    Section(
        "Replacements",
        "How a variable is written: {$name}, {$person.name}, {$name:...}",
        (
            ("DIV_TAG_REPLACEMENT_PREFIX", "Prefix"),
            ("DIV_TAG_MODIFIER_SIMPLE", "Simple replacement"),
            ("DIV_TAG_REPLACEMENT_SUFFIX", "Suffix"),
            ("DIV_TAG_VAR_MEMBER_DELIMITER", "Member delimiter"),
            ("DIV_TAG_SUBMATCH_SEPARATOR", "Substring separator"),
        ),
        f"Hello {_var('name')}\n"
        f"{R}{D}person{_t('VAR_MEMBER_DELIMITER')}name{S}\n"
        f"{R}{D}name{_t('SUBMATCH_SEPARATOR')}{_t('MODIFIER_TRUNCATE')}100{S}\n",
    ),
    Section(
        "Modifiers",
        "One-character transformations: {^name}, {_name}, {%name}, {html:name}...",
        (
            ("DIV_TAG_MODIFIER_CAPITALIZE_FIRST", "Capitalize first"),
            ("DIV_TAG_MODIFIER_CAPITALIZE_WORDS", "Capitalize words"),
            ("DIV_TAG_MODIFIER_UPPERCASE", "Upper case"),
            ("DIV_TAG_MODIFIER_LOWERCASE", "Lower case"),
            ("DIV_TAG_MODIFIER_LENGTH", "String length"),
            ("DIV_TAG_MODIFIER_COUNT_WORDS", "Count words"),
            ("DIV_TAG_MODIFIER_COUNT_SENTENCES", "Count sentences"),
            ("DIV_TAG_MODIFIER_COUNT_PARAGRAPHS", "Count paragraphs"),
            ("DIV_TAG_MODIFIER_ENCODE_URL", "URL encode"),
            ("DIV_TAG_MODIFIER_ENCODE_RAW_URL", "Raw URL encode"),
            ("DIV_TAG_MODIFIER_ENCODE_JSON", "JSON encode"),
            ("DIV_TAG_MODIFIER_HTML_ENTITIES", "HTML entities"),
            ("DIV_TAG_MODIFIER_NL2BR", "New line to <br>"),
            ("DIV_TAG_MODIFIER_SINGLE_QUOTES", "Escape quotes"),
            ("DIV_TAG_MODIFIER_JS", "JavaScript code"),
            ("DIV_TAG_MODIFIER_TRUNCATE", "Truncate"),
            ("DIV_TAG_MODIFIER_WORDWRAP", "Word wrap"),
            ("DIV_TAG_MODIFIER_SUBSTRING_SEPARATOR", "Substring range"),
            ("DIV_TAG_MODIFIER_FORMAT", "Format (sprintf)"),
        ),
        f"Capitalize first: {_var('name', _t('MODIFIER_CAPITALIZE_FIRST'))}\n"
        f"Capitalize words: {_var('name', _t('MODIFIER_CAPITALIZE_WORDS'))}\n"
        f"Upper case: {_var('name', _t('MODIFIER_UPPERCASE'))}\n"
        f"Lower case: {_var('name', _t('MODIFIER_LOWERCASE'))}\n"
        f"Length: {_var('name', _t('MODIFIER_LENGTH'))}\n"
        f"Words: {_var('name', _t('MODIFIER_COUNT_WORDS'))}\n"
        f"Sentences: {_var('name', _t('MODIFIER_COUNT_SENTENCES'))}\n"
        f"Paragraphs: {_var('name', _t('MODIFIER_COUNT_PARAGRAPHS'))}\n"
        f"URL encode: {_var('name', _t('MODIFIER_ENCODE_URL'))}\n"
        f"Raw URL encode: {_var('name', _t('MODIFIER_ENCODE_RAW_URL'))}\n"
        f"JSON encode: {_var('name', _t('MODIFIER_ENCODE_JSON'))}\n"
        f"HTML entities: {_var('name', _t('MODIFIER_HTML_ENTITIES'))}\n"
        f"New lines: {_var('name', _t('MODIFIER_NL2BR'))}\n"
        f"Single quotes: {_var('name', _t('MODIFIER_SINGLE_QUOTES'))}\n"
        f"JavaScript: {_var('name', _t('MODIFIER_JS'))}\n"
        f"Truncate: {R}{D}name{_t('SUBMATCH_SEPARATOR')}{_t('MODIFIER_TRUNCATE')}100{S}\n"
        f"Word wrap: {R}{D}name{_t('SUBMATCH_SEPARATOR')}{_t('MODIFIER_WORDWRAP')}100{S}\n"
        f"Substring: {R}{D}name{_t('SUBMATCH_SEPARATOR')}1{_t('MODIFIER_SUBSTRING_SEPARATOR')}2{S}\n"
        f"Format: {R}{D}name{_t('SUBMATCH_SEPARATOR')}{_t('MODIFIER_FORMAT')}.2f{S}\n",
    ),
    Section(
        "Multiple modifiers",
        "Several modifiers on one variable: {$name|^|_|}",
        (
            ("DIV_TAG_MULTI_MODIFIERS_PREFIX", "Prefix"),
            ("DIV_TAG_MULTI_MODIFIERS_OPERATOR", "Operator"),
            ("DIV_TAG_MULTI_MODIFIERS_SEPARATOR", "Separator"),
            ("DIV_TAG_MULTI_MODIFIERS_SUFFIX", "Suffix"),
        ),
        f"{_t('MULTI_MODIFIERS_PREFIX')}name{_t('MULTI_MODIFIERS_OPERATOR')}{_t('MODIFIER_UPPERCASE')}"
        f"{_t('MULTI_MODIFIERS_SEPARATOR')}{_t('MODIFIER_LOWERCASE')}{_t('MULTI_MODIFIERS_SUFFIX')}\n",
    ),
    Section(
        "Template variables",
        "Variables defined in the template: {= products: [...] =}, and default replacements",
        (
            ("DIV_TAG_TPLVAR_BEGIN", "Begin"),
            ("DIV_TAG_TPLVAR_ASSIGN_OPERATOR", "Assignment"),
            ("DIV_TAG_TPLVAR_PROTECTOR", "Protector"),
            ("DIV_TAG_TPLVAR_END", "End"),
            ("DIV_TAG_DEFAULT_REPLACEMENT_BEGIN", "Default repl. begin"),
            ("DIV_TAG_DEFAULT_REPLACEMENT_END", "Default repl. end"),
        ),
        f"{_t('TPLVAR_BEGIN')} {_t('TPLVAR_PROTECTOR')}products{_t('TPLVAR_ASSIGN_OPERATOR')} [\n"
        '  {name: "Potato", price: 20},\n'
        '  {name: "Banana", price: 10}\n'
        f"]{_t('TPLVAR_END')}\n"
        f"{_t('DEFAULT_REPLACEMENT_BEGIN')} [true, 'YES'] {_t('DEFAULT_REPLACEMENT_END')}\n",
    ),
    Section(
        "Loops and iterations",
        "[$products] ... @empty@ ... [/$products], and [:1,10:] ... [/]",
        (
            ("DIV_TAG_LOOP_BEGIN_PREFIX", "Begin prefix"),
            ("DIV_TAG_LOOP_BEGIN_SUFFIX", "Begin suffix"),
            ("DIV_TAG_LOOP_END_PREFIX", "End prefix"),
            ("DIV_TAG_LOOP_END_SUFFIX", "End suffix"),
            ("DIV_TAG_LOOP_VAR_SEPARATOR", "Item variable separator"),
            ("DIV_TAG_EMPTY", "Empty"),
            ("DIV_TAG_BREAK", "Break"),
            ("DIV_TAG_ITERATION_BEGIN_PREFIX", "Iteration prefix"),
            ("DIV_TAG_ITERATION_PARAM_SEPARATOR", "Iteration arguments"),
            ("DIV_TAG_ITERATION_BEGIN_SUFFIX", "Iteration suffix"),
            ("DIV_TAG_ITERATION_END", "Iteration end"),
        ),
        f"{_t('LOOP_BEGIN_PREFIX')}products{_t('LOOP_BEGIN_SUFFIX')} product {_t('LOOP_VAR_SEPARATOR')}\n"
        f"  Name: {R}{D}product{_t('VAR_MEMBER_DELIMITER')}name{S}\n"
        f"  {_t('BREAK')}\n"
        f"{_t('EMPTY')}\n"
        "  No products\n"
        f"{_t('LOOP_END_PREFIX')}products{_t('LOOP_END_SUFFIX')}\n"
        f"{_t('ITERATION_BEGIN_PREFIX')}1{_t('ITERATION_PARAM_SEPARATOR')}10{_t('ITERATION_PARAM_SEPARATOR')}i"
        f"{_t('ITERATION_PARAM_SEPARATOR')}2{_t('ITERATION_BEGIN_SUFFIX')}\n"
        f"  {_var('i')}\n"
        f"{_t('ITERATION_END')}\n",
    ),
    Section(
        "Conditions",
        "{?( expression )?} ... @else@ ... {/?}, and the conditional parts ?$show ... $show?",
        (
            ("DIV_TAG_CONDITIONS_BEGIN_PREFIX", "Condition prefix"),
            ("DIV_TAG_CONDITIONS_BEGIN_SUFFIX", "Condition suffix"),
            ("DIV_TAG_CONDITIONS_END", "Condition end"),
            ("DIV_TAG_ELSE", "Else"),
            ("DIV_TAG_CONDITIONAL_TRUE_BEGIN_PREFIX", "True begin prefix"),
            ("DIV_TAG_CONDITIONAL_TRUE_BEGIN_SUFFIX", "True begin suffix"),
            ("DIV_TAG_CONDITIONAL_TRUE_END_PREFIX", "True end prefix"),
            ("DIV_TAG_CONDITIONAL_TRUE_END_SUFFIX", "True end suffix"),
            ("DIV_TAG_CONDITIONAL_FALSE_BEGIN_PREFIX", "False begin prefix"),
            ("DIV_TAG_CONDITIONAL_FALSE_BEGIN_SUFFIX", "False begin suffix"),
            ("DIV_TAG_CONDITIONAL_FALSE_END_PREFIX", "False end prefix"),
            ("DIV_TAG_CONDITIONAL_FALSE_END_SUFFIX", "False end suffix"),
        ),
        f"{_t('CONDITIONS_BEGIN_PREFIX')} {_var('number')} > 5 {_t('CONDITIONS_BEGIN_SUFFIX')}\n"
        "  The number is bigger than five\n"
        f"{_t('ELSE')}\n"
        "  The number is not bigger than five\n"
        f"{_t('CONDITIONS_END')}\n"
        f"{_t('CONDITIONAL_TRUE_BEGIN_PREFIX')}show{_t('CONDITIONAL_TRUE_BEGIN_SUFFIX')}\n"
        "  Show something...\n"
        f"{_t('ELSE')}\n"
        "  Show another something...\n"
        f"{_t('CONDITIONAL_TRUE_END_PREFIX')}show{_t('CONDITIONAL_TRUE_END_SUFFIX')}\n"
        f"{_t('CONDITIONAL_FALSE_BEGIN_PREFIX')}show{_t('CONDITIONAL_FALSE_BEGIN_SUFFIX')}\n"
        "  Show another something...\n"
        f"{_t('CONDITIONAL_FALSE_END_PREFIX')}show{_t('CONDITIONAL_FALSE_END_SUFFIX')}\n",
    ),
    Section(
        "Includes and locations",
        "{% header %}, {%% footer %%}, and locations (( name )) filled by {{name ... name}}",
        (
            ("DIV_TAG_INCLUDE_BEGIN", "Include begin"),
            ("DIV_TAG_INCLUDE_END", "Include end"),
            ("DIV_TAG_PREPROCESSED_BEGIN", "Pre-processed begin"),
            ("DIV_TAG_PREPROCESSED_SEPARATOR", "Pre-processed data"),
            ("DIV_TAG_PREPROCESSED_END", "Pre-processed end"),
            ("DIV_TAG_LOCATION_BEGIN", "Location begin"),
            ("DIV_TAG_LOCATION_END", "Location end"),
            ("DIV_TAG_LOCATION_CONTENT_BEGIN_PREFIX", "Content begin prefix"),
            ("DIV_TAG_LOCATION_CONTENT_BEGIN_SUFFIX", "Content begin suffix"),
            ("DIV_TAG_LOCATION_CONTENT_END_PREFIX", "Content end prefix"),
            ("DIV_TAG_LOCATION_CONTENT_END_SUFFIX", "Content end suffix"),
        ),
        f"{_t('INCLUDE_BEGIN')}header{_t('INCLUDE_END')}\n"
        f"{_t('PREPROCESSED_BEGIN')}footer{_t('PREPROCESSED_SEPARATOR')}footer.json{_t('PREPROCESSED_END')}\n"
        f"{_t('LOCATION_BEGIN')}header_left{_t('LOCATION_END')}\n"
        f"{_t('LOCATION_CONTENT_BEGIN_PREFIX')}header_left{_t('LOCATION_CONTENT_BEGIN_SUFFIX')}\n"
        '  <img src="logo.png">\n'
        f"{_t('LOCATION_CONTENT_END_PREFIX')}header_left{_t('LOCATION_CONTENT_END_SUFFIX')}\n",
    ),
    Section(
        "Formats and formulas",
        "Dates {/div.now:Y-m-d/}, numbers {#price:2.#} and formulas (# 1 + 2 #)",
        (
            ("DIV_TAG_DATE_FORMAT_PREFIX", "Date prefix"),
            ("DIV_TAG_DATE_FORMAT_SEPARATOR", "Date separator"),
            ("DIV_TAG_DATE_FORMAT_SUFFIX", "Date suffix"),
            ("DIV_TAG_NUMBER_FORMAT_PREFIX", "Number prefix"),
            ("DIV_TAG_NUMBER_FORMAT_SEPARATOR", "Number separator"),
            ("DIV_TAG_NUMBER_FORMAT_SUFFIX", "Number suffix"),
            ("DIV_TAG_FORMULA_BEGIN", "Formula begin"),
            ("DIV_TAG_FORMULA_FORMAT_SEPARATOR", "Formula format"),
            ("DIV_TAG_FORMULA_END", "Formula end"),
        ),
        f"Date: {_t('DATE_FORMAT_PREFIX')}div{_t('VAR_MEMBER_DELIMITER')}now{_t('DATE_FORMAT_SEPARATOR')}Y-m-d{_t('DATE_FORMAT_SUFFIX')}\n"
        f"Number: {_t('NUMBER_FORMAT_PREFIX')}price{_t('NUMBER_FORMAT_SEPARATOR')}2.,{_t('NUMBER_FORMAT_SUFFIX')}\n"
        f"Formula: {_t('FORMULA_BEGIN')} 1 + 2 + 3 {_t('FORMULA_FORMAT_SEPARATOR')} 2,. {_t('FORMULA_END')}\n",
    ),
    Section(
        "Aggregate functions",
        "count, max, min, sum and avg over a list: {$sum:products-price}",
        (
            ("DIV_TAG_AGGREGATE_FUNCTION_COUNT", "Count"),
            ("DIV_TAG_AGGREGATE_FUNCTION_MAX", "Maximum"),
            ("DIV_TAG_AGGREGATE_FUNCTION_MIN", "Minimum"),
            ("DIV_TAG_AGGREGATE_FUNCTION_SUM", "Sum"),
            ("DIV_TAG_AGGREGATE_FUNCTION_AVG", "Average"),
            ("DIV_TAG_AGGREGATE_FUNCTION_SEPARATOR", "Function separator"),
            ("DIV_TAG_AGGREGATE_FUNCTION_PROPERTY_SEPARATOR", "Property separator"),
        ),
        "".join(
            f"{label}: {R}{_t('AGGREGATE_FUNCTION_' + fn)}{_t('AGGREGATE_FUNCTION_SEPARATOR')}products"
            f"{_t('AGGREGATE_FUNCTION_PROPERTY_SEPARATOR')}price{S}\n"
            for label, fn in (("Count", "COUNT"), ("Maximum", "MAX"), ("Minimum", "MIN"), ("Sum", "SUM"), ("Average", "AVG"))
        ),
    ),
    Section(
        "Blocks",
        "Ignored code, comments, strip, HTML to text, friendly tags and macros",
        (
            ("DIV_TAG_IGNORE_BEGIN", "Ignore begin"),
            ("DIV_TAG_IGNORE_END", "Ignore end"),
            ("DIV_TAG_COMMENT_BEGIN", "Comment begin"),
            ("DIV_TAG_COMMENT_END", "Comment end"),
            ("DIV_TAG_STRIP_BEGIN", "Strip begin"),
            ("DIV_TAG_STRIP_END", "Strip end"),
            ("DIV_TAG_TXT_BEGIN", "HTML to text begin"),
            ("DIV_TAG_TXT_WIDTH_SEPARATOR", "HTML to text width"),
            ("DIV_TAG_TXT_END", "HTML to text end"),
            ("DIV_TAG_FRIENDLY_BEGIN", "Friendly tag begin"),
            ("DIV_TAG_FRIENDLY_END", "Friendly tag end"),
            ("DIV_TAG_MACRO_BEGIN", "Macro begin"),
            ("DIV_TAG_MACRO_END", "Macro end"),
        ),
        f"{_t('IGNORE_BEGIN')} ... ignored code ... {_t('IGNORE_END')}\n"
        f"{_t('COMMENT_BEGIN')} A comment {_t('COMMENT_END')}\n"
        f"{_t('STRIP_BEGIN')}\n"
        "  ... some ugly code here ...\n"
        f"{_t('STRIP_END')}\n"
        f"{_t('TXT_BEGIN')} 150 {_t('TXT_WIDTH_SEPARATOR')}\n"
        "  <p>Hello World</p>\n"
        f"{_t('TXT_END')}\n"
        f"{_t('FRIENDLY_BEGIN')} {_var('name')} {_t('FRIENDLY_END')}\n"
        f"{_t('MACRO_BEGIN')}\n"
        "  $a = 5;\n"
        f"{_t('MACRO_END')}\n",
    ),
    Section(
        "Capsules and sub-parsers",
        "Capsules [[entity ... entity]], multiple replacements {:all} ... {:/all}, sub-parsers {p} ... {/p}",
        (
            ("DIV_TAG_CAPSULE_BEGIN_PREFIX", "Capsule begin prefix"),
            ("DIV_TAG_CAPSULE_BEGIN_SUFFIX", "Capsule begin suffix"),
            ("DIV_TAG_CAPSULE_END_PREFIX", "Capsule end prefix"),
            ("DIV_TAG_CAPSULE_END_SUFFIX", "Capsule end suffix"),
            ("DIV_TAG_MULTI_REPLACEMENT_BEGIN_PREFIX", "Multi-repl. begin prefix"),
            ("DIV_TAG_MULTI_REPLACEMENT_BEGIN_SUFFIX", "Multi-repl. begin suffix"),
            ("DIV_TAG_MULTI_REPLACEMENT_END_PREFIX", "Multi-repl. end prefix"),
            ("DIV_TAG_MULTI_REPLACEMENT_END_SUFFIX", "Multi-repl. end suffix"),
            ("DIV_TAG_SUBPARSER_BEGIN_PREFIX", "Sub-parser begin prefix"),
            ("DIV_TAG_SUBPARSER_BEGIN_SUFFIX", "Sub-parser begin suffix"),
            ("DIV_TAG_SUBPARSER_END_PREFIX", "Sub-parser end prefix"),
            ("DIV_TAG_SUBPARSER_END_SUFFIX", "Sub-parser end suffix"),
        ),
        f"{_t('CAPSULE_BEGIN_PREFIX')}entity{_t('CAPSULE_BEGIN_SUFFIX')}\n"
        "  ... some code here ...\n"
        f"{_t('CAPSULE_END_PREFIX')}entity{_t('CAPSULE_END_SUFFIX')}\n"
        f"{_t('MULTI_REPLACEMENT_BEGIN_PREFIX')}replaceall{_t('MULTI_REPLACEMENT_BEGIN_SUFFIX')}\n"
        "  ... some code to replace their parts ...\n"
        f"{_t('MULTI_REPLACEMENT_END_PREFIX')}replaceall{_t('MULTI_REPLACEMENT_END_SUFFIX')}\n"
        f"{_t('SUBPARSER_BEGIN_PREFIX')}myparser{_t('SUBPARSER_BEGIN_SUFFIX')}\n"
        "  ... some code here ...\n"
        f"{_t('SUBPARSER_END_PREFIX')}myparser{_t('SUBPARSER_END_SUFFIX')}\n",
    ),
    Section(
        "Special characters",
        "Escapes for characters that are hard to write, and the teaser break",
        (
            ("DIV_TAG_SPECIAL_REPLACE_NEW_LINE", "New line"),
            ("DIV_TAG_SPECIAL_REPLACE_CAR_RETURN", "Carriage return"),
            ("DIV_TAG_SPECIAL_REPLACE_HORIZONTAL_TAB", "Horizontal tab"),
            ("DIV_TAG_SPECIAL_REPLACE_VERTICAL_TAB", "Vertical tab"),
            ("DIV_TAG_SPECIAL_REPLACE_NEXT_PAGE", "Next page"),
            ("DIV_TAG_SPECIAL_REPLACE_DOLLAR_SYMBOL", "Dollar symbol"),
            ("DIV_TAG_SPECIAL_REPLACE_SPACE", "Space"),
            ("DIV_TAG_TEASER_BREAK", "Teaser break"),
        ),
        f"Hello{_t('SPECIAL_REPLACE_NEW_LINE')}World{_t('SPECIAL_REPLACE_HORIZONTAL_TAB')}!\n"
        f"Return {_t('SPECIAL_REPLACE_CAR_RETURN')} vtab {_t('SPECIAL_REPLACE_VERTICAL_TAB')} page {_t('SPECIAL_REPLACE_NEXT_PAGE')}\n"
        f"Price: {_t('SPECIAL_REPLACE_DOLLAR_SYMBOL')}20{_t('SPECIAL_REPLACE_SPACE')}USD\n"
        f"<p>Lorem ipsum dolor sit amet, {_t('TEASER_BREAK')} Excepteur sint ...</p>\n",
    ),
)

ALL_KEYS: list[str] = [k for s in SECTIONS for k in s.keys]
LABELS: dict[str, str] = {k: label for s in SECTIONS for k, label in s.fields}


def section_of(key: str) -> Section | None:
    return next((s for s in SECTIONS if key in s.keys), None)


# --------------------------------------------------------------- filling
@dataclass
class Filled:
    """An example written with a dialect, and where each tag landed."""

    text: str
    spans: dict[str, list[tuple[int, int]]] = field(default_factory=dict)  # key -> [(start, end)]
    sections: dict[str, tuple[int, int]] = field(default_factory=dict)  # title -> (start, end)


def fill(template: str, tags: dict[str, str], offset: int = 0, into: Filled | None = None) -> Filled:
    out = into or Filled("")
    parts: list[str] = []
    pos = offset + len(out.text)
    last = 0
    for m in PLACEHOLDER.finditer(template):
        literal = template[last : m.start()]
        parts.append(literal)
        pos += len(literal)
        value = tags.get(m.group(1), DEFAULT_TAGS.get(m.group(1), ""))
        parts.append(value)
        out.spans.setdefault(m.group(1), []).append((pos, pos + len(value)))
        pos += len(value)
        last = m.end()
    parts.append(template[last:])
    out.text += "".join(parts)
    return out


def example(tags: dict[str, str], sections: tuple[Section, ...] = SECTIONS, *, headings: bool = True) -> Filled:
    """The examples of ``sections`` written with ``tags`` (a full tag set or overrides)."""
    full = {**DEFAULT_TAGS, **tags}
    out = Filled("")
    for section in sections:
        start = len(out.text)
        if headings:
            out.text += f"{section.title}\n{'-' * len(section.title)}\n"
        fill(section.example, full, into=out)
        out.sections[section.title] = (start, len(out.text))
        out.text += "\n"
    return out


# ------------------------------------------------------------- the dialect
def overrides(tags: dict[str, str]) -> dict[str, str]:
    """Only what differs from Div's default dialect, in Div's order."""
    return {k: tags[k] for k in DEFAULT_TAGS if k in tags and tags[k] != DEFAULT_TAGS[k]}


def changed_in(section: Section, tags: dict[str, str]) -> int:
    return sum(1 for k in section.keys if tags.get(k, DEFAULT_TAGS[k]) != DEFAULT_TAGS[k])


def dialect_json(tags: dict[str, str]) -> str:
    """The dialect file: a JSON object with the tags that differ from Div's defaults."""
    data = overrides(tags)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n" if data else "{}\n"


def php_code(tags: dict[str, str], name: str = "") -> str:
    """The same dialect as PHP constants, to be included before div.php."""
    data = overrides(tags)
    lines = [
        "<?php",
        "",
        f"/* Div dialect{' ' + name if name else ''}, written with divide's dialector on {date.today().isoformat()} */",
        "/* Include this file before div.php (the constants must exist before Div defines its defaults). */",
        "",
    ]
    if not data:
        lines.append("// Nothing to define: every tag is Div's default.")
    for key, value in data.items():
        lines.append(f"define('{key}', {_php_string(value)});")
    lines.append("")
    return "\n".join(lines)


def _php_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def transform(tags: dict[str, str], find: str, replace: str, keys: list[str] | None = None) -> dict[str, str]:
    """Replace ``find`` with ``replace`` in every tag (or in ``keys``): the tags that change."""
    if not find:
        return {}
    out = {}
    for key in keys or ALL_KEYS:
        value = tags.get(key, DEFAULT_TAGS[key])
        if find in value:
            out[key] = value.replace(find, replace)
    return out


# ------------------------------------------------------- Div's reading back
@dataclass(frozen=True)
class Difference:
    """A section of the example that Div read back otherwise."""

    section: str
    line: int  # 1-based, within the section's example
    wrote: str  # the line in the dialect
    expected: str  # the line in Div's default dialect
    read: str  # what Div made of it


def _heading(section: Section) -> str:
    return f"{section.title}\n{'-' * len(section.title)}\n"


def _split(text: str) -> dict[str, str]:
    """The example's sections by title (headings are plain text in every dialect)."""
    out: dict[str, str] = {}
    marks = [(text.find(_heading(s)), s) for s in SECTIONS]
    marks = sorted((pos, s) for pos, s in marks if pos >= 0)
    for i, (pos, section) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out[section.title] = text[pos + len(_heading(section)) : end]
    return out


def differences(tags: dict[str, str], translated: str) -> list[Difference]:
    """Compare Div's reading of the example written in ``tags`` with the default example."""
    wrote = _split(example(overrides(tags)).text)
    want = _split(example({}).text)
    got = _split(translated)
    out = []
    for section in SECTIONS:
        w, g, s = want.get(section.title, ""), got.get(section.title), wrote.get(section.title, "")
        if g == w:
            continue
        g = g or ""
        wl, gl, sl = w.splitlines(), g.splitlines(), s.splitlines()
        n = next((i for i in range(max(len(wl), len(gl))) if (wl[i:i + 1] or [""]) != (gl[i:i + 1] or [""])), 0)
        pick = lambda lines: lines[n] if n < len(lines) else ""  # noqa: E731
        out.append(Difference(section.title, n + 1, pick(sl), pick(wl), pick(gl)))
    return out
