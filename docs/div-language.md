# Div as seen by the editor

Reference: `src/div.php` of divengine/div 6.x (the `define()` block is the
source of truth for tags) and its `docs/` wiki.

## How the lexer mirrors the engine

- Keyed blocks (`[$x]…[/$x]`, `?$x…$x?`, `!$x…$x!`, `[[x…x]]`, `{{x…x}}`,
  `{:x}…{:/x}`, `{name}…{/name}`) are only recognised when the closing tag
  exists, with balanced nesting (as `getRanges`). An unclosed or orphan list
  tag is shown as an error.
- When a begin suffix is empty (`?$`, `[[`, `{{`) the key is the longest
  prefix that has a matching close: `?$showYES@else@NO$show?` → key `show`.
- Code containers are lexed recursively: `{= =}` / `{@ @}` as JSON-ish values,
  `{?( )?}`, `(# #)`, `<? ?>` as PHP expressions, `{% %}`/`{%% %%}` as paths,
  `[: :]` as iteration params. Replacements nested inside are highlighted.
- Text between tags is lexed as light HTML; tag/attribute-string state
  survives across Div tags.
- `@_DIALECT = file` is resolved relative to the template folder, then the
  project root, then cwd (the engine uses cwd only).

## Docs vs. source discrepancies found (worth fixing in the wiki)

- Tag table in 02.37 vs `div.php`: `DIV_TAG_INCLUDE_BEGIN` is `'{% '` and
  `INCLUDE_END` `' %}'` (with spaces), likewise `{%% `/` %%}` and
  `(( `/` ))`; `COMMENT_BEGIN` is `<!--{` (no trailing space), `MACRO_BEGIN`
  is `<?`, `FRIENDLY_BEGIN` `<!--|`; `ITERATION_PARAM_SEPARATOR` is `,`
  (empty in the table).
- Not documented: `DIV_TAG_SPECIAL_REPLACE_SPACE` (`{\s}`),
  `DIV_TAG_PREPROCESSED_SEPARATOR` (`:`).
- 02.10 example opens `[$products]` and closes `[/$employees]`.
- 02.32 example output does not match its template ("Product's price: Potato").

## Known limits / next steps

- Full re-lex on every edit (~20 ms per 1k lines; ~330 ms at 17k lines).
  Incremental lexing when it matters.
- Custom modifiers and sub-parsers are guessed from syntax; a project config
  could declare them (and `div.literals`, default dialect, include roots).
- Next: diagnostics panel, outline (blocks/vars), go-to-include, completion
  of modifiers/vars, live render via `php` + div.
