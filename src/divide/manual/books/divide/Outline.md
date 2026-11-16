# Outline

**Search > Outline** (**Ctrl+O**) opens a window at the right of the desktop with the shape of the active file as a tree, in every language divide colours (a Div template, PHP, HTML, Markdown, CSS, JavaScript, SQL, JSON, YAML...): to see how it is made, fold what you don't need and jump to any part of it.

![the outline of the shop's home page, on the products loop](images/outline_tpl.png)

## How it reads

Each row starts with a letter that says what it is, in its colour: **C** a class, **m** a method, **l** a Div list... Members of a class have UML's mark for their visibility after it: **+** public (green), **#** protected (yellow), **-** private (red). Then the name, coloured as the editor colours it: in `m + add(string $name, int $qty = 1): self` the method's name, the types and the parameters each have the colour they have in the code, in every palette of **Options > Colors**.

What holds other parts has a **►** before it: **▼** when it is unfolded, with what it holds indented below it, joined by lines.

## In a template

A template has no declarations: Div rewrites it until nothing changes. Its outline is the structure the editor sees, the constructs Div would recognise, each one shown by its opening tag as it is written:

| Letter | What |
|---|---|
| **p** | a property: `@_DIALECT = erb.dialect` |
| **v** | a template variable: `{= year: 2026 =}` |
| **i** | an include: `{% layout/header %}`, `{%% components/card %%}` |
| **l** | a list: `[$products] product =>` |
| **r** | an iteration: `[:1,10:]` |
| **?** | a condition `{?( {$cart.items} > 0 )?}`, a conditional part `?$logged` / `!$logged` |
| **c** | a capsule: `[[product` |
| **o** | a location and its content: `(( side ))` / `{{side` |
| **s**, **x**, **g**, **a** | a sub-parser, multiple replacements, an ignored part, a macro |

Blocks hold what is written inside them: the include inside a list is below the list. Replacements (`{$name}`) and formulas are left out: they are the text of the template, not its shape. The tags are found with Div's own rules, the ones that colour the editor (see [[Editing Templates]]), and with the template's dialect: a template in another dialect shows its own tags. Long tags are cut with `...`.

## In a PHP file

![the outline of Div's own class, on parseMatches](images/outline.png)

| Letter | What |
|---|---|
| **n** | a namespace: what follows `namespace X;` (or is inside `namespace X { }`) is below it |
| **C**, **I**, **T**, **E** | a class (with what it extends and implements), an interface, a trait, an enum |
| **m** | a method, with its parameters and return type as written |
| **p** | a property, with its type: `- $items: array` |
| **k** | a constant or an enum case |
| **f** | a function, also inside `if (!function_exists(...)) { }` |

Classes, interfaces, traits and enums hold their members. Closures and anonymous classes are left out.

The declarations come from [tree-sitter](https://tree-sitter.github.io/)'s PHP grammar, the one that colours the editor (see [[Editing PHP]]), so the outline needs no language server and works while the file has errors.

## In the other files

The same tree, with what each kind of file is made of. Labels keep the editor's colours here too.

| File | What the outline holds |
|---|---|
| HTML | every element (**<**), nested as written, by its tag, id and classes: `main#main.page`; scripts, links and images with their `src` or `href` |
| XML | every element (**<**), nested, with its `name`, `id` or first attribute: `testsuite name="unit"` |
| Markdown | the headings (**#**), each one holding the deeper ones below it |
| CSS | the rules (**s**) by their selectors; `@media`, `@supports` and `@keyframes` (**@**) holding their rules; `@import` |
| JavaScript | imports (**u**), classes with their methods and fields (`#private` ones marked **-**), functions, and the file's constants (**k**) and variables (**v**); a constant holding a function counts as a function |
| SQL | what the script creates: tables (**t**) with their columns and types (**c**), views (**w**), indexes (**x**), functions |
| JSON | the keys (**k**) with their values; objects (**o**) and lists (**a**, with how many items) holding theirs; the objects of a list as `[0]`, `[1]`... with their first key beside them |
| YAML, TOML | the keys the same way; TOML's tables `[owner]` (**t**) and `[[products]]` (**a**) |
| Shell scripts, `.env` | the functions and the variables set |
| INI (`php.ini`) | the sections (**[**) with their keys and values |
| CSV | the columns, by the names in the first row |

## Keys

| Key | Action |
|---|---|
| **↑ / ↓**, PgUp / PgDn | move the bar |
| **Enter** / double click | go there: the editor comes to the front with the tag or the declaration's name selected |
| **Space** | fold or unfold the part under the bar |
| **←** | fold it; on a folded part or one that holds nothing, to the part that holds it |
| **→** | unfold it; on an unfolded part, to the first thing it holds |
| click on **►** / **▼** | fold or unfold |
| **Ctrl+O** | back to the outline from the editor |

The outline follows you: it changes when another editor comes to the front, and it is redone a moment after you stop typing, keeping what you folded and the bar where it was. In a plain text file it keeps the one it was showing; opened from such files alone, it says there is no outline for that kind of file.
