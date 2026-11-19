# Glossary

| Term | Meaning |
|---|---|
| **divide** | The IDE for developing generators with the Divengine ecosystem: *div* + *ide*, and the English word *divide*. Always lowercase. |
| **Div** | The Divengine template engine, written in PHP (github.com/divengine/div): a template and a data model become text, which can be code in any language, configuration, data or another template. Templates are rewritten again and again until nothing changes. |
| **Generator** | An independent software project that transforms input models into source code, configuration, templates or other artifacts through explicit, reusable rules (for example, with Div templates and their data). Developed in divide, deployed and run without it. It may implement its own orchestration, CLI, HTTP API or MCP server. Its form as a unit is not decided yet. |
| **Deterministic generation** | Generation that gives the same output from the same inputs, which holds only when every effective input and execution condition is controlled (Div can also read the time, the request, random values and allowed PHP functions). A central use case of divide; reproducible, which is not the same as correct. |
| **Orchestration** | Composing and running several generation stages, with dependencies and validation between them. A generator project may implement it; what divide might offer for it is not decided. |
| **Nodes** | Divengine's independent PHP library for file-based structured data (schemas, nodes, references, indexes). Not integrated in divide; a generator may use it. Its role in generator development is not decided. |
| **Ways** | Divengine's independent PHP library of execution control points (HTTP, CLI or direct calls, routing, hooks, rules). Not integrated in divide; a generator may use it. Its role in generator development is not decided. |
| **Template** | A Div source file (`.tpl` and other extensions Div accepts). |
| **Dialect** | A set of `DIV_TAG_*` overrides that changes the tags of the language (for example ERB-like `<%= %>`), so the generator's syntax does not collide with the syntax it generates. A template chooses one with `@_DIALECT = file`. Defaults mirror the `define()` calls of `div.php`. |
| **Data file** | The JSON (Div JSON) a template is rendered with. By default it is the template's name with `.json`, and it can be chosen per template in Run > Data file. |
| **Div JSON** | Div's own JSON, decoded by `div::jsonDecode`: it accepts variable references (`$name`), comments and single quotes. |
| **Fixed point** | The moment Div stops: a whole cycle of the engine changes nothing. |
| **Mutation** | One change Div makes to the template during a render (a condition decided, an include pasted, a list unrolled, a value replaced). The render trace lists them. |
| **Keyed block** | A Div block whose closer repeats its key: `[$x]...[/$x]`, `?$x...$x?`, `[[x...x]]`, `{{x...x}}`. |
| **Include / preprocessed include** | `{% path %}` / `{%% path %%}`: another template pasted into this one. |
| **Bridge** | `src/divide/run/bridge.php`: the one PHP script divide talks to. It reads a JSON request on stdin and answers in JSON, asking Div to render, resolve includes, validate, load dialects, trace or translate. |
| **Engine** | The Div installation used to render: a `vendor/autoload.php` (Composer) or a `div.php`, chosen in Options > Div engine or found in the project. |
| **Turbo Vision (TV)** | Borland's text-mode UI framework. divide recreates its look on **textual-vision**, a TV-style widget set for Textual. |
| **Textual** | The Python TUI framework below textual-vision. |
| **Project (folder)** | The folder divide works on, given on the command line or opened with File > Open folder. It is optional: files can be opened alone, with no folder. |
| **Welcome window** | What divide shows with nothing to open: Start (new file, open a file, open a folder, help), the recent folders and the recent files. Help > Welcome. |
| **Recent folders and files** | The folders and files opened lately, newest first, kept in the config's `recent`. |
| **Div setup** | How divide sets up Div for a project at design time (editing, checking, rendering, tracing): `.div/setup.json` (the project's) over `~/.div/setup.json` (the user's). Options > Div setup. It does not configure the Div an application runs in production. |
| **Trust (of a setup)** | The developer's consent to a project's `php` settings, which let templates call PHP functions; kept as a hash in `~/.div/trust.json`, asked again when they change. |
| **Area (git)** | Where a change is in Git > Changes: conflicts, staged, changes, untracked. |
| **Forge** | The host of the repository's remote: GitHub (through `gh`) or Gitea, Forgejo, Codeberg (through `tea`). |
| **Filter line** | `» type to filter`: the line over a list or tree that keeps only the items holding what is typed. |
| **Release note** | `releases/<version>.md`: the text of a release on GitHub. With a new `VERSION`, it makes the Release workflow publish that version. |
| **Desktop** | The area between the menu bar and the status line, where windows live. |
| **Window** | A framed, movable view on the desktop (editor, project, Messages, Output, Outline, Watches...). Numbered 1-9 for Alt+n. |
| **Dialog** | A modal window with controls (input lines, check boxes, radio buttons, lists, buttons). |
| **Status line** | The bottom row: key hints on the left, a context hint (language, verdict, spinner) on the right. |
| **Command** | A Turbo Vision command number (`Command.*` or `CM_*`) posted by menus, keys and the status line, and handled in `Divide.run_command`. |
| **Mixin** | A class that adds one feature area to the app (`RunMixin`, `LspMixin`, `PaletteMixin`...). The app is the composition of its mixins. |
| **Palette (colours)** | A colour theme (`themes.Palette`): 16 ANSI slots, UI roles, syntax roles. Not to be confused with the command palette. |
| **Command palette** | Alt+P: every menu entry, found by typing (VS Code's Ctrl+Shift+P, which Windows Terminal keeps for itself). |
| **Go to file** | Ctrl+P: every project file, found by typing. |
| **History (input line)** | Turbo Vision's THistory: what an input line accepted before, kept per kind of line in the config. |
| **Search index** | `manual/search.sqlite`: the help books' sections in SQLite FTS5 tables (stemmed and as written), built by `tools/sync_book.py`, ranked with BM25 by Help > Search. |
| **Catalogue (translation)** | `locale/<lang>/LC_MESSAGES/divide.po` (and its compiled `.mo`): the interface's texts in one language, made with gettext. |
| **Help book** | A manual shown in the help window, copied from a wiki or a docs folder by `tools/sync_book.py`. divide has two: divide and Div. |
| **Language** | An entry in `divide.lang`: its name, extensions, help topic and whether divide checks it. |
| **LSP / language server** | A Language Server Protocol server (phpactor, intelephense...) that gives completion, hover, definitions and diagnostics. |
| **DBGp** | The protocol Xdebug speaks. divide is the DBGp client. |
| **Render trace** | Debug > Render trace: Div's mutations, step by step, with the template at each step. |
| **Dialector** | Tools > Dialector: the assistant that builds and validates Div dialects (a port of divengine/dialector). |
| **Messages window** | Turbo Pascal's list of errors and warnings. Enter goes to the place. |
| **Wiki shots** | The screenshots of the manual, produced by `tools/wiki_shots.py` from a running divide. |
