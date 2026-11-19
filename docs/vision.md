# Vision

## 1. Introduction

divide is a full-screen terminal IDE in the style of the Borland IDEs (Turbo
Pascal, Turbo C, Borland Pascal): overlapping windows, drop-down menus,
dialogs with shadows and a status line that always shows the next key. It
started as the IDE for [Div](https://github.com/divengine/div), the PHP
template engine, and is built so that languages and help books are plug-ins:
it already edits Div templates, Div JSON data and PHP, and it reads the
manuals of divide and of Div.

## 2. Positioning

### 2.1 Problem statement

| | |
|---|---|
| **The problem of** | writing Div templates with general-purpose editors |
| **affects** | developers who use Div, and Div's maintainers |
| **the impact of which is** | Div's constructs (lists, conditions, includes, dialects, data references) are shown as plain text; errors appear only at render time or are silently left in the output; the template's data and the engine's behaviour (a fixed-point rewrite, not a top-down pass) are invisible |
| **a successful solution would** | understand Div the way Div does: highlight and check the template in its own dialect, complete from the real data, render and trace through the real engine, all in one place, in any terminal, including over SSH |

### 2.2 Product position statement

For developers who write Div templates and PHP, often on remote machines,
divide is a terminal IDE that speaks Div through Div itself: the engine
renders, validates dialects, resolves includes and decodes data. Unlike
general editors with a syntax file, it reads the template's dialect, checks
what Div would trip over, completes from the data file and shows how Div
mutated the template into its output.

## 3. Stakeholders and users

| Stakeholder | Role | Interest |
|---|---|---|
| Div's author and maintainer | product owner, main user | an IDE that respects Div's semantics; Div stays the source of truth and is never modified for the IDE |
| Div template developers | users | edit, check, render and debug templates quickly, keyboard first |
| PHP developers | users | edit, run and debug the PHP around the templates (Xdebug, language servers, `php -S`) |
| Plug-in authors | extenders | add a language or a help book without touching the core |

User environment: terminals on Linux, macOS and Windows, often through SSH
and tmux, with fonts the user does not control. That is why divide keeps to
ASCII and CP437 glyphs and why it works with 16 colours as well as truecolour.

## 4. Key needs and features

| Need | Feature |
|---|---|
| See Div's structure | dialect-aware lexer and highlighting (`@_DIALECT`), Div JSON highlighting, outline of templates and PHP files |
| The rest of a PHP project | highlighting of HTML, CSS, JavaScript, Markdown, SQL, XML, YAML, TOML, shell scripts and `.env`, INI and CSV |
| Catch errors before rendering | static checks (unclosed blocks, orphan closers, broken JSON in definitions, unresolvable includes), Messages window, Alt+F8 / Alt+F7 |
| Write faster | completion of variables from the data file, loop item fields, includes, Div snippets; language servers for PHP |
| Run what will run in production | render through PHP and the real Div (unsaved edits included), Output window, data file per template, data tree editor |
| Understand a render | render trace: Div's mutations one by one until the fixed point |
| Own dialects | Dialector (build, validate with Div, import, export), template translation with Div's `translate()` |
| PHP around the templates | `php -l` checks, run with arguments, Xdebug debugger (breakpoints, step, watches, call stack, evaluate), built-in web server with debugging per request |
| Find your way | project window, Go to file, command palette, Find / Replace, Find in files, Go to included template |
| Learn in place | help books (divide's manual, Div's documentation) inside the IDE, context help on F1, full-text search of the books with ranking |
| Version control in place | the Git menu: what changed (in the project window, the editor's margin and Git > Changes), diffs as a code review shows them, commits, history with its graph, branches, merges and stashes, blame, pull, push; pull requests and issues of GitHub and Gitea |
| The project's PHP setup | Tools > Composer packages (Composer runs every change); Options > Div setup: how Div is set up for the project at design time (`.div/setup.json`) |
| Start where you left off | a folder, a file or nothing on the command line, as VS Code; the Welcome window with the recent folders and files; File > Open folder |
| Comfortable for hours | colour themes (Turbo Pascal, Turbo C, Free Pascal, modern dark), drop shadows, input line histories |

## 5. Constraints

- Div is never modified for divide. Div bugs found while building divide are reported upstream.
- What Div decides (rendering, include resolution, data decoding, dialect validation, translation) is asked of Div through PHP, never reimplemented in Python.
- Existing tools are reused before new ones are written: tree-sitter for PHP, `php -l`, Xdebug, `php -S`, language servers, git, `gh` and `tea`, Composer.
- The user manual documents divide only. It links to Div's documentation instead of copying it.
- divide's own glyphs stay ASCII or CP437 and fixed width, with no Nerd Fonts and no wide or emoji characters.

## 6. Scope and quality ranges

In scope: a single-user desktop IDE in the terminal, one project folder at a
time (or files on their own, with no folder), git through the system's own
`git`. Out of scope for now: multi-root workspaces, collaborative editing, a
plug-in marketplace.

Quality ranges are detailed in the [supplementary specification](supplementary-specification.md):
responsiveness while typing, modest memory use, and behaviour that is the
same in every terminal.
