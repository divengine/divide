# Test Plan

## 1. Objectives

- Keep the UI-independent core (languages, runners, search) correct with
  fast unit tests.
- Check every feature end to end through the real UI, headless, with
  Textual's pilot: keys pressed, windows and dialogs inspected.
- Check against the real external tools (Div, PHP, Xdebug, language
  servers) when they are available. Those tests are skipped when they are
  not.
- Protect the cross-cutting rules: ASCII/CP437 glyphs only, and the old
  Borland colours unchanged (golden values).

## 2. Test types and tools

| Type | Tool | Scope |
|---|---|---|
| Unit | pytest | lexer, dialect, diagnostics, completion, outline, Div JSON, search, fuzzy matching, themes, help parsing, DBGp parsing |
| Integration (system tools) | pytest + subprocesses | render and resolve through `bridge.php` and Div; `php -l`; scripts; `php -S`; Xdebug; LSP (a fake server and real ones); git on real repositories made by the test; `gh` and `tea` as fake programs that record what they were asked; Composer |
| UI / system | pytest-asyncio + Textual `run_test` / `Pilot` | each window, dialog and command, driven by keys and mouse |
| Visual | `tools/wiki_shots.py`, `tools/screencast.py` | screenshots and GIFs of the manual from the running app, reviewed by eye |
| Packaging | pytest | the version manifest, the Homebrew, Scoop and winget manifests, the MSIX manifest |

`asyncio_mode = "auto"`. Tests that need Div read it from `DIVIDE_DIV_PHP`
(a `vendor/autoload.php` or `div.php`), and those that need Xdebug use
`DIVIDE_SHOT_XDEBUG` or a configured path. Without them, those tests are
skipped.

## 3. Test suites

| File | Area |
|---|---|
| `test_lexer.py` | Div lexer: every construct, dialects, keyed blocks, nesting |
| `test_diagnostics.py` | static checks of templates, Messages window, Alt+F8 |
| `test_complete.py`, `test_completion_ui.py` | completion logic and the popup |
| `test_divjson.py`, `test_jsontree.py` | Div JSON and the tree editor |
| `test_render.py` | render, includes, data files through Div |
| `test_dialector.py` | the dialect assistant and translation, by Div |
| `test_help.py` | books, topics, links, the help window |
| `test_helpsearch.py` | help full-text search: sections, ranking, stems and prefixes, stale index rebuilt, the shipped index current, the dialog and Ctrl+F1 |
| `test_books_languages.py` | books in the interface's language on an example book (`tests/books`): the translation chosen, pages not translated from the original, links, contents, a search index per language, `tools/sync_book.py --language` |
| `test_php.py` | PHP highlighting, `php -l`, outline |
| `test_lsp.py` (+ `fake_lsp_server.py`) | LSP client and UI |
| `test_run.py`, `test_progress.py` | running scripts, the progress box |
| `test_trace.py` | the render trace |
| `test_web.py` | the web server and per-request debugging |
| `test_outline.py` | outline of PHP and templates, following edits |
| `test_explorer.py` | project window: file operations, clicks, local menu, tiling |
| `test_search.py` | find and replace |
| `test_history.py` | File > Open, input line histories |
| `test_palette.py` | Go to file, command palette, fuzzy matching |
| `test_findfiles.py` | Find in files and its window |
| `test_themes.py` | palettes, roles, 16-colour snapping, Borland golden values |
| `test_scrollbars.py` | frame scroll bars |
| `test_shadow.py` | drop shadows |
| `test_glyphs.py` | only ASCII and CP437 in divide's own strings |
| `test_filetypes.py` | the other file types: detection by name and extension, every grammar loads, every capture has a colour, INI and CSV tokens, each sample file coloured in the editor |
| `test_i18n.py` | catalogues complete and current, placeholders and hotkey marks kept, translations single-width, menu and dialog hotkeys unique in each language (the dialogs in a process started in Spanish), language choice, no local `_` hiding gettext |
| `test_app.py` | the application shell, commands, layout |
| `test_welcome.py` | the command line (a folder only when given), the Welcome window and its recent lists, File > Open folder and Close folder, unsaved changes asked about, a file with no folder |
| `test_wheel.py` | the mouse wheel on the Turbo Vision lists |
| `test_alt_keys.py` | Alt+letter opens its menu in every language |
| `test_selection.py` | a selected block drawn over the syntax colours |
| `test_reveal.py` | a jump centres its line and scrolls sideways only as needed; the project window's bar on the revealed file |
| `test_members.py` | the project window unfolds a file into its members |
| `test_children.py` | no process divide starts outlives it |
| `test_git.py`, `test_git_ui.py` | `run.git` (git's output parsed, its commands on real repositories) and the Git menu's windows: stage, commit, branches, merge, stash, discard, history, blame, pull and push |
| `test_diffview.py` | diffs unified and side by side, line numbers, the words that changed |
| `test_forge.py`, `test_forge_ui.py` | GitHub and Gitea through fake `gh` and `tea`; the pull requests and issues window |
| `test_composer.py` | Tools > Composer packages and its assistants |
| `test_setup.py`, `test_divsetup.py` | the Div setup (layers, problems, trust, what the bridge gets) and Options > Div setup |
| `test_packaging.py` | the release's manifests |

## 4. Environment and execution

UI tests start a full application each. On small machines, run **one file
at a time**, at low priority and with a timeout, and never the whole suite at
once:

```sh
nice -n 10 timeout 300 .venv/bin/python -m pytest -q tests/test_palette.py
```

Some UI tests wait for screens. Under heavy memory pressure they may time out
(`WaitForScreenTimeout`) and pass when run alone. Treat such a failure as
environmental only after it passes on a rerun with free memory.

The tests isolate the configuration (`XDG_CONFIG_HOME` in a temporary
folder, `tmp_path_factory.mktemp("config")`), so they never touch the user's
settings, histories or recent lists. That folder must not be inside a project
made by the test: divide writes the recent folders at start, and searches
would find them. Likewise the user's Div setup (`DIV_HOME`) is kept out.

**Continuous integration.** `.github/workflows/tests.yml` runs the whole suite
on every push to `main` and every pull request: Ubuntu with Python 3.11 and
3.12, macOS and Windows with 3.12, with PHP 8.3, Composer, Xdebug and Div
installed in the shop example. A release is built only from a commit whose
tests passed.

## 5. Entry and exit criteria

- **Entry:** the change builds (imports) and its own test file passes.
- **Exit for a commit:** the new or changed behaviour has tests; the test
  files of the touched areas pass; and tests and commits run as separate
  steps.
- **Exit for a UI change in the manual:** the owner has reviewed the UI,
  then screenshots are regenerated and the wiki is updated.

## 6. Defect handling

A defect in divide gets a test that reproduces it, then the fix. A defect in
Div is reported upstream with a minimal template, and divide does not patch
Div.
