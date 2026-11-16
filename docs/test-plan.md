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
| Integration (system tools) | pytest + subprocesses | render and resolve through `bridge.php` and Div; `php -l`; scripts; `php -S`; Xdebug; LSP (a fake server and real ones) |
| UI / system | pytest-asyncio + Textual `run_test` / `Pilot` | each window, dialog and command, driven by keys and mouse |
| Visual | `tools/wiki_shots.py` | screenshots of the manual from the running app, reviewed by eye |

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
| `test_app.py` | the application shell, commands, layout |

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
folder), so they never touch the user's settings or histories. A project
created in a test must not contain that configuration folder, or searches
would find the histories.

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
