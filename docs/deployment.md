# Deployment and Configuration

## 1. Requirements

| Component | Needed for | Notes |
|---|---|---|
| Python 3.11+ | divide itself | developed on 3.14 |
| textual 8.2, textual-vision 0.0.1, tree-sitter, tree-sitter-php, pygls 2 | divide itself | installed by pip from `pyproject.toml` |
| A terminal with 16+ colours | display | truecolour preferred; any font with CP437 box characters |
| PHP 8 CLI | render, checks of PHP, scripts, web server | `php` on `PATH` |
| Div 6.x | render, include resolution, dialects, trace, translate | a Composer `vendor/autoload.php` in the project, or a `div.php`; Options > Div engine |
| Xdebug 3 | debugger, debugging web requests | a `xdebug.so` path in Options > Xdebug if it is not loaded by PHP |
| phpactor or intelephense | PHP completion, hover, definitions | optional; Options > Language servers |
| git | Go to file and Find in files respect `.gitignore` | optional; without it, a folder walk |

## 2. Installation

From a checkout:

```sh
tools/install.sh            # creates .venv, installs divide editable, links ~/.local/bin/divide
tools/install.sh /usr/local/bin
```

The command is a link into the checkout's virtual environment, so `git
pull` updates it. Remove the link to uninstall. The
[Installation](https://github.com/divengine/divide/wiki/Installation) page of
the manual covers per-platform details and terminal setup (fonts, colours,
tmux).

## 3. Running

```sh
divide [folder] [files...] [--palette NAME] [--colors auto|truecolor|256|16] [--language auto|en|es]
```

- `folder`: the project, by default the current folder.
- `--palette`: one of the themes (`turbo-pascal`, `turbo-c`, `free-pascal`,
  `modern-dark`). The default is the one chosen in Options > Colors.
- `--colors`: forces the colour depth. By default it is what the terminal
  reports.
- `--language`: the interface's language for this run. By default it is the
  one chosen in Options > Language, else the system's.

## 4. Configuration

One JSON file: `$XDG_CONFIG_HOME/divide/config.json` (by default
`~/.config/divide/config.json`). It is written by the dialogs. Editing it by
hand is possible while divide is closed.

| Key | Set by | Meaning |
|---|---|---|
| `palette` | Options > Colors | the colour theme |
| `colors` | Options > Colors | colour depth: `auto` or a forced one (applies at the next start) |
| `icons` | Options > Plain symbols / File type marks | the project tree's file marks |
| `div_engine` | Options > Div engine | the Div engine to render with |
| `xdebug` | Options > Xdebug | the Xdebug extension to load |
| `lsp`, `lsp_commands` | Options > Language servers | which server per language, and custom commands |
| `run_args` | Run > Parameters | the arguments of each script |
| `web` | Run > Web server | address, document root, router, browser |
| `language` | Options > Language | the interface's language: `auto` (the system's), `en`, `es` (applies at the next start) |
| `history` | every input line with `▐↓▌` | the input histories, by kind (`file`, `find`, `find-files`, `commands`...), 20 entries each |

Environment variables:

| Variable | Use |
|---|---|
| `XDG_CONFIG_HOME` | where `divide/config.json` lives |
| `XDG_CACHE_HOME` | caches of language servers |
| `DIVIDE_LANGUAGE` | the interface's language for this run, over everything else (the tests and screenshots set `en`) |
| `LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG` | the system's language, used when nothing else chooses |
| `DIVIDE_DIV_PHP` | tests and screenshots: the Div engine to use |
| `DIVIDE_SHOT_XDEBUG`, `DIVIDE_SHOT_LSP`, `DIVIDE_SHOT_KEEP_SVG` | screenshots only (`tools/wiki_shots.py`) |

## 5. Packaged resources

`pyproject.toml` ships `run/*.php` (the bridge), `manual/books.json`, the
books' pages (`manual/books/*/*`, a translation in `books/<id>.<lang>`), the
help's search indexes (`manual/search.sqlite`, `manual/search.<lang>.sqlite`) and the compiled translations
(`locale/*/LC_MESSAGES/*.mo`) inside the package. After changing texts,
`tools/i18n.py all` extracts, merges and compiles the catalogues. The books are refreshed from
their sources, and the index rebuilt, with:

```sh
.venv/bin/python tools/sync_book.py divide <path to divide.wiki clone>
.venv/bin/python tools/sync_book.py divide <path to a Spanish wiki> --language es
.venv/bin/python tools/sync_book.py --index     # only the search indexes
```

## 6. Release (Transition, planned)

A release would publish a wheel (`python -m build`) with the version in
`pyproject.toml` and `divide/__init__.py`, note the supported Div versions,
and refresh the help books.
