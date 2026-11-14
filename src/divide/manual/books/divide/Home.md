# divide

**The Div template IDE that lives in your terminal.**

divide is a full-screen, keyboard-first IDE for [Div](https://github.com/divengine/div) templates, built in the spirit of the Borland IDEs: a desktop of overlapping windows, drop-down menus, dialogs with shadows, a status line that always tells you the next key. It understands Div the way Div does: it reads your dialect, checks your templates as you type, completes your variables from your real data, and renders through the real Div engine, side by side with the code.

![divide: project, template and rendered output side by side](images/hero.png)

## Why divide

- **It speaks Div.** Every tag of the language is highlighted, in your template's own dialect (`@_DIALECT`), not a generic HTML mode with braces.
- **Errors before you render.** Unclosed loops, orphan `[/$x]`, conditions without `{/?}`, broken JSON in `{= x: … =}`, includes Div cannot resolve: painted in the editor and listed in a Turbo Pascal–style Messages window.
- **Completion from your data.** Type `{$` and pick from the keys of `page.json`; inside `[$products]` you get the fields of a product, the item name and Div's `_index`, `_is_last`… Type `[$` and the loop is closed for you.
- **The real engine, not an imitation.** Ctrl+F9 renders through PHP and Div with your unsaved edits; includes are resolved by Div's own `getTplPath()`; data is decoded by Div's own `jsonDecode()`.
- **Data as code or as a tree.** Div JSON (references, comments, single quotes) is highlighted and validated; Ctrl+T turns the same buffer into a tree you can edit with dialogs.
- **Your own dialects, with an assistant.** The [[Dialector]] builds a Div dialect section by section, with a live preview and Div's verdict on every change. A wizard translates templates from one dialect to another with Div's own translator.
- **PHP next to the templates.** `.php` files are highlighted with tree-sitter's PHP grammar and checked by PHP itself (`php -l`) as you type; Ctrl+Enter on `new div('page.tpl')` opens the template. With phpactor or intelephense, completion, definitions and their warnings too: see [[Editing PHP]] and [[Language Servers]].
- **Run and debug PHP, the Turbo Pascal way.** Ctrl+F9 runs the script under a progress box and lists PHP's errors with their place; F7 / F8 step through it with Xdebug, with breakpoints, watches and the call stack: see [[Running PHP]] and [[Debugging PHP]].
- **A project window that does things.** Create, rename and delete files and folders without leaving the IDE.
- **Runs anywhere there is a terminal**: over SSH, inside tmux, on the server where the templates live.

## Start here

1. [[Installation]]: Python, PHP and Div.
2. [[Getting Started]]: a five-minute tour.
   New to Div? Its language is described in [Div's documentation](https://github.com/divengine/div/tree/master/docs), which is also inside divide: see [[Help]].
3. Then the chapters: [[The Desktop]], [[Editing Templates]], [[Editing PHP]], [[Language Servers]], [[Completion]], [[Checking Templates]], [[Rendering]], [[Running PHP]], [[Debugging PHP]], [[Data Files]], [[Project Window]], [[Dialector]], [[Translating Templates]].
4. [[Keyboard Reference]] and [[Troubleshooting]] when you need them.

The whole manual is also inside divide: press **F1** (see [[Help]]).

divide is part of [Divengine](https://github.com/divengine). Source code: [divengine/divide](https://github.com/divengine/divide).
