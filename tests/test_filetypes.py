"""The other files of a PHP project, coloured: tree-sitter (HTML, CSS, JavaScript,
Markdown, SQL, XML, YAML, TOML, shell) and divide's lexers (INI, CSV)."""

from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from divide import themes
from divide.editor.div_editor import DivEditor
from divide.lang import language, language_of, plain, treesitter

SAMPLES = {
    "page.html": '<!DOCTYPE html>\n<html lang="en"><body class="x"><!-- note --><p>Hi &amp; bye</p></body></html>\n',
    "app.css": "/* theme */\nbody { color: #fff; margin: 0 auto; }\n@media screen { a:hover { color: red; } }\n",
    "app.js": "// entry\nimport x from './x.js';\nconst n = 42;\nfunction hi(name) { return `hi ${name}`; }\n",
    "README.md": "# Title\n\nSome *text* and a [link](https://example.com).\n\n- item\n\n```php\necho 1;\n```\n",
    "schema.sql": "-- users\nCREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(40) NOT NULL);\nSELECT * FROM users WHERE id = 1;\n",
    "phpunit.xml.dist": '<?xml version="1.0"?>\n<!-- tests -->\n<phpunit colors="true"><testsuites><testsuite name="unit"/></testsuites></phpunit>\n',
    "services.yaml": "# services\nservices:\n  app.mailer:\n    class: App\\Mailer\n    arguments: ['%mailer.from%', 25, true]\n",
    "pyproject.toml": '# build\n[project]\nname = "x"\nversion = "1.0"\nok = true\n',
    "deploy.sh": '#!/bin/sh\n# deploy\nfor f in *.php; do echo "$f"; done\nexport APP_ENV=prod\n',
    ".env": "# local\nAPP_ENV=dev\nDB_URL=\"mysql://root@localhost/app\"\n",
    "php.ini": "; PHP\n[PHP]\nmemory_limit = 128M\ndisplay_errors = On\nerror_log = \"/tmp/php.log\" ; here\n",
    "data.csv": 'id,name,price\n1,"Potato, red",1.50\n2,Tomato,2.25\n',
}
LANGS = {"page.html": "html", "app.css": "css", "app.js": "javascript", "README.md": "markdown",
         "schema.sql": "sql", "phpunit.xml.dist": "xml", "services.yaml": "yaml", "pyproject.toml": "toml",
         "deploy.sh": "shell", ".env": "shell", "php.ini": "ini", "data.csv": "csv"}


def test_languages_of_files():
    for name, lang in LANGS.items():
        assert language_of(Path(name)) == lang, name
    assert language_of(Path(".env.local")) == "shell" and language_of(Path("phpcs.xml.dist")) == "xml"
    assert language_of(Path("notes.txt")) is None and language_of(Path("composer.json")) == "json"
    assert language("yaml").title == "YAML" and language("csv").treesitter is False


@pytest.mark.parametrize("lang", sorted(treesitter.GRAMMARS))
def test_grammars_load(lang):
    found = treesitter.grammar(lang)
    assert found is not None, f"tree-sitter-{treesitter.GRAMMARS[lang][0]} is not installed"
    _language, query = found
    assert "@ts." in query and "@string" not in query.replace("@ts.", "")


def test_every_capture_has_a_colour():
    """The captures of the queries are styled by the palettes (none left plain by mistake)."""
    import re

    plain_ones = {"ts.text", "ts.none", "ts.spell", "ts._attr", "ts.error"}
    for lang in treesitter.GRAMMARS:
        _language, query = treesitter.grammar(lang)
        for capture in set(re.findall(r"@(ts\.[\w.\-]+)", query)):
            assert capture in themes.TOKENS or capture in plain_ones or capture.startswith("ts._"), (lang, capture)


def test_ini_tokens():
    text = SAMPLES["php.ini"]
    kinds = {text[t.start:t.end]: t.kind for t in plain.ini_tokens(text)}
    assert kinds["; PHP"] == "ini.comment" and kinds["[PHP]"] == "ini.section"
    assert kinds["memory_limit"] == "ini.key" and kinds["128M"] == "ini.number" and kinds["On"] == "ini.constant"
    assert kinds['"/tmp/php.log"'] == "ini.string" and kinds["; here"] == "ini.comment"


def test_csv_tokens():
    text = SAMPLES["data.csv"]
    cells = [(text[t.start:t.end], t.kind) for t in plain.csv_tokens(text) if t.kind != "csv.sep"]
    assert cells[:3] == [("id", "csv.col0"), ("name", "csv.col1"), ("price", "csv.col2")]
    assert ('"Potato, red"', "csv.col1") in cells  # the separator inside quotes is the field's
    assert plain.csv_separator("a;b;c\n1;2;3") == ";" and plain.csv_separator("a\tb", tsv=True) == "\t"
    many = plain.csv_tokens(",".join("abcdefgh"))
    assert [t.kind for t in many if t.kind != "csv.sep"][6] == "csv.col0"  # six colours, then again


class EditorApp(App):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def compose(self) -> ComposeResult:
        yield DivEditor(self.path.read_text(), path=self.path)


@pytest.mark.parametrize("name", sorted(SAMPLES))
async def test_files_are_coloured(name, tmp_path):
    path = tmp_path / name
    path.write_text(SAMPLES[name])
    app = EditorApp(path)
    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.pause()
        editor = app.query_one(DivEditor)
        assert editor.lang == LANGS[name]
        names = {h[2] for row in editor._highlights.values() for h in row}
        prefix = {"ini": "ini.", "csv": "csv."}.get(editor.lang, "ts.")
        coloured = {n for n in names if n.startswith(prefix)}
        assert coloured and all(n in themes.TOKENS for n in coloured if not n.startswith(("ts.text", "ts.none", "ts.spell"))), names
        assert any(n in themes.TOKENS for n in names)  # at least one coloured by the palette


def test_queries_are_made_once_and_kept():
    """Freeing a JavaScript query corrupts memory (tree-sitter 0.26): every editor shares one, never freed."""
    from textual.document._syntax_aware_document import SyntaxAwareDocument

    language, source = treesitter.grammar("javascript")
    first = SyntaxAwareDocument("let a = 1;\n", language).prepare_query(source)
    again = SyntaxAwareDocument("let b = 2;\n", language).prepare_query(source)
    assert first is again is treesitter.query(language, source)

