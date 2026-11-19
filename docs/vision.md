# Vision

## 1. Introduction

**divide: an IDE for developing generators with the Divengine ecosystem.**

divide is a specialised development environment for building, testing,
debugging and maintaining generators that use the
[Divengine](https://github.com/divengine) ecosystem. It knows the
ecosystem's libraries, APIs, syntax, configuration, behaviour and
conventions, and gives tools made for them: today, mainly for
[Div](https://github.com/divengine/div).

The name joins *div* and *ide*, and keeps the meaning of the English word
*divide*. It is always written in lowercase.

The interface follows the Borland IDEs (Turbo Pascal, Turbo C, Borland
Pascal): overlapping windows, drop-down menus, dialogs with shadows and a
status line that always shows the next key. It runs in any terminal,
including over SSH.

### 1.1 Why a dedicated IDE

Generators can be written in any editor, and VS Code, JetBrains IDEs or
Neovim are perfectly able to edit the same files. divide does not compete
with them on general programming. Its value is domain knowledge: first-class
tools for the Divengine ecosystem, designed around how generators are
actually developed. Examples in the current code:

- templates highlighted and checked in their own Div dialect, with
  completion from the data they will be rendered with;
- rendering through the real Div engine, with the project's design-time Div
  setup, and the render trace of every mutation Div made up to the fixed
  point;
- dialects built and validated by Div itself, and templates translated
  between dialects with Div's own translator.

New capabilities should serve generator development. General-purpose IDE
features are not added for their own sake; the ones divide has (git,
Composer, PHP support, the debugger, file management) are there because
generator projects need them.

### 1.2 What divide is not

- It is not a general-purpose IDE.
- It is not only an editor for website templates. HTML is one possible
  output among many.
- It is not mainly an IDE for PHP applications. PHP is the language the
  Divengine libraries are written in, not a limit on what generators produce.
- It is not the generator, and it is not where generators run in production
  (section 2).
- It is not an AI coding agent, and it does not replace one.

## 2. The IDE, the generator and its deployment

Three separate things:

| | What it is | Where it lives |
|---|---|---|
| **divide** | The development environment: where a generator project is designed, written, configured, tested, inspected and debugged | the developer's terminal |
| **A generator** | An independent software project. It transforms input models into source code, configuration, templates or other artifacts through explicit, reusable rules, and may use Div, Nodes, Ways, PHP and whatever else it needs. It may implement its own orchestration of stages, CLI commands, an HTTP API or an MCP server: those are capabilities of the generator project, not services of divide | its own repository |
| **Deployment** | The finished generator installed and run on another machine, a server, a container or any infrastructure, and used there by people, tools or AI coding agents through the interfaces the generator itself implements | wherever it is deployed |

A deployed generator does not depend on divide being installed or running.
An optional integration between them may be designed one day; none exists
or is decided today. Developing a generator and operating it in production
are different activities, and divide is for the first.

What a generator is as a unit (a template, a folder, a Composer package, a
workflow, a class or something else) has not been decided. It belongs to an
abstraction model that the product owner has not specified yet, so no
generator schema, workflow language, pipeline format or execution
architecture is defined here.

## 3. Generation with Div

Deterministic code generation is a central motivation for divide, and Div is
the engine divide supports today. It is one way of generating, not the whole
of divide's identity.

Div takes a template and a data model and produces text. That text can be
source code in any language (Python, PHP, JavaScript, TypeScript, React
components, Odoo or Drupal modules), configuration, tests, infrastructure
definitions or another template, by explicit and reusable rules. What makes
it suitable for generation, as its implementation and documentation describe
it:

- **Iteration to a fixed point.** Div does not process a template in a single
  top-down pass. It parses and transforms the whole template again and again,
  until a cycle changes nothing or a limit is reached. A template can
  therefore produce structures that later cycles evaluate: meta-templates and
  templates that write templates.
- **Output as input.** The output is plain text, so it can become another
  template, a data model (such as JSON) or part of a composed result. Div's
  documentation names three core operations, *compile*, *transform* and
  *compose*, that combine into multi-stage generation.
- **Dialects.** A dialect is a JSON file that maps another tag syntax onto
  Div's own. A template names its dialect (`@_DIALECT`), and Div translates it
  before parsing. This keeps the generator's syntax apart from the syntax of
  the code being generated (braces in JavaScript, `<% %>` in a target
  language, XML that must stay valid), which matters more when the outputs
  are themselves templates at another level.
- **Reuse.** Includes and preprocessed includes, template inheritance,
  locations, macros, custom modifiers, sub-parsers and hooks, global data and
  default replacements.

Determinism has conditions. A template and its data give the same output
only when every input that takes effect is controlled: Div can also read the
time (`div.now`), the request (`div.get`, `div.post`, `div.server`,
`div.session`), random values (`rand`, `mt_rand`, `uniqid` and random list
order) and whatever the PHP functions it is allowed to call return, besides
the files it includes. Reproducible generation comes from explicit models,
controlled execution conditions and reusable rules.

Reproducible output is not correct output by itself either: a generator is
correct only as far as its rules, its models and the checks around it are.
That is why divide puts checking, tracing and testing next to editing.

## 4. Positioning

### 4.1 The problem

| | |
|---|---|
| **The problem of** | developing generators with the Divengine libraries: templates and data models that produce other software, in a syntax that must not collide with the code it produces, and the PHP around them |
| **affects** | developers who build and maintain generators, Div's maintainers, and teams that rely on generated code |
| **the impact of which is** | in general-purpose editors, Div's constructs are plain text: errors show only at render time or silently stay in the output, the data a template sees is invisible, and the engine's fixed-point rewriting cannot be followed |
| **a successful solution would** | understand generator projects the way the Divengine libraries run them: check templates in their own dialect, complete from the real data, render and trace through the real engine, and debug the PHP around them, in one place |

### 4.2 Product position statement

For developers who build generators with the Divengine ecosystem, divide is
an IDE that works through the libraries themselves: Div renders, validates
dialects, resolves includes, decodes data and translates templates. Unlike a
general editor with a syntax file, it reads each template's dialect, checks
what Div would trip over, completes from the data, and shows how Div turned
the template into its output, step by step.

## 5. The Divengine ecosystem

The Divengine libraries are independent PHP packages, each usable on its own.
**Only Div is integrated directly with divide.**

| Component | What it does | In divide today |
|---|---|---|
| [Div](https://github.com/divengine/div) | Template processing and transformations: data and templates to text, iterated to a fixed point, with dialects, includes, translation between dialects | Integrated through a PHP bridge: render, include resolution, data decoding, dialect checks and loading, render trace, translation, the Div setup of a project |
| [Nodes](https://github.com/divengine/nodes) | File-based structured data management without a server: schemas, nodes and references between them, indexes for search, file locking | Not integrated |
| [Ways](https://github.com/divengine/ways) | Execution control points ("ways") called from HTTP, the CLI or PHP code: routing, hooks and rules | Not integrated |

Nodes and Ways are being considered for future generator-development use
cases; their roles are not decided. A generator project may use them for its
own needs (Ways to expose HTTP operations, Nodes to manage its data) without
divide integrating them, and that a generator uses a library does not make
the library a subsystem of divide. None of these libraries was made only for
code generation.

## 6. Stakeholders and users

| Stakeholder | Role | Interest |
|---|---|---|
| Div's author and maintainer | product owner, main user | an IDE that respects Div's semantics; Div stays the source of truth, and is not changed merely to suit the IDE |
| Generator developers | users | design, write, configure, check, render, trace, test and debug generator projects, quickly and from the keyboard |
| Teams using generated code | consumers of generators | generators that are versioned, reviewed and tested like any other code |
| AI coding agents and their users | consumers of generators | use deployed generators through the interfaces those generators implement |
| Plug-in authors | extenders | add a language or a help book without touching the core |

User environment: terminals on Linux, macOS and Windows, often through SSH
and tmux, with fonts the user does not control. That is why divide keeps to
ASCII and CP437 glyphs and why it works with 16 colours as well as truecolour.

## 7. Implemented capabilities

Everything in this table exists in the current code.

| Need of a generator developer | Feature |
|---|---|
| See a template's structure | dialect-aware lexer and highlighting (`@_DIALECT`), Div JSON highlighting, outline of templates and of every other language divide colours |
| Catch errors before generating | static checks (unclosed blocks, orphan closers, broken JSON in definitions, unresolvable includes), Messages window, Alt+F8 / Alt+F7 |
| Write templates against their data | completion of variables from the data file, loop item fields, includes, Div snippets |
| Run the real engine | render through PHP and Div (unsaved edits included) into the Output window, a data file per template, the data as code or as a tree |
| Understand a generation | render trace: Div's mutations one by one up to the fixed point |
| Keep generator syntax apart from target syntax | Dialector (build, validate with Div, import, export); translation of templates between dialects with Div's `translate()` |
| Set up the Div that divide runs while you design | Options > Div setup (`.div/setup.json`): engine, paths, extensions, parser limits, dialect, global data, allowed PHP functions and modifiers, simulated request data. This is divide's design-time configuration: it does not configure the Div an application or a deployed generator runs, which keeps its own setup in its own code |
| The PHP of a generator project | PHP highlighting and `php -l`, language servers, running scripts with arguments, the Xdebug debugger, Composer packages |
| Try HTTP code while developing | a built-in PHP development server (`php -S`) with per-request debugging. It can help develop and test a generator that serves HTTP; it is not a generator API or an MCP platform |
| The files a generator produces | highlighting and outline of HTML, CSS, JavaScript, Markdown, SQL, XML, YAML, TOML, shell scripts and `.env`, INI and CSV |
| Version and review generators | the Git menu: changes, diffs as a code review shows them, commits, history, branches, merges, stashes, blame, pull and push; pull requests and issues of GitHub and Gitea |
| Find your way | project window, Go to file, command palette, Find / Replace, Find in files, Go to included template; a folder only when given, the Welcome window with recent folders and files |
| Learn in place | help books (divide's manual, Div's documentation) in English and Spanish, context help on F1, full-text search |
| Comfortable for hours | colour themes (Turbo Pascal, Turbo C, Free Pascal, modern dark), drop shadows, input line histories |

Inside divide, Div renders one template with its data at a time, into a
window. A generator project can chain renders, write files or run stages in
its own code; divide has no tool of its own for that yet.

## 8. Constraints

- divide uses the Divengine libraries through their existing public APIs and keeps their responsibilities apart from its own. A library is not changed merely to accommodate the IDE; any change to one is an explicit technical decision, taken in that library's project. Bugs found while building divide are reported upstream.
- What Div decides (rendering, include resolution, data decoding, dialect validation, translation) is asked of Div through PHP, never reimplemented in Python.
- Existing tools are reused before new ones are written: tree-sitter, `php -l`, Xdebug, `php -S`, language servers, git, `gh` and `tea`, Composer.
- The user manual documents divide only. It links to Div's documentation instead of copying it.
- divide's own glyphs stay ASCII or CP437 and fixed width, with no Nerd Fonts and no wide or emoji characters.
- Undecided directions are described as undecided. The documentation does not present a direction as a feature, or one architectural option as chosen.

## 9. Open questions (not decided)

### 9.1 Orchestration

A single generation is data + template → output. A real generator may need
more: several stages, outputs that feed later stages, intermediate
representations, dependencies, validation between steps, related artifacts
produced together. That orchestration may be implemented by generator
projects themselves; divide may give tools to develop, inspect, debug or test
it. Which responsibilities belong in the IDE and which in generator projects
has **not been decided**, and the abstraction model behind it has not been
specified. No execution graph, pipeline format, workflow language or project
schema exists in divide, and this document does not define one.

### 9.2 CLI, API and MCP

A generator may expose a CLI, an HTTP API or an MCP server, implemented in
the generator project. divide may one day offer tools to develop and test
such interfaces; it does not expose a generation API or an MCP server today,
and whether it ever will is not decided. Its command line opens the IDE.

### 9.3 AI coding agents

divide is meant to complement AI coding agents (Claude Code, Codex, OpenCode
and others), not to be one. An agent should not have to write large amounts
of predictable, repetitive code when a validated generator can produce it:
the agent can interpret requirements, build models, choose generators or help
develop new ones in divide, and use deployed generators through the
interfaces they implement. Less repeated output, fewer tokens and less
variation between runs are motivations, not measured results, and a
generator's output is not correct merely because it is reproducible.

## 10. Scope and quality ranges

In scope: a single-user IDE in the terminal for developing generators with
the Divengine ecosystem, one project folder at a time (or files on their
own), git through the system's own `git`. Out of scope: running generators in
production. Undecided: the questions of section 9. Out of scope for now:
multi-root workspaces, collaborative editing, a plug-in marketplace.

Quality ranges are detailed in the [supplementary specification](supplementary-specification.md):
responsiveness while typing, modest memory use, and behaviour that is the
same in every terminal.
