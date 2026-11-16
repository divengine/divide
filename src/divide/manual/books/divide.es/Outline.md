# Esquema

**Buscar > Esquema** (**Ctrl+O**) abre una ventana a la derecha del escritorio con la forma del archivo activo, una plantilla de Div o un archivo PHP, para ver cómo está hecho y saltar a cualquier parte de él.

![el esquema de la página de inicio de la tienda, en el bucle de productos](images/outline_tpl.png)

## En una plantilla

Una plantilla no tiene declaraciones: Div la reescribe hasta que nada cambia. Su esquema es la estructura que ve el editor, las construcciones que Div reconocería, cada una mostrada por su etiqueta de apertura tal como está escrita:

- variables de plantilla y propiedades: `{= year: 2026 =}`, `@_DIALECT = erb.dialect`;
- includes: `{% layout/header %}`, `{%% components/card %%}`;
- los bloques, con lo que contienen debajo y con sangría: listas `[$products] product =>`, iteraciones `[:1,10:]`, condiciones `{?( {$cart.items} > 0 )?}`, partes condicionales `?$logged` / `!$logged`, cápsulas `[[product`, ubicaciones y su contenido `(( side ))` / `{{side`, sub-parsers, reemplazos múltiples, partes ignoradas y macros.

Los reemplazos (`{$name}`) y las fórmulas se omiten: son el texto de la plantilla, no su forma. Las etiquetas se encuentran con las reglas de Div, las que colorean el editor (consulta [[Edición de plantillas|Editing Templates]]), y con el dialecto de la plantilla: una plantilla en otro dialecto muestra sus propias etiquetas. Las etiquetas largas se cortan con `...`.

## En un archivo PHP

![el esquema de la propia clase de Div, en parseMatches](images/outline.png)

- espacios de nombres, clases (con lo que extienden), interfaces, traits y enums;
- debajo de cada uno, con sangría: sus constantes, casos de enum, propiedades y métodos, con las marcas de UML para su visibilidad: **+** public, **#** protected, **-** private;
- las funciones y constantes del archivo, también las que están dentro de `if (!function_exists(...)) { }`.

Las funciones y los métodos muestran sus parámetros y su tipo de retorno, tal como están escritos: `add(string $name, int $qty = 1): self`. Las closures y las clases anónimas se omiten.

Las declaraciones vienen de la gramática de PHP de [tree-sitter](https://tree-sitter.github.io/), la que colorea el editor (consulta [[Edición de PHP|Editing PHP]]), así que el esquema no necesita servidor de lenguaje y funciona mientras el archivo tiene errores.

## Teclas

| Tecla | Acción |
|---|---|
| **↑ / ↓**, PgUp / PgDn | mover la barra |
| **Enter** / doble clic | ir allí: el editor pasa al frente con la etiqueta o el nombre de la declaración seleccionado |
| **Ctrl+O** | volver al esquema desde el editor |

El esquema te sigue: cambia cuando otro editor de plantilla o de PHP pasa al frente, y se rehace un momento después de que dejas de escribir. En cualquier otro archivo conserva el que mostraba; abierto solo desde otros archivos, dice que el esquema es para archivos PHP y plantillas Div.
