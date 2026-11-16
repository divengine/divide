# Otros archivos

Un proyecto PHP es más que plantillas y PHP: un README, hojas de estilo, scripts para el navegador, la configuración de PHPUnit o del framework, un `php.ini`, un CSV con los datos que importar. divide los abre todos en el mismo editor, con sus colores, así que no tienes que salir de él para ver uno.

![README.md, phpunit.xml.dist, php.ini y un CSV, en mosaico](images/other-files.png)

| Lenguaje | Archivos |
|---|---|
| HTML | `.html`, `.htm` |
| CSS | `.css` |
| JavaScript | `.js`, `.mjs`, `.cjs`, `.jsx` |
| Markdown | `.md`, `.markdown` |
| SQL | `.sql` |
| XML | `.xml`, `.xsd`, `.xsl`, `.xslt`, `.svg`, `.xhtml`, `.xliff`, `.xlf`, y los archivos `.xml.dist` (`phpunit.xml.dist`, `phpcs.xml.dist`) |
| YAML | `.yml`, `.yaml`, `.neon`, y los archivos `.yml.dist` / `.yaml.dist` |
| TOML | `.toml` |
| Shell | `.sh`, `.bash`, `.bashrc`, `.profile`, y `.env` con sus variantes (`.env.local`, `.env.test`…) |
| INI | `.ini`, `.cfg`, `.conf`, `.editorconfig`, `.ini.dist` |
| CSV | `.csv`, `.tsv` |

La línea de estado nombra el lenguaje del archivo en el que estás. Un archivo que divide no conoce (`.txt`, `.log`…) se abre como texto plano.

## Cómo se colorean

Los nueve primeros se leen con gramáticas de [tree-sitter](https://tree-sitter.github.io/), igual que PHP (consulta [[Edición de PHP|Editing PHP]]): los colores siguen la estructura del archivo, no conjeturas con patrones. Una gramática se carga la primera vez que se abre un archivo de su lenguaje.

Los colores vienen del tema de **Opciones > Colores**: las cadenas, los números, las palabras reservadas, los comentarios, las etiquetas y los nombres toman los mismos colores que en las plantillas y en PHP, en todos los temas (consulta [[El escritorio|The Desktop#colores]]).

**INI**: las `[sections]`, las claves, sus valores (cadenas entre comillas, números como `128M`, y `On` / `Off` / `true` / `false`) y los comentarios, de línea entera o tras un valor (`;` o `#`).

**CSV**: cada columna tiene un color propio, seis por turnos, para poder seguir una columna a lo largo del archivo. Un campo entre comillas puede contener el separador (`"Potato, red"`) y sigue siendo un solo campo. El separador se toma de la primera línea: coma, punto y coma, tabulador o `|`; los archivos `.tsv` usan tabuladores.

## Lo que divide no hace con ellos

Se colorean, no se verifican: divide lista errores solo para plantillas, Div JSON y PHP (consulta [[Verificación de plantillas|Checking Templates]]). El autocompletado y los servidores de lenguaje también son para plantillas y PHP. Cada uno tiene su [[esquema|Outline]]: los elementos de una página HTML, los encabezados de un archivo Markdown, las reglas de una hoja de estilos, las tablas de un script SQL, las claves de un archivo YAML o JSON...
