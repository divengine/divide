# Getting Started

A five-minute tour with a tiny shop. The repository ships it ready in
[`examples/shop`](https://github.com/divengine/divide/tree/main/examples/shop)
(`divide examples/shop`); its layout, simplified:

```
shop/
├── index.tpl
├── index.json
├── components/card.tpl
└── layout/header.tpl, layout/footer.tpl
```

`index.tpl`:

```
{% layout/header %}
<main>
  <h1>{^^title}</h1>
  [$products] product =>
    {% components/card %}
  @empty@
    <p>Nothing on sale today.</p>
  [/$products]
</main>
{% layout/footer %}
```

`index.json`, the data. By Div's convention `index.tpl` takes `index.json`:

```json
{
  "title": "the divide shop",
  "products": [
    {"name": "Potato", "price": 1.5, "offer": true},
    {"name": "Tomato", "price": 2.25, "offer": false}
  ]
}
```

## 1. Open the project

```bash
divide examples/shop
```

The project window opens on the left. Move with the arrows, press **Enter** on `index.tpl`: it opens beside the tree. **F6** cycles windows, **Alt+1…9** jumps to a window by number, **F5** zooms.

## 2. Write with completion

Inside the loop, type `{$`. A list opens with what is visible there: `product`, `product.name`, `product.price`, the fields `name`, `price` directly, and Div's loop variables. Type to narrow it, **Enter** to insert.

![completion inside a loop](images/completion-variables.png)

More in [[Completion]].

## 3. Let divide check the template

Delete the `[/$products]` line. The loop opening turns red and the status line says why. **Alt+F9** opens the Messages window with every problem; **Enter** on a message jumps to it; **Alt+F8** / **Alt+F7** walk the errors without opening the window. Undo with **Ctrl+Z**.

More in [[Checking Templates]].

## 4. Render

Press **Ctrl+F9**. divide runs your template through PHP and Div, with your unsaved edits, and shows the result in an Output window to the right. From now on, saving the template or its data (**F2**) renders again.

More in [[Rendering]].

## 5. Edit the data as a tree

Press **Ctrl+T** in the template: its data file opens as a tree. **Enter** edits a value, **Ins** adds one, **Del** removes it, **F2** saves, and the Output follows.

More in [[Data Files]].

## 6. Follow an include

Put the cursor on `{% components/card %}` and press **Ctrl+Enter** (or Ctrl+click): the template Div would include opens. If Div cannot find it, divide offers to create it.

## 7. Create files without leaving

Back in the project window (**Ctrl+B**), press **Ins** for a new file, **F7** for a new folder, **F2** to rename, **Del** to delete, or **Alt+F10** for the local menu.

More in [[Project Window]].

Leave with **Alt+X**; divide asks about unsaved changes.
