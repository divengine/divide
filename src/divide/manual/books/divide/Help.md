# Help

divide carries its documentation with it, as books: this manual, and Div's own documentation. **F1** opens the help at the topic of the window you are in, in a help window coloured like the one in Borland Pascal: black on cyan, cross references in yellow.

![the help window on the Dialector topic](images/help.png)

## Opening the help

| Key | Menu | |
|---|---|---|
| **F1** | Help > Using help | the topic of the active window: the editor, a data file, the project, the dialector, the output, the messages |
| | Help > Contents | the table of contents of the book on show (divide's when the help is closed) |
| | Help > Books | the list of books |
| **Shift+F1** | Help > Index | every topic and every section of the book on show, alphabetically |
| **Ctrl+F1** | Help > Topic search | the topic of the word under the editor's cursor, in any book (for example *dialect*, *render*, *loops*). When no topic has that name, **Search** opens with the word. In a PHP file with a [[language server|Language Servers]], what the server knows about the symbol instead |
| | Help > Search | the books by words: see below |
| **Alt+F1** | Help > Previous topic | back to the topic you came from |

F1 in the help window itself shows this page.

![the index: every topic and section, alphabetically](images/help-index.png)

## The help in Spanish

The books are also in Spanish: this manual and Div's documentation, translated in wikis of their own, [help-divide-es](https://github.com/divengine/help-divide-es/wiki) and [help-div-es](https://github.com/divengine/help-div-es/wiki). When the interface is in Spanish (see [[The Desktop#language]]), the help shows them; a page not translated yet shows in English. The topics are the same in both languages, so **F1** and the links lead to the same places.

## Searching the help

**Help > Search** finds the words you type in every book, like a web search engine. As you type, it lists the sections that contain the words, best first. Each row is one section of a page, such as `Breakpoints · Debugging PHP`, with the words you typed highlighted, and rows from Div's documentation are marked *Div*. The pane below shows the book and the sentence where the words appear.

![Help > Search](images/help-search.png)

- **The order.** Sections that contain all the words come first. A word in a page title counts most, then a word in a heading, then a word in the text. When no section has every word, sections with any of them are listed.
- **Word forms.** Finished words also match their other forms: *configure* finds *configuration* and *configured*, *template* finds *templates*. In the Spanish books the words match as written, accents and capitals aside: *numero* finds *Número*.
- **While you type.** The last word matches as the start of a word, so *itera* already finds *Iterations*.
- **↑ ↓** (and **PgUp PgDn**) move the bar while you keep typing. **Enter** or a double click opens the help at that section. **Esc** closes.

## Moving in the help window

| Key | |
|---|---|
| **Tab** / **Shift+Tab** | next / previous cross reference |
| **Enter** or a click | follow the cross reference, or open the web page in the browser |
| **Alt+F1** / **Backspace** | previous topic |
| **↑ ↓ PgUp PgDn Home End** | scroll |
| **Esc** | close the help window |

The help window is a window like the others: **F5** zooms it, **F6** moves to the next window and back, and the help stays where you left it.

## Books

**Help > Books** lists them. Each book has its own contents and index, and the window's title names the book when it is not divide's.

| Book | What it is | Written in |
|---|---|---|
| divide | this manual | the [divide wiki](https://github.com/divengine/divide/wiki) |
| Div | the template engine: the language, dialects, the PHP API | the [`docs` folder of Div](https://github.com/divengine/div/tree/master/docs) |

![Div's documentation in the help window](images/help-div.png)

A book is a copy of the place where it is written, so each documentation is written once. Pictures are left out. Links to other topics are cross references, also between books. Links to web pages are underlined: **Tab** reaches them too, and **Enter** or a click opens them in the browser. They are also the terminal's own hyperlinks, so Ctrl+click (or the terminal's gesture for links) opens them as well, even over SSH when the terminal is local.

![the list of books](images/help-books.png)

## Adding a book

The books are listed in `src/divide/manual/books.json`. Each entry gives:

| Field | |
|---|---|
| `id`, `title`, `description` | how the book is named and listed |
| `source`, `path` | the repository and the folder inside it with the pages (Markdown) |
| `home` | the first page |
| `contents` | the table of contents: a wiki's `_Sidebar.md`, or a file listing the pages in order (one path per line, like Div's `book-order.txt`); pages numbered `02.10 …` are nested under `02 …` |
| `skip` | pages to leave out |

Then copy the pages in with `tools/sync_book.py <id> <checkout of the source>`, and run it again whenever the source changes:

```bash
tools/sync_book.py divide path/to/divide.wiki
tools/sync_book.py div path/to/div
tools/sync_book.py --index          # only rebuild the search index
```

After copying, the script rebuilds the index **Help > Search** uses (`src/divide/manual/search.sqlite`), from every book. If the pages ever differ from the index, for example when a book is copied by hand, divide rebuilds the index in memory the first time you search.
