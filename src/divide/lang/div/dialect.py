"""Div dialects.

A dialect is a set of ``DIV_TAG_*`` overrides. The defaults below mirror the
``define()`` calls at the top of ``src/div.php`` (divengine/div 6.x); the PHP
source is the reference, not the wiki, when both disagree (e.g. the include
tag is ``'{% '`` with a trailing space).

Templates select a dialect with the template property ``@_DIALECT = file``.
Dialect files are JSON objects, written leniently (single quotes, unquoted
keys and trailing commas are accepted, as ``div::jsonDecode`` does).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TAGS: dict[str, str] = {
    "DIV_TAG_VAR_MEMBER_DELIMITER": ".",
    "DIV_TAG_REPLACEMENT_PREFIX": "{",
    "DIV_TAG_REPLACEMENT_SUFFIX": "}",
    "DIV_TAG_MULTI_MODIFIERS_PREFIX": "{$",
    "DIV_TAG_MULTI_MODIFIERS_OPERATOR": "|",
    "DIV_TAG_MULTI_MODIFIERS_SEPARATOR": "|",
    "DIV_TAG_MULTI_MODIFIERS_SUFFIX": "|}",
    "DIV_TAG_SUBMATCH_SEPARATOR": ":",
    "DIV_TAG_MODIFIER_SIMPLE": "$",
    "DIV_TAG_MODIFIER_CAPITALIZE_FIRST": "^",
    "DIV_TAG_MODIFIER_CAPITALIZE_WORDS": "^^",
    "DIV_TAG_MODIFIER_UPPERCASE": "^^^",
    "DIV_TAG_MODIFIER_LOWERCASE": "_",
    "DIV_TAG_MODIFIER_LENGTH": "%",
    "DIV_TAG_MODIFIER_COUNT_WORDS": "%%",
    "DIV_TAG_MODIFIER_COUNT_SENTENCES": "%%%",
    "DIV_TAG_MODIFIER_COUNT_PARAGRAPHS": "%%%%",
    "DIV_TAG_MODIFIER_ENCODE_URL": "&",
    "DIV_TAG_MODIFIER_ENCODE_RAW_URL": "&&",
    "DIV_TAG_MODIFIER_ENCODE_JSON": "json:",
    "DIV_TAG_MODIFIER_HTML_ENTITIES": "html:",
    "DIV_TAG_MODIFIER_NL2BR": "br:",
    "DIV_TAG_MODIFIER_TRUNCATE": "~",
    "DIV_TAG_MODIFIER_WORDWRAP": "/",
    "DIV_TAG_MODIFIER_SUBSTRING_SEPARATOR": ",",
    "DIV_TAG_MODIFIER_SINGLE_QUOTES": "'",
    "DIV_TAG_MODIFIER_JS": "js:",
    "DIV_TAG_MODIFIER_FORMAT": "",
    "DIV_TAG_DATE_FORMAT_PREFIX": "{/",
    "DIV_TAG_DATE_FORMAT_SUFFIX": "/}",
    "DIV_TAG_DATE_FORMAT_SEPARATOR": ":",
    "DIV_TAG_NUMBER_FORMAT_PREFIX": "{#",
    "DIV_TAG_NUMBER_FORMAT_SUFFIX": "#}",
    "DIV_TAG_NUMBER_FORMAT_SEPARATOR": ":",
    "DIV_TAG_FORMULA_BEGIN": "(#",
    "DIV_TAG_FORMULA_END": "#)",
    "DIV_TAG_FORMULA_FORMAT_SEPARATOR": ":",
    "DIV_TAG_SUBPARSER_BEGIN_PREFIX": "{",
    "DIV_TAG_SUBPARSER_BEGIN_SUFFIX": "}",
    "DIV_TAG_SUBPARSER_END_PREFIX": "{/",
    "DIV_TAG_SUBPARSER_END_SUFFIX": "}",
    "DIV_TAG_IGNORE_BEGIN": "{ignore}",
    "DIV_TAG_IGNORE_END": "{/ignore}",
    "DIV_TAG_COMMENT_BEGIN": "<!--{",
    "DIV_TAG_COMMENT_END": "}-->",
    "DIV_TAG_TXT_BEGIN": "{txt}",
    "DIV_TAG_TXT_END": "{/txt}",
    "DIV_TAG_TXT_WIDTH_SEPARATOR": "=>",
    "DIV_TAG_STRIP_BEGIN": "{strip}",
    "DIV_TAG_STRIP_END": "{/strip}",
    "DIV_TAG_LOOP_BEGIN_PREFIX": "[$",
    "DIV_TAG_LOOP_BEGIN_SUFFIX": "]",
    "DIV_TAG_LOOP_END_PREFIX": "[/$",
    "DIV_TAG_LOOP_END_SUFFIX": "]",
    "DIV_TAG_EMPTY": "@empty@",
    "DIV_TAG_BREAK": "@break@",
    "DIV_TAG_LOOP_VAR_SEPARATOR": "=>",
    "DIV_TAG_ITERATION_BEGIN_PREFIX": "[:",
    "DIV_TAG_ITERATION_BEGIN_SUFFIX": ":]",
    "DIV_TAG_ITERATION_END": "[/]",
    "DIV_TAG_ITERATION_PARAM_SEPARATOR": ",",
    "DIV_TAG_CONDITIONAL_TRUE_BEGIN_PREFIX": "?$",
    "DIV_TAG_CONDITIONAL_TRUE_BEGIN_SUFFIX": "",
    "DIV_TAG_CONDITIONAL_TRUE_END_PREFIX": "$",
    "DIV_TAG_CONDITIONAL_TRUE_END_SUFFIX": "?",
    "DIV_TAG_CONDITIONAL_FALSE_BEGIN_PREFIX": "!$",
    "DIV_TAG_CONDITIONAL_FALSE_BEGIN_SUFFIX": "",
    "DIV_TAG_CONDITIONAL_FALSE_END_PREFIX": "$",
    "DIV_TAG_CONDITIONAL_FALSE_END_SUFFIX": "!",
    "DIV_TAG_ELSE": "@else@",
    "DIV_TAG_CONDITIONS_BEGIN_PREFIX": "{?(",
    "DIV_TAG_CONDITIONS_BEGIN_SUFFIX": ")?}",
    "DIV_TAG_CONDITIONS_END": "{/?}",
    "DIV_TAG_TPLVAR_BEGIN": "{=",
    "DIV_TAG_TPLVAR_END": "=}",
    "DIV_TAG_TPLVAR_ASSIGN_OPERATOR": ":",
    "DIV_TAG_TPLVAR_PROTECTOR": "*",
    "DIV_TAG_DEFAULT_REPLACEMENT_BEGIN": "{@",
    "DIV_TAG_DEFAULT_REPLACEMENT_END": "@}",
    "DIV_TAG_INCLUDE_BEGIN": "{% ",
    "DIV_TAG_INCLUDE_END": " %}",
    "DIV_TAG_PREPROCESSED_BEGIN": "{%% ",
    "DIV_TAG_PREPROCESSED_END": " %%}",
    "DIV_TAG_PREPROCESSED_SEPARATOR": ":",
    "DIV_TAG_CAPSULE_BEGIN_PREFIX": "[[",
    "DIV_TAG_CAPSULE_BEGIN_SUFFIX": "",
    "DIV_TAG_CAPSULE_END_PREFIX": "",
    "DIV_TAG_CAPSULE_END_SUFFIX": "]]",
    "DIV_TAG_MULTI_REPLACEMENT_BEGIN_PREFIX": "{:",
    "DIV_TAG_MULTI_REPLACEMENT_BEGIN_SUFFIX": "}",
    "DIV_TAG_MULTI_REPLACEMENT_END_PREFIX": "{:/",
    "DIV_TAG_MULTI_REPLACEMENT_END_SUFFIX": "}",
    "DIV_TAG_FRIENDLY_BEGIN": "<!--|",
    "DIV_TAG_FRIENDLY_END": "|-->",
    "DIV_TAG_AGGREGATE_FUNCTION_COUNT": "count",
    "DIV_TAG_AGGREGATE_FUNCTION_MAX": "max",
    "DIV_TAG_AGGREGATE_FUNCTION_MIN": "min",
    "DIV_TAG_AGGREGATE_FUNCTION_SUM": "sum",
    "DIV_TAG_AGGREGATE_FUNCTION_AVG": "avg",
    "DIV_TAG_AGGREGATE_FUNCTION_SEPARATOR": ":",
    "DIV_TAG_AGGREGATE_FUNCTION_PROPERTY_SEPARATOR": "-",
    "DIV_TAG_LOCATION_BEGIN": "(( ",
    "DIV_TAG_LOCATION_END": " ))",
    "DIV_TAG_LOCATION_CONTENT_BEGIN_PREFIX": "{{",
    "DIV_TAG_LOCATION_CONTENT_BEGIN_SUFFIX": "",
    "DIV_TAG_LOCATION_CONTENT_END_PREFIX": "",
    "DIV_TAG_LOCATION_CONTENT_END_SUFFIX": "}}",
    "DIV_TAG_MACRO_BEGIN": "<?",
    "DIV_TAG_MACRO_END": "?>",
    "DIV_TAG_SPECIAL_REPLACE_NEW_LINE": "{\\n}",
    "DIV_TAG_SPECIAL_REPLACE_CAR_RETURN": "{\\r}",
    "DIV_TAG_SPECIAL_REPLACE_HORIZONTAL_TAB": "{\\t}",
    "DIV_TAG_SPECIAL_REPLACE_VERTICAL_TAB": "{\\v}",
    "DIV_TAG_SPECIAL_REPLACE_NEXT_PAGE": "{\\f}",
    "DIV_TAG_SPECIAL_REPLACE_DOLLAR_SYMBOL": "{\\$}",
    "DIV_TAG_SPECIAL_REPLACE_SPACE": "{\\s}",
    "DIV_TAG_TEASER_BREAK": "<!--break-->",
}

# Variable names the engine injects into loop/capsule scopes (02.11, 02.44).
SCOPE_VARS = frozenset(
    {
        "value", "_item", "_previous", "_next", "_key", "_index", "_index_random",
        "_order", "_list", "_is_last", "_is_first", "_is_odd", "_is_even",
        "_to_string", "_empty",
    }
)

# System vars (02.31) and engine setup vars, all under the "div." namespace.
SYSTEM_VAR_PREFIX = "div."

_PROPERTY_RE = re.compile(r"^[ \t]*@_([A-Za-z_]\w*)[ \t]*=[ \t]*(.*?)[ \t]*$", re.M)


def lenient_json(text: str):
    """Decode the relaxed JSON that Div accepts in dialect files and tplvars."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = i + 1
            buf = []
            while j < n and text[j] != c:
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j : j + 2])
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            body = "".join(buf)
            if c == "'":
                body = body.replace("\\'", "'").replace('"', '\\"')
            out.append('"' + body + '"')
            i = j + 1
            continue
        m = re.match(r"[A-Za-z_][\w\-]*", text[i:])
        if m and m.group(0) not in ("true", "false", "null"):
            word = m.group(0)
            rest = text[i + len(word) :].lstrip()
            if rest.startswith(":"):
                out.append(json.dumps(word))
                i += len(word)
                continue
        out.append(c)
        i += 1
    cleaned = re.sub(r",\s*([}\]])", r"\1", "".join(out))
    return json.loads(cleaned)


@dataclass
class Dialect:
    name: str = "default"
    tags: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TAGS))
    source: Path | None = None
    error: str | None = None

    def __getitem__(self, key: str) -> str:
        return self.tags.get(key, "")

    @classmethod
    def from_overrides(cls, overrides: dict, name: str = "custom", source: Path | None = None) -> "Dialect":
        tags = dict(DEFAULT_TAGS)
        for k, v in overrides.items():
            if isinstance(k, str) and k.startswith("DIV_TAG_"):
                tags[k] = "" if v is None else str(v)
        return cls(name=name, tags=tags, source=source)

    @classmethod
    def load(cls, path: Path) -> "Dialect":
        data = lenient_json(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path}: a dialect must be a JSON object")
        return cls.from_overrides(data, name=path.stem, source=path)


DEFAULT_DIALECT = Dialect()


def template_properties(text: str) -> dict[str, tuple[str, int]]:
    """Return ``@_NAME = value`` properties as ``{NAME: (value, offset)}``."""
    props: dict[str, tuple[str, int]] = {}
    for m in _PROPERTY_RE.finditer(text):
        key = m.group(1).upper()
        props.setdefault(key, (m.group(2), m.start()))
    return props


def resolve_dialect(text: str, template_path: Path | None = None, roots: list[Path] | None = None) -> Dialect:
    """Pick the dialect for a template from its ``@_DIALECT`` property.

    The engine resolves the path relative to the process cwd; an editor does
    not know it, so we try the template folder, then each project root.
    """
    prop = template_properties(text).get("DIALECT")
    if not prop:
        return DEFAULT_DIALECT
    ref = prop[0].strip().strip("'\"")
    candidates: list[Path] = []
    p = Path(ref)
    if p.is_absolute():
        candidates.append(p)
    else:
        if template_path is not None:
            candidates.append(template_path.parent / p)
        for r in roots or []:
            candidates.append(r / p)
        candidates.append(Path.cwd() / p)
    for c in candidates:
        if c.is_file():
            try:
                return Dialect.load(c)
            except (OSError, ValueError) as exc:
                return Dialect(name=ref, error=str(exc))
    return Dialect(name=ref, error=f"dialect file not found: {ref}")
