"""The help books in the language of the interface, on an example book
(tests/books: "guide" in English, and in Spanish with one page not translated)."""

import importlib.util
import shutil
import sqlite3
from pathlib import Path

import pytest

from divide import i18n, manual
from divide.manual import fulltext

EXAMPLE = Path(__file__).parent / "books"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def library(tmp_path, monkeypatch):
    """The example book as the help's books, its indexes in a folder of their own."""
    root = tmp_path / "manual"
    shutil.copytree(EXAMPLE, root)
    manual.use_root(root)
    monkeypatch.setattr(fulltext, "INDEX_FILE", root / "search.sqlite")
    fulltext._connection.cache_clear()
    yield root
    manual.use_root(manual.HERE)
    fulltext._connection.cache_clear()


def in_language(monkeypatch, lang: str) -> None:
    monkeypatch.setattr(i18n, "current", lang)


def text_of(topic) -> str:
    return "\n".join("".join(s.text for s in line) for line in topic.lines)


def test_registry_and_languages(library):
    english, spanish = manual.registry()
    assert (english.id, english.language, english.folder) == ("guide", "en", "guide")
    assert (spanish.id, spanish.language, spanish.folder) == ("guide", "es", "guide.es")
    assert spanish.home == "Home" and spanish.contents == "_Sidebar.md"  # from the original
    assert spanish.dirs == (library / "books" / "guide.es", library / "books" / "guide")
    assert manual.languages() == ["en", "es"]


def test_english_by_default(library, monkeypatch):
    in_language(monkeypatch, "en")
    assert [b.title for b in manual.books()] == ["Guide"]
    assert manual.title_of("guide:Home") == "The Guide"


def test_the_interface_language_chooses_the_book(library, monkeypatch):
    in_language(monkeypatch, "es")
    (guide,) = manual.books()
    assert guide.title == "Guía" and manual.language() == "es"
    assert manual.title_of("guide:Home") == "La guía"
    # a page not translated yet: the original's
    assert manual.page_names("guide") == ["guide:Getting-Started", "guide:Home", "guide:Other-Files"]
    assert manual.title_of("guide:Other-Files") == "Other Files"
    # the links keep the page names, in every language
    home = manual.layout("guide:Home", 76)
    assert {link.target for link in home.links} == {"guide:Getting-Started", "guide:Other-Files"}
    assert "Primeros pasos" in text_of(home)
    # the contents: the translation's sidebar
    contents = text_of(manual.layout(manual.contents_of("guide"), 76))
    assert "Inicio" in contents and "Otros archivos" in contents


def test_a_language_with_no_books_shows_the_originals(library, monkeypatch):
    in_language(monkeypatch, "fr")
    assert manual.language() == "en" and manual.books()[0].title == "Guide"


def test_search_in_each_language(library, monkeypatch):
    built = fulltext.build_all()
    assert set(built) == {"en", "es"}
    assert (library / "search.sqlite").is_file() and (library / "search.es.sqlite").is_file()
    in_language(monkeypatch, "es")
    assert fulltext.connection().execute("PRAGMA database_list").fetchone()[2].endswith("search.es.sqlite")
    hits = [h.target for h in fulltext.search("plantilla")]
    assert hits == ["guide:Getting-Started"]
    assert [h.target for h in fulltext.search("numero")] == ["guide:Home#ventanas"]  # accents or not
    assert [h.target for h in fulltext.search("stylesheets")] == ["guide:Other-Files"]  # the original's page
    assert fulltext.search("template") == []  # not in the English page translated
    in_language(monkeypatch, "en")
    assert [h.target for h in fulltext.search("template")] == ["guide:Getting-Started"]
    assert fulltext.search("plantilla") == []


def test_a_stale_index_of_a_language_is_rebuilt(library, monkeypatch):
    fulltext.build_all()
    in_language(monkeypatch, "es")
    (library / "books" / "guide.es" / "Other-Files.md").write_text("# Otros archivos\n\nHojas de estilo.\n")
    manual.use_root(library)  # the pages changed under the caches
    db = fulltext.connection()
    assert db.execute("PRAGMA database_list").fetchone()[2] == ""  # in memory
    assert [h.target for h in fulltext.search("hojas")] == ["guide:Other-Files"]


def test_sync_book_copies_a_translation(library, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("sync_book", ROOT / "tools" / "sync_book.py")
    sync_book = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync_book)
    monkeypatch.setattr(sync_book, "MANUAL", library)
    monkeypatch.setattr(sync_book, "REGISTRY", library / "books.json")
    wiki = tmp_path / "guide-es.wiki"
    wiki.mkdir()
    (wiki / "Home.md").write_text("# La guía\n\nOtra vez.\n")
    (wiki / "Other-Files.md").write_text("# Otros archivos\n\nHojas de estilo.\n")
    (wiki / "_Footer.md").write_text("pie\n")
    monkeypatch.setattr("sys.argv", ["sync_book.py", "guide", str(wiki), "--language", "es"])
    assert sync_book.main() == 0
    copied = sorted(p.name for p in (library / "books" / "guide.es").iterdir())
    assert copied == ["Home.md", "Other-Files.md"]  # as the wiki has it, without the skipped footer
    assert sorted(p.name for p in (library / "books" / "guide").iterdir()) == \
        ["Getting-Started.md", "Home.md", "Other-Files.md", "_Sidebar.md"]  # the original untouched
    assert (library / "search.es.sqlite").is_file()
    db = sqlite3.connect(library / "search.es.sqlite")
    assert db.execute("SELECT count(*) FROM help WHERE page = 'Other-Files' AND title = 'Otros archivos'").fetchone()[0]
