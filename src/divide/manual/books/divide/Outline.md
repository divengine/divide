# Outline

**Search > Outline** (**Ctrl+O**) opens a window at the right of the desktop with the shape of the active file, a Div template or a PHP file, to see how it is made and to jump to any part of it.

![the outline of the shop's home page, on the products loop](images/outline_tpl.png)

## In a template

A template has no declarations: Div rewrites it until nothing changes. Its outline is the structure the editor sees, the constructs Div would recognise, each one shown by its opening tag as it is written:

- template variables and properties: `{= year: 2026 =}`, `@_DIALECT = erb.dialect`;
- includes: `{% layout/header %}`, `{%% components/card %%}`;
- the blocks, with what they hold indented below them: lists `[$products] product =>`, iterations `[:1,10:]`, conditions `{?( {$cart.items} > 0 )?}`, conditional parts `?$logged` / `!$logged`, capsules `[[product`, locations and their content `(( side ))` / `{{side`, sub-parsers, multiple replacements, ignored parts and macros.

Replacements (`{$name}`) and formulas are left out: they are the text of the template, not its shape. The tags are found with Div's own rules, the ones that colour the editor (see [[Editing Templates]]), and with the template's dialect: a template in another dialect shows its own tags. Long tags are cut with `...`.

## In a PHP file

![the outline of Div's own class, on parseMatches](images/outline.png)

- namespaces, classes (with what they extend), interfaces, traits and enums;
- below each, indented: its constants, enum cases, properties and methods, with UML's marks for their visibility: **+** public, **#** protected, **-** private;
- the functions and constants of the file, also those inside `if (!function_exists(...)) { }`.

Functions and methods show their parameters and return type, as written: `add(string $name, int $qty = 1): self`. Closures and anonymous classes are left out.

The declarations come from [tree-sitter](https://tree-sitter.github.io/)'s PHP grammar, the one that colours the editor (see [[Editing PHP]]), so the outline needs no language server and works while the file has errors.

## Keys

| Key | Action |
|---|---|
| **↑ / ↓**, PgUp / PgDn | move the bar |
| **Enter** / double click | go there: the editor comes to the front with the tag or the declaration's name selected |
| **Ctrl+O** | back to the outline from the editor |

The outline follows you: it changes when another template or PHP editor comes to the front, and it is redone a moment after you stop typing. In any other file it keeps the one it was showing; opened from other files alone, it says the outline is for PHP files and Div templates.
