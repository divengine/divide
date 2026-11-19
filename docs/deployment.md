# Deployment and Configuration

## 1. Requirements

| Component | Needed for | Notes |
|---|---|---|
| Python 3.11+ | divide from a checkout | developed on 3.14; the standalone binaries bring their own |
| textual 8.2, textual-vision 0.0.1, tree-sitter, tree-sitter-php, pygls 2 | divide itself | installed by pip from `pyproject.toml` |
| A terminal with 16+ colours | display | truecolour preferred; any font with CP437 box characters |
| PHP 8 CLI | render, checks of PHP, scripts, web server | `php` on `PATH` |
| Div 6.x | render, include resolution, dialects, trace, translate | a Composer `vendor/autoload.php` in the project, or a `div.php`; Options > Div engine |
| Xdebug 3 | debugger, debugging web requests | a `xdebug.so` path in Options > Xdebug if it is not loaded by PHP |
| phpactor or intelephense | PHP completion, hover, definitions | optional; Options > Language servers |
| git | the Git menu, the project window's marks, the editor's margin; Go to file and Find in files respect `.gitignore` | optional; without it, no Git menu and a folder walk |
| gh, tea | Git > Pull requests and issues (GitHub; Gitea, Forgejo, Codeberg) | optional; signed in with `gh auth login` / `tea login add` |
| mcp 2.3+ (the official MCP SDK) | `divide --mcp` | optional: the `mcp` extra, `pip install -e ".[mcp]"` in a checkout; not in the standalone binaries yet |
| Composer | Tools > Composer packages | optional; `$DIVIDE_COMPOSER`, Options, a `composer.phar` in the project or `composer` on `PATH` |

## 2. Installation

Each release publishes divide ready to run, with Python and everything else
inside: `brew install divengine/tap/divide` (macOS, Linux), Scoop or the
`.msi` (Windows), `.deb`, `.rpm`, `.apk`, Arch packages and the AppImage
(Linux), and the binary alone (see [section 6](#6-release)).

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

- `folder`: the project. A folder is opened only when it is given (`divide .`
  for the current one), as VS Code does. Files alone open with no folder;
  with nothing, divide shows the Welcome window (start, recent folders and
  files). An argument that is a directory is the folder (the last one, if
  several); the others are files.
- `--version`: divide's version.
- `--palette`: one of the themes (`turbo-pascal`, `turbo-c`, `free-pascal`,
  `modern-dark`). The default is the one chosen in Options > Colors.
- `--colors`: forces the colour depth. By default it is what the terminal
  reports.
- `--language`: the interface's language for this run. By default it is the
  one chosen in Options > Language, else the system's.

```sh
divide --mcp /path/to/project
```

- `--mcp`: no interface; serves divide's MCP server for the project folder
  over stdio, for an MCP client to start (the protocol on stdout, logs on
  stderr). It takes exactly one folder and needs the `mcp` extra. The
  [MCP Server](https://github.com/divengine/divide/wiki/MCP-Server) page of
  the manual has the tools, a client configuration and the trust model.

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
| `recent` | opening a folder or a file | `folders` and `files` opened lately, newest first, 12 each (the Welcome window; Del forgets one) |
| `composer` | Tools > Composer packages | the Composer to run, when it is not found by itself |
| `git_diff_side_by_side` | S in a diff | the diffs side by side instead of unified |

The Div setup is not in this file: it is the project's `.div/setup.json` and
the user's `~/.div/setup.json` (`$DIV_HOME` moves that folder), with the
trusted `php` settings of projects in `~/.div/trust.json`. Options > Div setup
edits them.

Environment variables:

| Variable | Use |
|---|---|
| `XDG_CONFIG_HOME` | where `divide/config.json` lives |
| `XDG_CACHE_HOME` | caches of language servers |
| `DIVIDE_LANGUAGE` | the interface's language for this run, over everything else (the tests and screenshots set `en`) |
| `LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG` | the system's language, used when nothing else chooses |
| `DIV_HOME` | the user's Div folder (`setup.json`, `trust.json`), by default `~/.div` |
| `DIVIDE_COMPOSER` | the Composer to run, over everything else |
| `DIVIDE_DIV_PHP` | tests and screenshots: the Div engine to use |
| `DIVIDE_SHOT_XDEBUG`, `DIVIDE_SHOT_LSP`, `DIVIDE_SHOT_GH`, `DIVIDE_SHOT_KEEP_SVG` | screenshots and screencasts only (`tools/wiki_shots.py`, `tools/screencast.py`) |

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

## 6. Release

The version is the one line of `VERSION`: `pyproject.toml`, `divide.__version__`,
`divide --version` and the binaries read it. A release is a change of
`VERSION` with its note, `releases/<version>.md`, merged into `main`. When
the tests pass there (`.github/workflows/tests.yml`: Linux with Python 3.11
and 3.12, macOS, Windows), `.github/workflows/release.yml` sees a version
with no tag yet and its note, and:

1. builds the standalone binary with PyInstaller (`packaging/divide.spec`,
   `packaging/divide_main.py`) on Linux (x86_64, arm64), macOS (arm64,
   x86_64) and Windows (x86_64);
2. packs it: archives, the binary alone, `.deb`, `.rpm`, `.apk` and Arch
   packages (`packaging/nfpm.yaml`), the AppImage (`packaging/appimage/`), the
   `.msi` (`packaging/divide.wxs`);
3. writes `SHA256SUMS`, the Homebrew formula and the Scoop manifest
   (`packaging/manifests.py`);
4. tags the commit `v<version>` and publishes the release with the note and
   the files; a version with a letter (`0.3.0rc1`) is a pre-release;
5. pushes the formula to `divengine/homebrew-tap` (with the
   `HOMEBREW_TAP_DEPLOY_KEY` secret).

winget (`packaging/winget_submit.py`, with the `WINGET_TOKEN` secret) and the
Microsoft Store (`packaging/msix/`, with the `MSSTORE_*` variables and
secrets) are wired but off: without them a release does not try either. The
details, and what each file is for, are in
[releases/README.md](../releases/README.md).
