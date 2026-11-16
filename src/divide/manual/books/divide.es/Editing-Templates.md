# Edición de plantillas

Los archivos que terminan en `.tpl` (y `.div`) son plantillas Div; las ventanas sin nombre también se tratan como plantillas.

## Un resaltado que conoce Div

Cada construcción del lenguaje tiene su propio color: los reemplazos y sus modificadores (`{$x}`, `{^^title}`, `{html:body}`, `{$body:~25}`), los bucles y los nombres de sus elementos, las condiciones, las variables de plantilla y su JSON, los includes, las fórmulas, los formatos de número y de fecha, los comentarios y bloques de documentación, las macros, los bloques ignorados… El código Div anidado dentro de otro código Div también se resalta, y el HTML entre etiquetas se colorea suavemente para que el Div quede en primer plano.

### Dialectos

Div permite que una plantilla cambie sus etiquetas con `@_DIALECT = file.dialect`. divide resalta, verifica y completa con **tus** etiquetas, y la línea de estado muestra el nombre del dialecto.

Qué archivo es ese, y qué dice, es asunto de Div: divide le pide a Div que cargue el dialecto como lo hace cuando renderiza. Div encuentra el archivo con `getTplPath()` (relativo al directorio de trabajo, a la carpeta de la plantilla, a las plantillas incluidas antes) y lo decodifica con su propio `jsonDecode()`. Si Div no puede encontrar el archivo o no puede decodificarlo, la línea `@_DIALECT` se informa como error. Hasta que Div responde, o sin PHP y Div, divide adivina el archivo solo para colorear la plantilla y no informa nada sobre él. Como los includes, el dialecto se resuelve desde la carpeta de la plantilla, así que se verifica una vez guardada la plantilla (ver *Guardar antes* en [[Verificación de plantillas|Checking Templates]]). Para construir un dialecto, usa el [[Dialector]]; para pasar una plantilla a otro dialecto, [[Traducir plantillas|Translating Templates]].

## Buscar y reemplazar

| Tecla | |
|---|---|
| **Ctrl+F** | Buscar |
| **Ctrl+R** | Reemplazar |
| **Ctrl+L** | Buscar de nuevo (repite la última búsqueda o reemplazo) |
| **Ctrl+G** | Ir a línea |

Los diálogos son los clásicos: mayúsculas y minúsculas, palabras completas, expresiones regulares (con grupos `\1` en el reemplazo), hacia adelante o hacia atrás, desde el cursor o en todo el archivo, y *preguntar al reemplazar* para confirmar cada cambio. Se propone como texto a buscar el texto seleccionado, o la palabra bajo el cursor.

![el diálogo Reemplazar](https://raw.githubusercontent.com/wiki/divengine/divide/images/replace.png)

## Teclas de edición

Funcionan las habituales: flechas, Home/End, PgUp/PgDn, Shift para seleccionar, **Ctrl+Z** / **Ctrl+Y** deshacer y rehacer, **Ctrl+X/C/V** cortar, copiar y pegar, **Ctrl+A** seleccionar todo, **Tab** sangra (**F7** abre la [[Traza del render|Render Trace]]). **Ctrl+Space** abre el [[autocompletado|Completion]], **Ctrl+Enter** va a la plantilla a la que apunta un include (ver [[Verificación de plantillas|Checking Templates]]).

## Otros archivos

Los archivos de datos (`.json`, `.dialect`) son JSON de Div: ver [[Archivos de datos|Data Files]]. Los archivos PHP tienen su propio editor: ver [[Edición de PHP|Editing PHP]]. Cualquier otro archivo se abre como texto plano.
