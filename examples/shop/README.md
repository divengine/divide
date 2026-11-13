# shop: a small Div project

A demo storefront used in the [manual](https://github.com/divengine/divide/wiki)
and to generate its screenshots (`tools/wiki_shots.py`).

- `index.tpl` + `index.json`: the home page and its data (Div's convention:
  same name, `.json`). It loops over the products, includes a component per
  product, and includes the header and footer layouts.
- `components/card.tpl`, `layout/header.tpl`, `layout/footer.tpl`: the
  included templates.
- `checkout.tpl` is **broken on purpose**: an unclosed loop, an unclosed
  condition, an include Div cannot find, bad JSON in a template variable and
  an orphan loop closing. Open it and press Alt+F9.

Try it:

```bash
divide examples/shop
```

Rendering needs `php` and Div (see the manual's Installation page).
