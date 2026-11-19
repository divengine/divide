# Primeros pasos

![un recorrido: completado, verificación, render, la traza, los datos, el esquema, el Dialector](images/tour.gif)

Un recorrido de cinco minutos con una tienda diminuta. El repositorio la trae lista en
[`examples/shop`](https://github.com/divengine/divide/tree/main/examples/shop)
(`divide examples/shop`); su estructura, simplificada:

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

`index.json`, los datos. Por convención de Div, `index.tpl` toma `index.json`:

```json
{
  "title": "the divide shop",
  "products": [
    {"name": "Potato", "price": 1.5, "offer": true},
    {"name": "Tomato", "price": 2.25, "offer": false}
  ]
}
```

## 1. Abre el proyecto

```bash
divide examples/shop
```

La ventana de proyecto se abre a la izquierda. (`divide` solo muestra la ventana de bienvenida, con las carpetas y archivos que abriste hace poco: ver [[El escritorio|The Desktop#una-carpeta-un-archivo-o-nada]].) Muévete con las flechas y pulsa **Enter** sobre `index.tpl`: se abre junto al árbol. **F6** recorre las ventanas, **Alt+1…9** salta a una ventana por su número, **F5** la amplía.

## 2. Escribe con autocompletado

Dentro del bucle, escribe `{$`. Se abre una lista con lo que es visible ahí: `product`, `product.name`, `product.price`, los campos `name` y `price` directamente, y las variables de bucle de Div. Escribe para acotarla y pulsa **Enter** para insertar.

![autocompletado dentro de un bucle](images/completion-variables.png)

Más en [[Autocompletado|Completion]].

## 3. Deja que divide verifique la plantilla

Borra la línea `[/$products]`. La apertura del bucle se pone en rojo y la línea de estado dice por qué. **Alt+F9** abre la ventana Mensajes con todos los problemas; **Enter** sobre un mensaje salta a él; **Alt+F8** / **Alt+F7** recorren los errores sin abrir la ventana. Deshaz con **Ctrl+Z**.

Más en [[Verificación de plantillas|Checking Templates]].

## 4. Renderiza

Pulsa **Ctrl+F9**. divide pasa tu plantilla por PHP y Div, con tus cambios sin guardar: un cuadro de progreso indica cómo fue (se cierra solo, o con cualquier tecla) y el resultado queda en una ventana Salida a la derecha. A partir de ahí, guardar la plantilla o sus datos (**F2**) vuelve a renderizar.

Más en [[Renderizado|Rendering]].

## 5. Edita los datos como un árbol

Pulsa **Ctrl+T** en la plantilla: su archivo de datos se abre como un árbol. **Enter** edita un valor, **Ins** añade uno, **Supr** lo elimina, **F2** guarda, y la Salida lo sigue.

Más en [[Archivos de datos|Data Files]].

## 6. Sigue un include

Pon el cursor sobre `{% components/card %}` y pulsa **Ctrl+Enter** (o Ctrl+clic): se abre la plantilla que Div incluiría. Si Div no la encuentra, divide ofrece crearla.

## 7. Crea archivos sin salir

De vuelta en la ventana de proyecto (**Ctrl+B**), pulsa **Ins** para un archivo nuevo, **F7** para una carpeta nueva, **F2** para renombrar, **Supr** para eliminar, o **Alt+F10** para el menú local.

Más en [[Ventana de proyecto|Project Window]].

Sal con **Alt+X**; divide pregunta por los cambios sin guardar.
