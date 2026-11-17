"""The languages divide edits, by file extension.

Each language says what it is called, which files are its own, which help
topic explains its editor, and whether divide checks it (its errors go to
the Messages window). The editor and the app ask here instead of testing
extensions themselves, so a new language is one more entry.

Div templates, Div JSON, INI and CSV are coloured by divide's own lexers; PHP
and the other files of a PHP project (HTML, CSS, JavaScript, Markdown, SQL,
XML, YAML, TOML, shell scripts) by tree-sitter grammars (divide.lang.php,
divide.lang.treesitter).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Language:
    name: str  # the editor's ``lang``
    title: str  # for people: the status line, the Messages window
    extensions: frozenset[str]
    help_topic: str  # the help topic of its editor (F1)
    checked: bool = False  # its errors are listed in the Messages window
    names: frozenset[str] = frozenset()  # whole file names (.env) or endings (.xml.dist) it owns
    treesitter: bool = False  # coloured by a tree-sitter grammar (divide.lang.treesitter)


DIV = Language("div", "Div", frozenset({".tpl", ".div"}), "Editing-Templates", checked=True)
JSON = Language("json", "JSON", frozenset({".json", ".dialect"}), "Data-Files")
PHP = Language("php", "PHP", frozenset({".php", ".phtml"}), "Editing-PHP", checked=True)

OTHER = "Other-Files"  # the help topic of the files divide only colours

HTML = Language("html", "HTML", frozenset({".html", ".htm"}), OTHER, treesitter=True)
CSS = Language("css", "CSS", frozenset({".css"}), OTHER, treesitter=True)
JAVASCRIPT = Language("javascript", "JavaScript", frozenset({".js", ".mjs", ".cjs", ".jsx"}), OTHER, treesitter=True)
MARKDOWN = Language("markdown", "Markdown", frozenset({".md", ".markdown"}), OTHER, treesitter=True)
SQL = Language("sql", "SQL", frozenset({".sql"}), OTHER, treesitter=True)
XML = Language("xml", "XML", frozenset({".xml", ".xsd", ".xsl", ".xslt", ".svg", ".xhtml", ".xliff", ".xlf"}), OTHER,
               names=frozenset({".xml.dist"}), treesitter=True)  # phpunit.xml.dist, phpcs.xml.dist
YAML = Language("yaml", "YAML", frozenset({".yml", ".yaml", ".neon"}), OTHER,
                names=frozenset({".yml.dist", ".yaml.dist"}), treesitter=True)
TOML = Language("toml", "TOML", frozenset({".toml"}), OTHER, treesitter=True)
SHELL = Language("shell", "Shell", frozenset({".sh", ".bash"}), OTHER,
                 names=frozenset({".env", ".bashrc", ".profile"}), treesitter=True)  # .env: KEY=value lines
INI = Language("ini", "INI", frozenset({".ini", ".cfg", ".conf"}), OTHER, names=frozenset({".editorconfig", ".ini.dist"}))
CSV = Language("csv", "CSV", frozenset({".csv", ".tsv"}), OTHER)

LANGUAGES: tuple[Language, ...] = (DIV, JSON, PHP, HTML, CSS, JAVASCRIPT, MARKDOWN, SQL, XML, YAML, TOML, SHELL, INI, CSV)


# the project's own extensions (its Div setup: DIV_DEFAULT_TPL_FILE_EXT, DIV_DEFAULT_DATA_FILE_EXT)
_project: dict[str, str] = {}


def set_project_extensions(template: str | None = None, data: str | None = None) -> None:
    """Files with the project's template extension are Div templates (before HTML,
    say: ``.html`` templates), and those with its data extension Div JSON."""
    _project.clear()
    if data:
        _project[data.lower()] = JSON.name
    if template:
        _project[template.lower()] = DIV.name


def template_extensions() -> frozenset[str]:
    """Div's (``.tpl``, ``.div``) and the project's."""
    return DIV.extensions | {ext for ext, name in _project.items() if name == DIV.name}


def language(name: str | None) -> Language | None:
    return next((lang for lang in LANGUAGES if lang.name == name), None)


def language_of(path: Path | None) -> str | None:
    """The language of a file: Div for templates (and untitled buffers), None for plain text."""
    if path is None:
        return DIV.name
    if path.suffix.lower() in _project:
        return _project[path.suffix.lower()]
    name = path.name.lower()
    for lang in LANGUAGES:  # whole names and endings first: phpunit.xml.dist, .env, .env.local
        if any(name == n or name.endswith(n) or (n == ".env" and name.startswith(".env.")) for n in lang.names):
            return lang.name
    suffix = path.suffix.lower()
    return next((lang.name for lang in LANGUAGES if suffix in lang.extensions), None)
