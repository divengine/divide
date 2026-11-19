# divide

**Deterministic code generation and orchestration environment.**

divide is a terminal-based engineering environment for developing and operating deterministic code generators built with the [Divengine](https://github.com/divengine) ecosystem. A generator transforms input models into output artifacts through explicit, reusable generation rules: for example, [Div](https://github.com/divengine/div) templates and their data producing source code in any language, configuration, tests, infrastructure definitions, HTML, or other templates. The aim is reproducible generation: explicit models, controlled execution conditions and reusable rules.

Today divide gives you the tools to build generators: editing, checking, rendering, tracing and debugging, all through the real Div engine. Orchestrating generators and letting AI coding agents use them are the direction of the product, not features yet: see [[Where divide is going|Home#where-divide-is-going]].

It is built in the spirit of the Borland IDEs: a desktop of overlapping windows, drop-down menus, dialogs with shadows, a status line that always tells you the next key. The name is *div* + *ide*, and the English word *divide*.

![divide: project, template and rendered output side by side](images/hero.png)

## What you can do today

The manual's examples generate HTML, the easiest output to read; the same tools work for templates that generate code or any other text.


- **It speaks Div.** Every tag of the language is highlighted, in your template's own dialect (`@_DIALECT`), not a generic HTML mode with braces.
- **Errors before you render.** Unclosed loops, orphan `[/$x]`, conditions without `{/?}`, broken JSON in `{= x: … =}`, includes Div cannot resolve: painted in the editor and listed in a Turbo Pascal–style Messages window.
- **Completion from your data.** Type `{$` and pick from the keys of `page.json`; inside `[$products]` you get the fields of a product, the item name and Div's `_index`, `_is_last`… Type `[$` and the loop is closed for you.
- **The real engine, not an imitation.** Ctrl+F9 renders through PHP and Div with your unsaved edits; includes are resolved by Div's own `getTplPath()`; data is decoded by Div's own `jsonDecode()`.
- **Data as code or as a tree.** Div JSON (references, comments, single quotes) is highlighted and validated; Ctrl+T turns the same buffer into a tree you can edit with dialogs.
- **Your own dialects, with an assistant.** The [[Dialector]] builds a Div dialect section by section, with a live preview and Div's verdict on every change. A wizard translates templates from one dialect to another with Div's own translator.
- **PHP next to the templates.** `.php` files are highlighted with tree-sitter's PHP grammar and checked by PHP itself (`php -l`) as you type; Ctrl+Enter on `new div('page.tpl')` opens the template. With phpactor or intelephense, completion, definitions and their warnings too: see [[Editing PHP]] and [[Language Servers]].
- **Run and debug PHP, the Turbo Pascal way.** Ctrl+F9 runs the script under a progress box and lists PHP's errors with their place; F7 / F8 step through it with Xdebug, with breakpoints, watches and the call stack: see [[Running PHP]] and [[Debugging PHP]]. Run > Web server serves the project with `php -S` and debugs its requests the same way: see [[Web Server]].
- **See how Div got there.** Debug > Render trace replays every mutation Div made to a template, in Div's own words, with what each one wrote and took away, up to the fixed point: see [[Render Trace]].
- **The rest of the project too.** HTML, CSS, JavaScript, Markdown, SQL, XML, YAML, TOML, shell scripts, `.env`, `php.ini` and CSV files open with their colours: see [[Other Files]].
- **Div set up for design time.** The project's `.div/setup.json` gives the Div that divide runs its folders, dialect, global data and allowed functions while you work. It does not configure the Div your application runs in production: see [[Div Setup]].
- **Version control and packages.** The Git menu shows changes, diffs, history, branches and blame, and the pull requests of GitHub or Gitea: see [[Git]]. Tools > Composer packages manages the project's PHP packages: see [[Composer]].
- **A project window that does things.** Create, rename, move and delete files and folders without leaving the IDE.
- **Runs anywhere there is a terminal**: over SSH, inside tmux, on the server where the templates live. In English or in Spanish (Options > Language).

## Where divide is going

These are directions, **not features of divide today**:

- **Orchestration.** Generating a real system takes several stages: outputs that feed later stages, intermediate representations, dependencies, validation between steps. divide is meant to compose and run generators that way. Its model has not been designed yet.
- **AI coding agents.** divide is meant to work alongside agents such as Claude Code, Codex or OpenCode, not to be one. Instead of an agent writing large amounts of predictable code, it would call a validated generator, through a CLI, API or MCP interface that is still to be designed.

divide is not a general-purpose IDE, and PHP is the language the Divengine components are written in, not a limit on what they generate. Only Div is integrated in divide; the other Divengine libraries, such as [Nodes](https://github.com/divengine/nodes) and [Ways](https://github.com/divengine/ways), are independent PHP libraries with no role in divide decided. The same template and data give the same output only when every other input is controlled too (Div can also read the time, the request, random values and the PHP functions it may call), and reproducible output is not necessarily right: that depends on the generator's rules, models and checks.

## Start here

1. [[Installation]]: Python, PHP and Div.
2. [[Getting Started]]: a five-minute tour.
   New to Div? Its language is described in [Div's documentation](https://github.com/divengine/div/tree/master/docs), which is also inside divide: see [[Help]].
3. Then the chapters: [[The Desktop]], [[Editing Templates]], [[Editing PHP]], [[Outline]], [[Finding Files and Commands]], [[Language Servers]], [[Completion]], [[Checking Templates]], [[Rendering]], [[Render Trace]], [[Running PHP]], [[Debugging PHP]], [[Web Server]], [[Data Files]], [[Other Files]], [[Project Window]], [[Dialector]], [[Translating Templates]], [[Div Setup]], [[Composer]], [[Git]].
4. [[Keyboard Reference]] and [[Troubleshooting]] when you need them.

The whole manual is also inside divide: press **F1** (see [[Help]]).

divide is part of [Divengine](https://github.com/divengine). Source code: [divengine/divide](https://github.com/divengine/divide).
