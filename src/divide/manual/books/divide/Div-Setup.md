# Div Setup

Your PHP application sets Div up in its own code: the folder of its templates, a dialect, globals, functions that templates may call... divide does not run that code. So a project tells divide how to set Div up **while you design**, in `.div/setup.json`, and every render, check, include, dialect and trace goes through that setup. Your application is not touched: this is divide's Div, not the application's.

**Options > Div setup...** edits it section by section. Or open the file and edit it as JSON: divide marks what it would leave out as you type.

![Options > Div setup: the sections, what is in effect and where it comes from, Div's verdict](images/div-setup.png)

## Where it lives

| File | For |
|---|---|
| `.div/setup.json` | the project. divide looks for it from the folder it opened upwards, as git looks for `.git`. Commit it: the team shares it. |
| `~/.div/setup.json` | you, in every project: your own engine, a dialect you always use, the request you simulate... (`DIV_HOME` moves the folder). |

- The project wins over the user. Lists are joined (the project's first) and objects are merged by key.
- `null` means *Div's default*: `"files": null` in the project drops what your own setup says about extensions.
- Relative paths are relative to the folder that holds that `.div`: the project's root, or your home folder.
- Everything is optional. Without any setup, divide uses Div exactly as it comes.
- An entry that is wrong is left out, and the rest still counts. It shows in the [[Messages window|Checking Templates]] as `SETUP: .div/setup.json: ...` (Enter goes to it), and in the editor while you edit the file.

In the editor, an entry that is left out is marked, and with the cursor on it the status line says why (`Warning: parser.max_cycles: ...`); elsewhere it counts them (`JSON ok · 2 warnings`).

![setup.json in the editor: the entries divide leaves out are marked, and the status line says why](images/div-setup-json.png)

## What it sets

```json
{
  "engine": "vendor/autoload.php",
  "paths": {"packages": "templates", "repository": "templates", "include": ["shared"]},
  "files": {"template_ext": "tpl", "data_ext": "json"},
  "parser": {"max_cycles": 100, "max_filename": 250, "error_reporting": "E_ALL & ~E_NOTICE"},
  "dialect": "erb.dialect",
  "data": {"globals": {"site": "Shop"},
           "defaults": [{"search": null, "replace": "-"}],
           "defaults_by_var": [{"var": "price", "search": "0", "replace": "free"}],
           "system_vars": ["server", "session"]},
  "php": {"allowed_functions": ["array_sum"], "modifiers": {"rev:": "strrev"}},
  "request": {"get": {"page": 1}, "server": {"HTTP_HOST": "shop.test"}, "session": {"user": "rafa"}}
}
```

| Setting | What Div gets |
|---|---|
| `engine` | the Div to use (`autoload.php` or `div.php`). Order: `DIVIDE_DIV_PHP`, the project's setup, yours, **Options > Div engine**, the project's `vendor/`. |
| `paths.packages`, `paths.repository` | `PACKAGES` and `DIV_REPO`: where Div looks for templates and includes |
| `paths.include` | `div::addIncludePath()` for each folder |
| `files.template_ext`, `files.data_ext` | `DIV_DEFAULT_TPL_FILE_EXT`, `DIV_DEFAULT_DATA_FILE_EXT`. divide follows them: files with the template extension are Div templates (`.html` templates too), `{% ` completes them without it, and a template's data file is `page.<data_ext>`. |
| `parser.max_cycles`, `parser.max_filename` | `DIV_MAX_PARSE_CYCLES`, `DIV_MAX_FILENAME_SIZE` |
| `parser.error_reporting` | `div::setErrorReporting()`: a number or PHP's levels (`E_ALL & ~E_NOTICE`). The PHP notices of formulas it leaves out stay out of the Messages window too. |
| `dialect` | the project's dialect: a `.dialect` file, or the `DIV_TAG_*` tags themselves |
| `data.globals` | `div::setGlobal()`: variables every template gets (a template's own data wins). `{$` completes them. |
| `data.defaults`, `data.defaults_by_var` | `div::setDefault()`, `div::setDefaultByVar()`: a value shown in place of another |
| `data.system_vars` | `div::enableSystemVar()`: `div.ascii`, `div.server`, `div.session`, `div.script_name` (Div always turns on `div.now`, `div.get`, `div.post`, `div.version`, `div.level`) |
| `php.allowed_functions` | `div::setAllowedFunction()`: PHP functions templates may call in formulas and conditions |
| `php.modifiers` | `div::addCustomModifier()`: `{rev:name}` passes the value through the PHP function |
| `request` | the request templates see: `get`, `post`, `server` (added to PHP's), `session`, `cookie` fill `$_GET`, `$_POST`, `$_SERVER`, `$_SESSION`, `$_COOKIE` before Div runs, for `div.get`, `div.post`, `div.server`... |

Div's defaults match Div's own JSON: a number in a data file comes out of `jsonDecode()` as a float, and Div compares defaults with `serialize()`, so `"search": 0` never matches a `0` read from a data file. Search for the text `"0"`, or for `null`.

## The project's dialect

With a `dialect`, it is the language of the project:

- a template without `@_DIALECT` is written in it (divide colours, checks and completes it so);
- a dialect file's missing tags are the project's dialect's, as Div fills them with its current tags. The [[Dialector]] and [[Translating Templates|Translating Templates]] use it as their base; their local menu and the translation dialog can switch to Div's default dialect instead.

Div judges the dialect before anything else. One it rejects is left out, with Div's reason in the Messages window: Div would stop on every render otherwise.

## Trust

`php` lets templates call PHP. A setup that came with a project (a clone, say) could make `system` callable, so the project's `php` settings wait until you trust them: divide asks once when it finds them, and **Options > Div setup**, Alt+F10, **Trust the project's PHP settings** asks again. Your answer is kept in `~/.div/trust.json` with a fingerprint of those settings: when they change, divide asks again. Your own `~/.div/setup.json` is always trusted.

Until then the rest of the setup applies, and the Messages window says what waits.

![the question when a project's setup lets templates call PHP](images/div-setup-trust.png)

## What cannot be set here

Hooks (`beforeBuild`, `afterParse`...), subclasses of `div`, closures and sub-parsers are PHP code. divide does not run your application's code to design its templates, so they are not part of the setup. The `Custom PHP code` section of the window says so.

## The window

**Options > Div setup...** opens the project's setup (a new `.div/setup.json` when there is none: **F2** creates it).

- **Left: the sections.** Engine and paths, File extensions, Parser, Dialect, Data, PHP functions, Simulated request, Custom PHP code. Each row says how many settings this file has (`2/4`) and carries a mark: `•` set, `!` something in it is left out.
- **Right: what is in effect** for the section: each setting, its value, and where it comes from (`project`, `user`, `project + user`, or `Div`).
- **Below the sections:** what the section is about; what divide leaves out of the file as it is now; and Div's verdict on the saved setup: whether the dialect is valid, how many include paths it has, the PHP functions it cannot find.

| Key | |
|---|---|
| **Enter** / double click | edit the section in a dialog: paths with **...** (Browse), lists separated by `;` or `,`, JSON values (checked before they are taken), system variables as check boxes |
| **Del** | the section back to Div's defaults in this file |
| **F2** | save the setup file (Div sees the saved file) |
| **Ctrl+Z / Ctrl+Y** | undo / redo |
| **Ctrl+T** | the file as JSON |
| **Alt+F10** / **Shift+F10** | local menu: the user's or the project's setup, edit as JSON, the dialect in the Dialector, trust the project's PHP settings, check with Div |

![editing the Data section: globals as JSON, system variables as check boxes](images/div-setup-dialog.png)

![the local menu (Alt+F10)](images/div-setup-menu.png)

Like the Dialector, the window is a view of the file: every change is one edit of its buffer. Before the first change, if the file has comments, the window asks before rewriting it as standard JSON.
