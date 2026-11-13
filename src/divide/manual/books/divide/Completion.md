# Completion

divide completes as you type, from what your template can actually see.

## While you type

The list opens by itself after:

| You type | You get |
|---|---|
| `{$`, `{^$`, `{html:$`… (any modifier) | variables, and the closing `}` |
| `[$` | lists to loop over (arrays first); the loop is closed for you with `[/$name]` |
| `[/$` | the loops that are open at that point |
| `?$` / `!$` | variables, and the matching `$name?` / `$name!` |
| `$` inside `{?( … )?}`, `(# … #)` or `{= … =}` | variables |
| `{% ` / `{%% ` | folders and templates (without `.tpl`, the way includes are written) |

Typing narrows the list (by prefix first, then anywhere in the name). **↑/↓**, **PgUp/PgDn** move, **Enter** or **Tab** inserts, **Esc** closes, and a click picks an item.

![variables inside a loop](images/completion-variables.png)

## Where the variables come from

In this order:

1. **The open loops**, innermost first: the item (`value`, or the name you gave it: `[$products] product => …`), its fields as `product.name` and also directly as `name`, and Div's loop variables `_index`, `_key`, `_order`, `_is_first`, `_is_last`, `_is_odd`, `_is_even`, `_list`, `_item`…
2. **The data file** of the template (`page.tpl` → `page.json`, or the one chosen in Run > Data file), with dotted members such as `site.name`. If the data file is open, its unsaved text is used; while it is broken, the last good version is.
3. **Template variables** defined with `{= name: … =}`.
4. **Names already used** elsewhere in the template.

Each entry shows its type on the right: `string`, `number`, `bool`, `array[3]`, `object`, `loop products`, `template var`…

## Ctrl+Space

**Ctrl+Space** (or Edit > Complete) opens the list wherever you are. Where none of the cases above applies, it offers the Div constructs as snippets, written with your dialect's tags: replacement, loop, condition (with and without `@else@`), template variable, include, preprocessed include, formula, comment, iteration, ignore / txt / strip blocks, location, macro, `@else@`, `@empty@`, `@break@`. What you typed before the cursor narrows them: `{?` leaves the conditions, `loop` the loop.

![Div tags as snippets](images/completion-tags.png)

Snippets that open something keep going: choosing the loop writes `[$` and lists the lists; choosing the include writes `{% ` and lists the templates; choosing a folder lists what is in it.

![include paths](images/completion-includes.png)
