# divide

**The Div template IDE that lives in your terminal.**

divide is a full-screen, keyboard-first IDE for [Div](https://github.com/divengine/div)
templates, in the spirit of the Borland IDEs: overlapping windows, drop-down
menus, dialogs with shadows and a status line that always tells you the next
key. It understands Div the way Div does: it reads your dialect, checks your
templates as you type, completes variables from your real data, and renders
through the real Div engine, side by side with the code.

![divide: project, template and rendered output side by side](https://raw.githubusercontent.com/wiki/divengine/divide/images/hero.png)

## What it does

- **Speaks Div.** Every construct of the language is highlighted, in the
  template's own dialect (`@_DIALECT`).
- **Errors before you render.** Unclosed loops, orphan `[/$x]`, conditions
  without `{/?}`, tags Div would leave as text, broken JSON in `{= x: … =}`,
  includes Div cannot resolve. They are painted in the editor and listed in a
  Turbo Pascal–style Messages window, and Alt+F8 walks through them.
- **Completion from your data.** `{$` offers the keys of `page.json`. Inside
  `[$products]` you get a product's fields, the item name and Div's `_index`,
  `_is_last`… `[$` closes the loop for you, `{% ` lists your templates, and
  Ctrl+Space offers every Div construct as a snippet.
- **The real engine.** Ctrl+F9 renders through PHP and Div, unsaved edits
  included. Includes are resolved by Div's own `getTplPath()` and data is
  decoded by Div's own `jsonDecode()`. Ctrl+Enter opens the template an
  include points to.
- **Data as code or as a tree.** Div JSON (references, comments, single
  quotes) is highlighted and validated, and Ctrl+T edits the same buffer as a
  tree.
- **Your own dialects.** Tools > Dialector builds a Div dialect section by
  section, with a live preview and Div's verdict on every change: Div's
  `isValidCurrentDialect()` validates it and Div's translator reads it back.
  It can import and export dialects, and a wizard translates templates from
  one dialect to another with Div's own `translate()`.
- **PHP next to the templates.** `.php` files are highlighted with
  tree-sitter's PHP grammar and checked by PHP itself (`php -l`) as you type.
  Ctrl+Enter on `new div('page.tpl')` opens the template.
- **Language servers.** With phpactor or intelephense (in the project or the
  PATH), PHP gets completion (with the classes of `vendor/`, like Div's, and
  their `use` lines added for you, and the documentation of each item),
  the signature of the call you type, hover (Ctrl+F1), go to definition
  (Ctrl+Enter) and the server's diagnostics. divide is a generic LSP client (pygls), so
  other languages are one entry away.
- **A project window that does things.** You can create, rename and delete
  files and folders without leaving the IDE.
- **Works in any terminal.** It runs over SSH, inside tmux, and on the server
  where the templates live.

## Quick start

```bash
git clone https://github.com/divengine/divide.git && cd divide
tools/install.sh                           # the `divide` command, in ~/.local/bin
cd ~/sites/my-project && divide            # any folder; or: divide page.tpl
```

`tools/install.sh` installs divide in the checkout's `.venv` (editable) and
links the command, so `git pull` updates it. Or, isolated:
`pipx install git+https://github.com/divengine/divide.git`.

Rendering and include checks need `php` and Div in your project
(`composer require divengine/div`). divide finds the engine there, in
`$DIVIDE_DIV_PHP`, or in Options > Div engine.

| | |
|---|---|
| `F10` / `Alt+letter` | menus |
| `Ctrl+B` | project window: `Ins` new file, `F7` new folder, `F2` rename, `Del` delete |
| `Ctrl+Space` | completion |
| `Alt+F9` · `Alt+F8` | check the template · next error |
| `Ctrl+F9` | render with its data (`page.tpl` + `page.json`) |
| `Ctrl+T` | data tree ⇄ code |
| `Ctrl+Enter` | go to the included template |
| `Alt+T` | Tools: Dialector, Translate a template |
| `F1` · `Shift+F1` | help on the active window · help index |
| `F2` · `F3` · `Alt+X` | save · open · exit |

## Manual

The **[wiki](https://github.com/divengine/divide/wiki)** is the user manual,
with screenshots. divide carries its documentation as books: this manual and
[Div's documentation](https://github.com/divengine/div/tree/master/docs).
`F1` opens the help at the topic of the window you are in, in a help window
with Borland's help colours; each book has its contents, an index and cross
references.

- [Installation](https://github.com/divengine/divide/wiki/Installation)
- [Getting Started](https://github.com/divengine/divide/wiki/Getting-Started)
- [The Desktop](https://github.com/divengine/divide/wiki/The-Desktop)
- [Editing Templates](https://github.com/divengine/divide/wiki/Editing-Templates)
- [Completion](https://github.com/divengine/divide/wiki/Completion)
- [Checking Templates](https://github.com/divengine/divide/wiki/Checking-Templates)
- [Rendering](https://github.com/divengine/divide/wiki/Rendering)
- [Data Files](https://github.com/divengine/divide/wiki/Data-Files)
- [Project Window](https://github.com/divengine/divide/wiki/Project-Window)
- [Dialector](https://github.com/divengine/divide/wiki/Dialector)
- [Translating Templates](https://github.com/divengine/divide/wiki/Translating-Templates)
- [Keyboard Reference](https://github.com/divengine/divide/wiki/Keyboard-Reference)
- [Troubleshooting](https://github.com/divengine/divide/wiki/Troubleshooting)
- [Help](https://github.com/divengine/divide/wiki/Help)

### One convention: save first

Div can take a template as a string, without a file, but then it has no folder.
Its includes would not resolve the way they will in production, and divide
would not know its data file. So **templates are saved before Div sees them**.
An untitled template is still highlighted, completed and checked, but its
includes are not resolved, and Render and Go to include ask you to save it
first. Once a template has a file, its unsaved edits are always what Div gets.

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                                                  # render tests need DIVIDE_DIV_PHP
.venv/bin/python -m divide.lang.div.preview [--kinds] file.tpl    # highlighted dump / token list
```

`examples/shop` is a small Div project (one template broken on purpose, and an
ERB-like `erb.dialect`) used by
the manual. `tools/wiki_shots.py --out <wiki clone>/images` retakes the
manual's screenshots from the real app on it, so they follow UI changes.
`src/divide/manual/books.json` lists the help's books and where each is
written; `tools/sync_book.py <book> <checkout>` copies a book's pages into
`src/divide/manual/books/<book>/`, which the help window reads: run it after
the wiki (or Div's `docs`) changes.

Tests that render need `DIVIDE_DIV_PHP` (an `autoload.php`, or a Div checkout's
`src/div.php` with its `vendor/` installed); they are skipped otherwise.

### How divide relies on Div

What the engine decides is asked to the engine. The PHP bridge
(`src/divide/run/bridge.php`) runs Div for renders and answers questions
about it, such as where an include leads (`getTplPath()` with the template's
path, the render's working directory and the include history), which
dialect a template's `@_DIALECT` loads (`getTplPath()`, `getFileContents()`,
`jsonDecode()`, as `prepareDialect()` does), whether a dialect is valid
(`isValidCurrentDialect()`) and how a template reads in another dialect
(`translate()`). The Python side highlights, completes and checks the syntax
the lexer sees; until Div answers (or without Div) it guesses the dialect
file only to colour, and reports nothing about it.

### Layout

- `src/divide/lang/__init__.py` — the languages divide edits, by extension (name, help topic, checked or not)
- `src/divide/lsp/` — the Language Server Protocol client: known servers, positions, the session (pygls)
- `src/divide/ui/lsp.py` — language servers in the IDE: lifecycle, completion, hover, definitions, Options dialog
- `src/divide/lang/php.py` — PHP: tree-sitter-php's grammar for colours, `php -l` for errors
- `src/divide/lang/divjson.py` — Div JSON: tokens, parser with positions, writer, tree edits
- `src/divide/lang/div/` — the language, UI-independent (lexer, dialects, diagnostics)
  - `dialect.py` — `DIV_TAG_*` defaults (mirrors `div.php`), lenient dialect JSON, `@_DIALECT` resolution
  - `lexer.py` — dialect-aware lexer → `Token(start, end, kind)`
  - `diagnostics.py` — Div errors and warnings for the editor and the Messages window
  - `complete.py` — completion of variables, loops, include paths and tags
- `src/divide/editor/` — `DivEditor` (Textual `TextArea` fed by the lexer instead of tree-sitter) and theme
- `src/divide/ui/` — Turbo Vision pieces on [textual-vision](https://pypi.org/project/textual-vision/):
  editor / project windows, message boxes, file dialog, completion list, project file operations,
  the dialector, the help window; `HRule` / `VRule` divide a window and join its frame in Ts
- `src/divide/run/` — rendering: `bridge.php` (runs Div, replies JSON) and `render.py`
- `src/divide/manual/` — the built-in help: books (copies of a wiki or a docs folder) laid out as topics with cross references
- `src/divide/app.py` — the application: menus, status line, commands, window management
- `docs/div-language.md` — notes on Div as understood by the editor

### textual-vision

`textual-vision` is pinned to `0.0.1` (young, single maintainer). Things divide
works around, to revisit on upgrades:

- nested sub-menus get no keyboard focus → menus are kept one level deep;
- `DeskTop` has no API to reorder windows → `Divide._cycle` uses `_z_order`;
- `TextArea` binds `F6` (select line) and `Ctrl+W` → those bindings are `priority`;
- `F10` only highlights the bar, leaving focus in the editor → `DropMenuBar` opens the menu;
- handlers of every class in the MRO run unless `prevent_default()` → overrides never call `super()`;
- no shadows → `divide.ui.shadow` restyles the composited lines (Textual compositor subclass).

If the project stalls, its code (Apache-2.0, ~4.7k lines) can be vendored.
