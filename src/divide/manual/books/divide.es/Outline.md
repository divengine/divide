# Esquema

**Buscar > Esquema** (**Ctrl+O**) abre una ventana a la derecha del escritorio con las declaraciones del archivo PHP activo, para ver cómo está hecho el archivo y saltar a cualquier parte de él.

![el esquema de la propia clase de Div, en parseMatches](https://raw.githubusercontent.com/wiki/divengine/divide/images/outline.png)

## Qué lista

- espacios de nombres, clases (con lo que extienden), interfaces, traits y enums;
- debajo de cada uno, con sangría: sus constantes, casos de enum, propiedades y métodos, con las marcas de UML para su visibilidad: **+** public, **#** protected, **-** private;
- las funciones y constantes del archivo, también las que están dentro de `if (!function_exists(...)) { }`.

Las funciones y los métodos muestran sus parámetros y su tipo de retorno, tal como están escritos: `add(string $name, int $qty = 1): self`. Las closures y las clases anónimas se omiten.

Las declaraciones vienen de la gramática de PHP de [tree-sitter](https://tree-sitter.github.io/), la que colorea el editor (consulta [[Edición de PHP|Editing PHP]]), así que el esquema no necesita servidor de lenguaje y funciona mientras el archivo tiene errores.

## Teclas

| Tecla | Acción |
|---|---|
| **↑ / ↓**, PgUp / PgDn | mover la barra |
| **Enter** / doble clic | ir a la declaración: el editor pasa al frente con su nombre seleccionado |
| **Ctrl+O** | volver al esquema desde el editor |

El esquema te sigue: cambia cuando otro editor de PHP pasa al frente, y se rehace un momento después de que dejas de escribir. En una plantilla conserva el archivo PHP que mostraba; abierto solo desde una plantilla, dice que el esquema es para archivos PHP.
