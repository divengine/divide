# Outline

**Search > Outline** (**Ctrl+O**) opens a window at the right of the desktop with the declarations of the active PHP file, to see how the file is made and to jump to any part of it.

![the outline of Div's own class, on parseMatches](images/outline.png)

## What it lists

- namespaces, classes (with what they extend), interfaces, traits and enums;
- below each, indented: its constants, enum cases, properties and methods, with UML's marks for their visibility: **+** public, **#** protected, **-** private;
- the functions and constants of the file, also those inside `if (!function_exists(...)) { }`.

Functions and methods show their parameters and return type, as written: `add(string $name, int $qty = 1): self`. Closures and anonymous classes are left out.

The declarations come from [tree-sitter](https://tree-sitter.github.io/)'s PHP grammar, the one that colours the editor (see [[Editing PHP]]), so the outline needs no language server and works while the file has errors.

## Keys

| Key | Action |
|---|---|
| **↑ / ↓**, PgUp / PgDn | move the bar |
| **Enter** / double click | go to the declaration: the editor comes to the front with its name selected |
| **Ctrl+O** | back to the outline from the editor |

The outline follows you: it changes when another PHP editor comes to the front, and it is redone a moment after you stop typing. In a template it keeps the PHP file it was showing; opened from a template alone, it says the outline is for PHP files.
