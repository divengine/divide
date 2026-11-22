# divide

**An IDE for developing generators with the Divengine ecosystem.**

divide is a specialised development environment for building, testing, debugging and maintaining generators that use the [Divengine](https://github.com/divengine) libraries. A generator is a project of its own that transforms input models into source code, configuration, templates or other artifacts through explicit, reusable rules, for example with [Div](https://github.com/divengine/div) templates and their data. You develop it in divide; the finished generator is deployed and runs without divide.

You could write the same software in any editor. What divide adds is knowledge of the ecosystem: Div-aware editing in each template's dialect, the project's design-time Div setup, rendering and checking through the real engine, and the render trace of how Div reached its output. Deterministic code generation is a central use case: see [[Generators and what is not decided|Home#generators-and-what-is-not-decided]].

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

## Generators and what is not decided

divide is the IDE, not the generator, and not where generators run in production. A generator project may use Div, Nodes, Ways, PHP or anything else it needs, and may implement its own orchestration of stages, CLI commands, an HTTP API or an MCP server; tools and AI coding agents then use the deployed generator through those interfaces. divide's [[Web Server]] can help while you develop an HTTP generator, but it is not a generator API or an MCP platform. divide's own [[MCP Server]] (Options > MCP server) is for developing: it lets an AI coding agent check, render and trace the project's templates through divide.

**Not decided yet**: what a generator is as a unit, and which responsibilities around orchestration and generator interfaces belong in divide (tools to develop, inspect, debug or test them) and which in generator projects. **Div is integrated in divide**, and the Flows of [Runner](https://github.com/divengine/runner) run through Runner's own command line ([[Running Flows]]), and their Blocks and Steps are edited in the [[Flow window|Flow Structure]] and drawn and designed in the [[Flow Designer]]; [Nodes](https://github.com/divengine/nodes) and [Ways](https://github.com/divengine/ways) are independent PHP libraries that a generator may use, with their role in generator development still to be decided.

divide is meant to complement AI coding agents such as Claude Code, Codex or OpenCode, not to be one: an agent should not have to write large amounts of predictable code that a validated generator can produce.

Generation with Div is reproducible when its inputs and conditions are controlled: the same template and data give the same output only if everything else that takes effect is controlled too (Div can also read the time, the request, random values and the PHP functions it may call). And reproducible output is not necessarily right: that depends on the generator's rules, models and checks.

## Start here

1. [[Installation]]: Python, PHP and Div.
2. [[Getting Started]]: a five-minute tour.
   New to Div? Its language is described in [Div's documentation](https://github.com/divengine/div/tree/master/docs), which is also inside divide: see [[Help]].
3. Then the chapters: [[The Desktop]], [[Editing Templates]], [[Editing PHP]], [[Outline]], [[Finding Files and Commands]], [[Language Servers]], [[Completion]], [[Checking Templates]], [[Rendering]], [[Render Trace]], [[Running PHP]], [[Debugging PHP]], [[Web Server]], [[Data Files]], [[Other Files]], [[Project Window]], [[Dialector]], [[Translating Templates]], [[Div Setup]], [[Composer]], [[Git]].
4. [[Keyboard Reference]] and [[Troubleshooting]] when you need them.

The whole manual is also inside divide: press **F1** (see [[Help]]).

divide is part of [Divengine](https://github.com/divengine). Source code: [divengine/divide](https://github.com/divengine/divide).
