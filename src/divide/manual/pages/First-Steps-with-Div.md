# First Steps with Div

New to Div? This page teaches the language in ten minutes, with divide open beside you. Every example below was rendered by Div; the outputs are exactly what Div writes, blank lines included.

For the whole language, read [Div's own documentation](https://github.com/divengine/div/wiki).

## What Div does

Div is a template engine written in PHP. It takes a **template** (text with tags) and a **model** (your data) and produces text:

```php
echo new div('index.tpl', $data);
```

The output is always text: HTML, source code, configuration files, even other templates. Div keeps processing the result until no tag is left, so a template may generate code that Div then resolves.

In divide you never write that PHP line. Put the data next to the template, with the same name: `index.tpl` takes `index.json`. Then press **Ctrl+F9**.

## Try it in divide

1. Open a folder: `divide my-first-site`.
2. In the project window press **Ins**, name the file `hello.tpl`, then do the same for `hello.json`.
3. Type the examples below, press **F2** to save, and **Ctrl+F9** in the template to render.

While you type `{$`, divide lists the keys of your JSON file (see [[Completion]]). If a tag is unclosed, it turns red (see [[Checking Templates]]).

## Variables

`{$name}` is replaced by the value of `name`. A dot goes into nested data.

`hello.tpl`:

```
Hello, {$name}!
You have {$cart.items} items in your cart.
```

`hello.json`:

```json
{"name": "Ana", "cart": {"items": 3}}
```

Output:

```
Hello, Ana!
You have 3 items in your cart.
```

Tags are **rigid**: `{$name }` looks for a variable called `name ` with the space. A variable that does not exist is left as written, which makes typos easy to spot in the Output window.

An array gives its length: `{$products}` with two products writes `2`.

## Modifiers

A modifier goes between the brace and the name and changes how the value is written. With `{"title": "welcome to the shop"}`:

| Template | Output |
|---|---|
| `{$title}` | welcome to the shop |
| `{^title}` | Welcome to the shop |
| `{^^title}` | Welcome To The Shop |
| `{^^^title}` | WELCOME TO THE SHOP |
| `{%title}` | 19 (characters) |
| `{$title:0,7}` | welcome (from 0, 7 characters) |
| `{#price:2.#}` | 1.50 (a number with two decimals) |

There are more: `{_x}` lowercase, `{html:x}` HTML entities, `{json:x}` JSON, `{/x:Y-m-d/}` a date. Div's documentation lists them all.

## Lists

`[$products] … [/$products]` repeats its body for each item. Inside it, the fields of the item are variables. `@empty@` starts the part written when the list is empty.

`list.tpl`:

```
[$products]
{$_order}. {$name}: {#price:2.#}
@empty@
Nothing on sale today.
[/$products]
```

`list.json`:

```json
{"products": [{"name": "Potato", "price": 1.5}, {"name": "Tomato", "price": 2.25}]}
```

Output:

```

1. Potato: 1.50

2. Tomato: 2.25


```

With `{"products": []}` the output is `Nothing on sale today.`

Div gives every loop some variables of its own:

| Variable | Value |
|---|---|
| `{$_index}` | 0, 1, 2… |
| `{$_order}` | 1, 2, 3… |
| `{$_is_first}`, `{$_is_last}` | true on the first or the last item |
| `{$_is_odd}`, `{$_is_even}` | by the index |
| `{$_previous}`, `{$_next}` | the neighbours |

To give the item a name, write it after the list. This helps in nested loops:

```
[$products] product =>
- {$product.name}
[/$products]
```

In divide, type `[$` and pick a list: the closing `[/$products]` is written for you.

## Conditions

Show a part when a value is true, hide it otherwise:

```
?$offer
On offer!
@else@
Regular price.
$offer?
```

`!$stock … $stock!` is the opposite: its body is shown when `stock` is false, `0`, empty or missing.

```
!$stock
Sold out.
$stock!
```

For a comparison, use an expression. Div replaces the variables, then evaluates the result as PHP:

```
{?( {$price} > 2 )?}
Expensive.
@else@
Cheap.
{/?}
```

Strings must be quoted, so that PHP sees `"big" == "big"` and not `big == "big"`:

```
{?( "{$size}" == "big" )?}
Big one.
{/?}
```

With `{"offer": true, "stock": 0, "price": 1.5, "size": "big"}` these four write `On offer!`, `Sold out.`, `Cheap.` and `Big one.`

Div trims the first and the last blank inside a conditional part. That is why `{$value}!$_is_last, $_is_last!` writes `red,green,blue` and not `red, green, blue`.

## Template variables and formulas

A template can define its own values with `{= name: value =}`. The value is a string, a number, or JSON:

```
{= shop: the divide shop =}
{= tax: 0.1 =}
{= colors: ["red", "green", "blue"] =}
Welcome to {^^shop}.
Colors: [$colors]{$value}!$_is_last, $_is_last![/$colors]
Total: (# {$price} * (1 + {$tax}) :2. #)
```

With `{"price": 20}`:

```



Welcome to The Divide Shop.
Colors: red,green,blue
Total: 22.00
```

- In a list of plain values, the value is `{$value}`.
- `(# … #)` is a **formula**: a PHP expression. `:2.` formats the result with two decimals.
- Data from the model takes precedence: `{= price: 5 =}` would not change a `price` that the JSON already has.

divide checks the JSON inside `{= … =}` as you type.

## Includes and layouts

`{% footer %}` is replaced by the template `footer.tpl`, which sees the same data. The path is relative to the template, without `.tpl`.

A layout leaves named holes, `(( name ))`, and the page fills them with `{{name … name}}`.

`layout.tpl`:

```
<html>
<head><title>(( title ))</title></head>
<body>
(( content ))
</body>
</html>
```

`footer.tpl`:

```
<footer>{$shop}</footer>
```

`page.tpl`:

```
{% layout %}
<!--{ the page fills the layout's locations }-->
{{title
Products
title}}
{{content
<h1>Products</h1>
{% footer %}
content}}
```

With `{"shop": "the divide shop"}`:

```
<html>
<head><title>
Products
</title></head>
<body>

<h1>Products</h1>
<footer>the divide shop</footer>


</body>
</html>
```

`<!--{ … }-->` is a comment: it never reaches the output.

In divide, put the cursor on `{% footer %}` and press **Ctrl+Enter** to open `footer.tpl`. If Div cannot find the template, divide offers to create it.

## Dialects

Every tag above is Div's **default dialect**. A dialect can rename any tag. A template names its dialect in its first lines, and Div translates it when it renders:

```
@_DIALECT = erb.dialect
<h1><%$title%></h1>
```

Build a dialect with the [[Dialector]]. Move templates from one dialect to another with [[Translating Templates]].

## The tags at a glance

| Tag | What it does |
|---|---|
| `{$x}` | the value of `x` |
| `{$a.b}` | a nested value |
| `{^x}` `{^^^x}` `{#x:2.#}`… | modifiers and formats |
| `[$list] … @empty@ … [/$list]` | repeat for each item |
| `[$list] item => … [/$list]` | the same, naming the item |
| `?$x … @else@ … $x?` | if `x` is true |
| `!$x … $x!` | if `x` is false |
| `{?( expression )?} … @else@ … {/?}` | if the PHP expression is true |
| `{= x: value =}` | define a variable |
| `(# expression #)` | a formula |
| `{% path %}` | include a template |
| `(( name ))`, `{{name … name}}` | a location and its content |
| `<!--{ … }-->` | a comment |

Next: [[Getting Started]] tours divide with a small shop. [[Editing Templates]] describes the editor.
