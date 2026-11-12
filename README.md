# divide

Terminal IDE (TUI) for the Divengine projects. First milestone: the official
editor for [Div](https://github.com/divengine/div) templates.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/divide [folder] [files...]
.venv/bin/python -m divide.lang.div.preview [--kinds] file.tpl   # highlighted dump / token list
.venv/bin/pytest
```

Keys: `ctrl+s` save · `ctrl+w` close tab · `ctrl+b` explorer · `ctrl+pgup/pgdn` switch tab · `ctrl+q` quit · `ctrl+p` palette.

## Layout

- `src/divide/lang/div/` — the language, UI-independent
  - `dialect.py` — `DIV_TAG_*` defaults (mirrors `div.php`), lenient dialect JSON, `@_DIALECT` resolution
  - `lexer.py` — dialect-aware lexer → `Token(start, end, kind)`
- `src/divide/editor/` — `DivEditor` (Textual `TextArea` fed by the lexer instead of tree-sitter) and theme
- `src/divide/app.py` — the TUI shell (explorer, tabs, status bar)
- `docs/div-language.md` — notes on Div as understood by the editor
