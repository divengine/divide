# Other Files

A PHP project is more than templates and PHP: a README, stylesheets, scripts for the browser, the configuration of PHPUnit or of the framework, a `php.ini`, a CSV with the data to import. divide opens all of them in the same editor, with their colours, so you do not have to leave it to look at one.

![README.md, phpunit.xml.dist, php.ini and a CSV, tiled](images/other-files.png)

| Language | Files |
|---|---|
| HTML | `.html`, `.htm` |
| CSS | `.css` |
| JavaScript | `.js`, `.mjs`, `.cjs`, `.jsx` |
| Markdown | `.md`, `.markdown` |
| SQL | `.sql` |
| XML | `.xml`, `.xsd`, `.xsl`, `.xslt`, `.svg`, `.xhtml`, `.xliff`, `.xlf`, and the `.xml.dist` files (`phpunit.xml.dist`, `phpcs.xml.dist`) |
| YAML | `.yml`, `.yaml`, `.neon`, and the `.yml.dist` / `.yaml.dist` files |
| TOML | `.toml` |
| Shell | `.sh`, `.bash`, `.bashrc`, `.profile`, and `.env` with its variants (`.env.local`, `.env.test`…) |
| INI | `.ini`, `.cfg`, `.conf`, `.editorconfig`, `.ini.dist` |
| CSV | `.csv`, `.tsv` |

The status line names the language of the file you are in. A file divide does not know (`.txt`, `.log`…) opens as plain text.

## How they are coloured

The first nine are read with [tree-sitter](https://tree-sitter.github.io/) grammars, the same way as PHP (see [[Editing PHP]]): the colours follow the structure of the file, not guesses with patterns. A grammar is loaded the first time a file of its language opens.

The colours come from the theme in **Options > Colors**: strings, numbers, keywords, comments, tags and names take the same colours as in templates and in PHP, in every theme (see [[The Desktop#colours]]).

**INI**: `[sections]`, the keys, their values (quoted strings, numbers such as `128M`, and `On` / `Off` / `true` / `false`), and the comments, whole lines or after a value (`;` or `#`).

**CSV**: each column has a colour of its own, six in turn, so a column can be followed down the file. A quoted field may hold the separator (`"Potato, red"`) and stays one field. The separator is taken from the first line: comma, semicolon, tab or `|`; `.tsv` files use tabs.

## What divide does not do with them

They are coloured, not checked: divide lists errors only for templates, Div JSON and PHP (see [[Checking Templates]]). Completion, the outline and the language servers are for templates and PHP too.
