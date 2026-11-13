# Data Files

`.json` files (and `.dialect` files) are **Div JSON**: everything Div's `jsonDecode()` accepts. That is JSON plus:

- references as values: `"author": $site.owner`;
- single quotes, unquoted keys, trailing commas;
- comments.

## As code

The editor highlights keys, strings, numbers, constants and references, and validates as you type: an error is painted in place and the status line says `JSON [!] line 6, col 47: unexpected 'r', expected a value`. When everything is fine it says `JSON ok`, and how many references the file uses.

![a JSON error while typing](images/data-code.png)

## As a tree

**Ctrl+T** turns the same buffer into a tree. From a template, Ctrl+T opens the tree of its data file (creating `page.json` if it does not exist yet). Ctrl+T again goes back to the code.

![the data tree](images/data-tree.png)

| Key | |
|---|---|
| **Enter** | edit the item: key, type, value |
| **Ins** | add an item: inside an object or array, or after a plain value |
| **Del** | delete the item |
| **Ctrl+↑ / Ctrl+↓** | move the item up / down |
| **Ctrl+Z / Ctrl+Y** | undo / redo (through the code editor's history) |
| **F2** | save |

The edit dialog lets you change the type as well as the value: String, Number, True, False, Null, Reference, Object, Array.

![editing an item](images/data-tree-edit.png)

The tree and the code are one buffer: typing in the code rebuilds the tree (while the JSON is broken, the last good tree stays and editing is refused until it is fixed), and every tree edit rewrites the code as standard JSON, keeping references bare. If the file uses comments, single quotes or unquoted keys, which a rewrite would drop, divide asks first.
