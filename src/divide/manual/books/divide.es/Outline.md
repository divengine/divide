# Esquema

**Buscar > Esquema** (**Ctrl+O**) abre una ventana a la derecha del escritorio con la forma del archivo activo como un árbol, en cada lenguaje que divide colorea (una plantilla de Div, PHP, HTML, Markdown, CSS, JavaScript, SQL, JSON, YAML...): para ver cómo está hecho, plegar lo que no necesitas y saltar a cualquier parte de él.

![el esquema de la página de inicio de la tienda, en el bucle de productos](images/outline_tpl.png)

![el esquema de una plantilla, un salto, un render, los miembros en la ventana del proyecto](images/outline.gif)

## Cómo se lee

Cada fila empieza con una letra que dice qué es, en su color: **C** una clase, **m** un método, **l** una lista de Div... Los miembros de una clase llevan después la marca de UML de su visibilidad: **+** public (verde), **#** protected (amarillo), **-** private (rojo). Luego el nombre, coloreado como lo colorea el editor: en `m + add(string $name, int $qty = 1): self` el nombre del método, los tipos y los parámetros tienen cada uno el color que tienen en el código, en cada paleta de **Opciones > Colores**.

Lo que contiene otras partes lleva un **►** delante: **▼** cuando está desplegado, con lo que contiene debajo y con sangría, unido por líneas.

## En una plantilla

Una plantilla no tiene declaraciones: Div la reescribe hasta que nada cambia. Su esquema es la estructura que ve el editor, las construcciones que Div reconocería, cada una mostrada por su etiqueta de apertura tal como está escrita:

| Letra | Qué |
|---|---|
| **p** | una propiedad: `@_DIALECT = erb.dialect` |
| **v** | una variable de plantilla: `{= year: 2026 =}` |
| **i** | un include: `{% layout/header %}`, `{%% components/card %%}` |
| **l** | una lista: `[$products] product =>` |
| **r** | una iteración: `[:1,10:]` |
| **?** | una condición `{?( {$cart.items} > 0 )?}`, una parte condicional `?$logged` / `!$logged` |
| **c** | una cápsula: `[[product` |
| **o** | una ubicación y su contenido: `(( side ))` / `{{side` |
| **s**, **x**, **g**, **a** | un sub-parser, reemplazos múltiples, una parte ignorada, una macro |

Los bloques contienen lo que está escrito dentro de ellos: el include dentro de una lista está debajo de la lista. Los reemplazos (`{$name}`) y las fórmulas se omiten: son el texto de la plantilla, no su forma. Las etiquetas se encuentran con las reglas de Div, las que colorean el editor (consulta [[Edición de plantillas|Editing Templates]]), y con el dialecto de la plantilla: una plantilla en otro dialecto muestra sus propias etiquetas. Las etiquetas largas se cortan con `...`.

## En un archivo PHP

![el esquema de la propia clase de Div, en parseMatches](images/outline.png)

| Letra | Qué |
|---|---|
| **n** | un espacio de nombres: lo que sigue a `namespace X;` (o está dentro de `namespace X { }`) va debajo de él |
| **C**, **I**, **T**, **E** | una clase (con lo que extiende e implementa), una interfaz, un trait, un enum |
| **m** | un método, con sus parámetros y su tipo de retorno tal como están escritos |
| **p** | una propiedad, con su tipo: `- $items: array` |
| **k** | una constante o un caso de enum |
| **f** | una función, también dentro de `if (!function_exists(...)) { }` |

Las clases, interfaces, traits y enums contienen sus miembros. Las closures y las clases anónimas se omiten.

Las declaraciones vienen de la gramática de PHP de [tree-sitter](https://tree-sitter.github.io/), la que colorea el editor (consulta [[Edición de PHP|Editing PHP]]), así que el esquema no necesita servidor de lenguaje y funciona mientras el archivo tiene errores.

## En los demás archivos

El mismo árbol, con aquello de lo que está hecho cada tipo de archivo. Las etiquetas también conservan aquí los colores del editor.

| Archivo | Qué contiene el esquema |
|---|---|
| HTML | cada elemento (**<**), anidado como está escrito, por su etiqueta, id y clases: `main#main.page`; los scripts, enlaces e imágenes con su `src` o `href` |
| XML | cada elemento (**<**), anidado, con su `name`, `id` o primer atributo: `testsuite name="unit"` |
| Markdown | los encabezados (**#**), cada uno con los más profundos debajo |
| CSS | las reglas (**s**) por sus selectores; `@media`, `@supports` y `@keyframes` (**@**) con sus reglas dentro; `@import` |
| JavaScript | los imports (**u**), las clases con sus métodos y campos (los `#privados` marcados con **-**), las funciones, y las constantes (**k**) y variables (**v**) del archivo; una constante que guarda una función cuenta como función |
| SQL | lo que crea el script: tablas (**t**) con sus columnas y tipos (**c**), vistas (**w**), índices (**x**), funciones |
| JSON | las claves (**k**) con sus valores; los objetos (**o**) y las listas (**a**, con cuántos elementos tienen) con las suyas dentro; los objetos de una lista como `[0]`, `[1]`... con su primera clave al lado |
| YAML, TOML | las claves del mismo modo; las tablas de TOML `[owner]` (**t**) y `[[products]]` (**a**) |
| Scripts de shell, `.env` | las funciones y las variables que se asignan |
| INI (`php.ini`) | las secciones (**[**) con sus claves y valores |
| CSV | las columnas, por los nombres de la primera fila |

## Teclas

| Tecla | Acción |
|---|---|
| **↑ / ↓**, PgUp / PgDn | mover la barra |
| **Enter** / doble clic | ir allí: el editor pasa al frente con la etiqueta o el nombre de la declaración seleccionado |
| **Espacio** | plegar o desplegar la parte bajo la barra |
| **←** | plegarla; en una parte plegada o que no contiene nada, a la parte que la contiene |
| **→** | desplegarla; en una parte desplegada, a lo primero que contiene |
| clic en **►** / **▼** | plegar o desplegar |
| **Ctrl+O** | volver al esquema desde el editor |

El esquema te sigue: cambia cuando otro editor pasa al frente, y se rehace un momento después de que dejas de escribir, conservando lo que plegaste y la barra donde estaba. En un archivo de texto plano conserva el que mostraba; abierto solo desde esos archivos, dice que no hay esquema para ese tipo de archivo.

Los mismos miembros están en la [[Ventana de proyecto|Project Window]], debajo de cada archivo: despliega un archivo allí para verlos sin abrirlo.
