# Archivos de datos

Los archivos `.json` (y los archivos `.dialect`) son **Div JSON**: todo lo que acepta el `jsonDecode()` de Div. Es decir, JSON más:

- referencias como valores: `"author": $site.owner`;
- comillas simples, claves sin comillas, comas finales;
- comentarios.

## Como código

El editor resalta claves, cadenas, números, constantes y referencias, y valida mientras escribes: un error se pinta en su sitio y la línea de estado dice `JSON [!] line 6, col 47: unexpected 'r', expected a value`. Cuando todo está bien dice `JSON correcto`, y cuántas referencias usa el archivo.

![un error de JSON mientras se escribe](https://raw.githubusercontent.com/wiki/divengine/divide/images/data-code.png)

## Como árbol

**Ctrl+T** convierte el mismo buffer en un árbol. Desde una plantilla, Ctrl+T abre el árbol de su archivo de datos (y crea `page.json` si aún no existe). Ctrl+T de nuevo vuelve al código.

![el árbol de datos](https://raw.githubusercontent.com/wiki/divengine/divide/images/data-tree.png)

| Tecla | |
|---|---|
| **Enter** | editar el elemento: clave, tipo, valor |
| **Ins** | añadir un elemento: dentro de un objeto o array, o después de un valor simple |
| **Supr** | eliminar el elemento |
| **Ctrl+↑ / Ctrl+↓** | mover el elemento arriba / abajo |
| **Ctrl+Z / Ctrl+Y** | deshacer / rehacer (con el historial del editor de código) |
| **F2** | guardar |

El diálogo de edición te deja cambiar el tipo además del valor: Texto, Número, Verdadero, Falso, Nulo, Referencia, Objeto, Array.

![edición de un elemento](https://raw.githubusercontent.com/wiki/divengine/divide/images/data-tree-edit.png)

El árbol y el código son un solo buffer: escribir en el código reconstruye el árbol (mientras el JSON está roto, se queda el último árbol bueno y se rechaza la edición hasta que se arregle), y cada edición del árbol reescribe el código como JSON estándar, manteniendo las referencias sin comillas. Si el archivo usa comentarios, comillas simples o claves sin comillas, que una reescritura eliminaría, divide pregunta antes.
