# Ayuda

divide lleva consigo su documentación, como libros: este manual y la propia documentación de Div. **F1** abre la ayuda en el tema de la ventana en la que estás, en una ventana de ayuda coloreada como la de Borland Pascal: negro sobre cian, referencias cruzadas en amarillo.

![la ventana de ayuda en el tema Dialector](images/help.png)

## Abrir la ayuda

| Tecla | Menú | |
|---|---|---|
| **F1** | Ayuda > Uso de la ayuda | el tema de la ventana activa: el editor, un archivo de datos, el proyecto, el dialector, la salida, los mensajes |
| | Ayuda > Contenido | el índice de contenidos del libro que se muestra (el de divide cuando la ayuda está cerrada) |
| | Ayuda > Libros | la lista de libros |
| **Shift+F1** | Ayuda > Índice | todos los temas y todas las secciones del libro que se muestra, por orden alfabético |
| **Ctrl+F1** | Ayuda > Buscar tema | el tema de la palabra bajo el cursor del editor, en cualquier libro (por ejemplo *dialect*, *render*, *loops*). Cuando ningún tema tiene ese nombre, se abre **Buscar** con la palabra. En un archivo PHP con un [[servidor de lenguaje\|Language Servers]], lo que el servidor sabe del símbolo en su lugar |
| | Ayuda > Buscar | los libros por palabras: ver más abajo |
| **Alt+F1** | Ayuda > Tema anterior | vuelve al tema del que venías |

F1 en la propia ventana de ayuda muestra esta página.

![el índice: todos los temas y secciones, por orden alfabético](images/help-index.png)

## La ayuda en español

Los libros están también en español: este manual y la documentación de Div, traducidos en wikis propias, [help-divide-es](https://github.com/divengine/help-divide-es/wiki) y [help-div-es](https://github.com/divengine/help-div-es/wiki). Cuando la interfaz está en español (ver [[El escritorio|The Desktop#idioma]]), la ayuda los muestra; una página aún sin traducir se muestra en inglés. Los temas son los mismos en los dos idiomas, así que **F1** y los enlaces llevan a los mismos sitios.

## Buscar en la ayuda

**Ayuda > Buscar** encuentra las palabras que escribes en todos los libros, como un buscador web. Mientras escribes, lista las secciones que contienen las palabras, las mejores primero. Cada fila es una sección de una página, como `Breakpoints · Debugging PHP`, con las palabras que escribiste resaltadas, y las filas de la documentación de Div van marcadas con *Div*. El panel de abajo muestra el libro y la frase donde aparecen las palabras.

![Ayuda > Buscar](images/help-search.png)

- **El orden.** Primero van las secciones que contienen todas las palabras. Una palabra en el título de una página es lo que más cuenta, después una palabra en un encabezado, después una palabra en el texto. Cuando ninguna sección tiene todas las palabras, se listan las secciones que tienen alguna.
- **Acentos y mayúsculas.** Las palabras coinciden sin distinguir acentos ni mayúsculas: *numero* encuentra *Número*.
- **Mientras escribes.** La última palabra coincide como comienzo de palabra, así que *plantil* ya encuentra *plantillas*.
- **↑ ↓** (y **PgUp PgDn**) mueven la barra mientras sigues escribiendo. **Enter** o un doble clic abre la ayuda en esa sección. **Esc** cierra.

## Moverse en la ventana de ayuda

| Tecla | |
|---|---|
| **Tab** / **Shift+Tab** | referencia cruzada siguiente / anterior |
| **Enter** o un clic | sigue la referencia cruzada, o abre la página web en el navegador |
| **Alt+F1** / **Backspace** | tema anterior |
| **↑ ↓ PgUp PgDn Home End** | desplazarse |
| **Esc** | cierra la ventana de ayuda |

La ventana de ayuda es una ventana como las demás: **F5** la amplía, **F6** pasa a la ventana siguiente y vuelve, y la ayuda se queda donde la dejaste.

## Libros

**Ayuda > Libros** los lista. Cada libro tiene su propio contenido e índice, y el título de la ventana nombra el libro cuando no es el de divide.

| Libro | Qué es | Escrito en |
|---|---|---|
| divide | este manual | la [wiki de divide](https://github.com/divengine/divide/wiki) |
| Div | el motor de plantillas: el lenguaje, los dialectos, la API de PHP | la [carpeta `docs` de Div](https://github.com/divengine/div/tree/master/docs) |

![la documentación de Div en la ventana de ayuda](images/help-div.png)

Un libro es una copia del lugar donde está escrito, así que cada documentación se escribe una sola vez. Las imágenes se omiten. Los enlaces a otros temas son referencias cruzadas, también entre libros. Los enlaces a páginas web van subrayados: **Tab** también llega a ellos, y **Enter** o un clic los abre en el navegador. Son además hipervínculos propios del terminal, así que Ctrl+clic (o el gesto del terminal para los enlaces) también los abre, incluso por SSH cuando el terminal es local.

![la lista de libros](images/help-books.png)

## Añadir un libro

Los libros se listan en `src/divide/manual/books.json`. Cada entrada da:

| Campo | |
|---|---|
| `id`, `title`, `description` | cómo se nombra y se lista el libro |
| `source`, `path` | el repositorio y la carpeta dentro de él con las páginas (Markdown) |
| `home` | la primera página |
| `contents` | el índice de contenidos: el `_Sidebar.md` de una wiki, o un archivo que lista las páginas en orden (una ruta por línea, como el `book-order.txt` de Div); las páginas numeradas `02.10 …` se anidan bajo `02 …` |
| `skip` | páginas que se omiten |

Después copia las páginas con `tools/sync_book.py <id> <checkout of the source>`, y vuelve a ejecutarlo cada vez que cambie el origen:

```bash
tools/sync_book.py divide path/to/divide.wiki
tools/sync_book.py div path/to/div
tools/sync_book.py --index          # only rebuild the search index
```

Tras copiar, el script reconstruye el índice que usa **Ayuda > Buscar** (`src/divide/manual/search.sqlite`), a partir de todos los libros. Si alguna vez las páginas difieren del índice, por ejemplo cuando un libro se copia a mano, divide reconstruye el índice en memoria la primera vez que buscas.
