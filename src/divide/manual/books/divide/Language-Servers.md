# Language Servers

A language server is a program that knows a language deeply: it reads the whole project and answers an editor's questions about the code under the cursor. divide speaks the Language Server Protocol, so the work of those tools comes into the Turbo Vision desktop. For PHP it uses [phpactor](https://phpactor.readthedocs.io) or [intelephense](https://intelephense.com).

![completion from intelephense in a PHP file](images/lsp.png)

## What it gives

| Key | |
|---|---|
| typing, or **Ctrl+Space** | completion: the server's functions, classes, methods and variables, with their types; after `->`, `::`, `$` and `\` it opens by itself; a class from another namespace brings its `use` line |
| **Ctrl+F1** | what the server knows about the word under the cursor (its signature, its documentation), in a dialog |
| **Ctrl+Enter** / Ctrl+click | the definition of the symbol under the cursor, in its file; on a string with a file name, that file (see [[Editing PHP]]) |
| | the server's errors and warnings join PHP's in the editor and in the Messages window (**Alt+F9**) |

The server is started when the first PHP file opens. A spinner turns in the status line while it starts and while it indexes the project; the status line then names the server. It is stopped when divide exits.

## Composer projects

In a project with a `composer.json` and its `vendor/` installed (`composer install`), the server reads the classes of the packages too. With Div (`composer require divengine/div`):

- `new di` offers `div (divengine)`; choosing it writes `div` and adds `use divengine\div;` at the top of the file;
- `div::` lists Div's static methods, `$tpl->` the methods of a `div` object;
- `\divengine\` lists what the namespace holds.

The first questions after the server starts may take a moment while it reads `vendor/`.

## Installing a server

You need one of them, in the project or in the `PATH`:

| Server | Install | Found at |
|---|---|---|
| phpactor | `composer require --dev phpactor/phpactor`, or the `phpactor.phar` of its releases | `vendor/bin/phpactor` of the project, `phpactor` in the `PATH` |
| intelephense | `npm install intelephense` (Node.js) | `node_modules/.bin/intelephense` of the project, `intelephense` in the `PATH` |

phpactor is written in PHP and is free software. intelephense runs on Node.js; its basic features are free, and some need a licence.

## Choosing the server

**Options > Language servers...**:

- **Automatic** (the default): the first one found, phpactor then intelephense;
- **phpactor** or **intelephense**: that one;
- **None**: no server; PHP's own syntax check stays.

The **Command** field runs the chosen server from anywhere, for example `/opt/phpactor.phar` (a `.phar` runs with `php`) or `/usr/local/bin/intelephense --stdio`. **Browse** picks the file. The dialog shows what it finds for each server. divide remembers the choice.

If the server does not start, divide says why once, and works without it.
