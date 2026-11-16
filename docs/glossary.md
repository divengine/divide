# Glossary

| Term | Meaning |
|---|---|
| **Div** | The PHP template engine divide was born for (github.com/divengine/div). Templates are rewritten again and again until nothing changes. |
| **Template** | A Div source file (`.tpl` and other extensions Div accepts). |
| **Dialect** | A set of `DIV_TAG_*` overrides that changes the tags of the language (for example ERB-like `<%= %>`). A template chooses one with `@_DIALECT = file`. Defaults mirror the `define()` calls of `div.php`. |
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
| **Desktop** | The area between the menu bar and the status line, where windows live. |
| **Window** | A framed, movable view on the desktop (editor, project, Messages, Output, Outline, Watches...). Numbered 1-9 for Alt+n. |
| **Dialog** | A modal window with controls (input lines, check boxes, radio buttons, lists, buttons). |
| **Status line** | The bottom row: key hints on the left, a context hint (language, verdict, spinner) on the right. |
| **Command** | A Turbo Vision command number (`Command.*` or `CM_*`) posted by menus, keys and the status line, and handled in `Divide.run_command`. |
| **Mixin** | A class that adds one feature area to the app (`RunMixin`, `LspMixin`, `PaletteMixin`...). The app is the composition of its mixins. |
| **Palette (colours)** | A colour theme (`themes.Palette`): 16 ANSI slots, UI roles, syntax roles. Not to be confused with the command palette. |
| **Command palette** | Ctrl+Shift+P: every menu entry, found by typing. |
| **Go to file** | Ctrl+P: every project file, found by typing. |
| **History (input line)** | Turbo Vision's THistory: what an input line accepted before, kept per kind of line in the config. |
| **Help book** | A manual shown in the help window, copied from a wiki or a docs folder by `tools/sync_book.py`. divide has two: divide and Div. |
| **Language** | An entry in `divide.lang`: its name, extensions, help topic and whether divide checks it. |
| **LSP / language server** | A Language Server Protocol server (phpactor, intelephense...) that gives completion, hover, definitions and diagnostics. |
| **DBGp** | The protocol Xdebug speaks. divide is the DBGp client. |
| **Render trace** | Debug > Render trace: Div's mutations, step by step, with the template at each step. |
| **Dialector** | Tools > Dialector: the assistant that builds and validates Div dialects (a port of divengine/dialector). |
| **Messages window** | Turbo Pascal's list of errors and warnings. Enter goes to the place. |
| **Wiki shots** | The screenshots of the manual, produced by `tools/wiki_shots.py` from a running divide. |
