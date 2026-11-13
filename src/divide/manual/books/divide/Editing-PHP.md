# Editing PHP

Files ending in `.php` (and `.phtml`) open in a PHP editor: the code that calls Div sits next to the templates, in the same desktop.

![a PHP file with a syntax error found by PHP](images/php.png)

## Highlighting

The colours come from [tree-sitter](https://tree-sitter.github.io/)'s PHP grammar, the same one many editors use. In the Borland palette, reserved words are white, variables light cyan like Div's, strings light green, comments light gray, and the `<?php` tags light red. HTML outside the PHP tags is left plain.

## Errors from PHP itself

divide does not judge PHP code: PHP does. When you stop typing for a moment, divide passes the buffer (saved or not) to `php -l`, PHP's own syntax check, and shows its answer:

- the line PHP points at is painted red;
- the status line gives PHP's message;
- **Alt+F9** lists it in the Messages window, **Enter** jumps to it, **Alt+F8** / **Alt+F7** walk the errors, as with templates (see [[Checking Templates]]).

PHP stops at the first syntax error, so there is one at a time. `php` must be in the `PATH`; without it the status line says the file is not checked.

## Opening the file a string names

Put the cursor on a string that names a file and press **Ctrl+Enter** (or Ctrl+click): `new div('index.tpl', $data)` opens the template, `require 'menu.php'` opens `menu.php`. divide looks next to the PHP file, then in the project folder, and tries the name with `.tpl` too.

## What is not there yet

Completion of PHP (classes, functions, methods) and checks beyond syntax will come later.

Everything else is the same editor as for templates: find and replace, the editing keys, undo (see [[Editing Templates]]).
