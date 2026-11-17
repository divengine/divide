# Configuración de Div

Tu aplicación PHP configura Div en su propio código: la carpeta de sus plantillas, un dialecto, globales, funciones que las plantillas pueden llamar... divide no ejecuta ese código. Por eso un proyecto le dice a divide cómo configurar Div **mientras diseñas**, en `.div/setup.json`, y cada render, verificación, include, dialecto y traza pasa por esa configuración. Tu aplicación no se toca: es el Div de divide, no el de la aplicación.

**Opciones > Configuración de Div...** la edita sección a sección. También puedes abrir el archivo y editarlo como JSON: divide marca lo que omitiría mientras escribes.

![Opciones > Configuración de Div: las secciones, lo que está en vigor y de dónde viene, el veredicto de Div](images/div-setup.png)

![un global en Opciones > Configuración de Div, completado y renderizado](images/div-setup.gif)

## Dónde está

| Archivo | Para |
|---|---|
| `.div/setup.json` | el proyecto. divide lo busca desde la carpeta que abrió hacia arriba, como git busca `.git`. Guárdalo en el repositorio: es del equipo. |
| `~/.div/setup.json` | tú, en todos los proyectos: tu propio motor, un dialecto que siempre usas, la petición que simulas... (`DIV_HOME` cambia la carpeta). |

- El proyecto gana sobre el usuario. Las listas se unen (primero las del proyecto) y los objetos se mezclan por clave.
- `null` significa *el valor por defecto de Div*: `"files": null` en el proyecto descarta lo que tu configuración dice de las extensiones.
- Las rutas relativas son relativas a la carpeta que contiene ese `.div`: la raíz del proyecto, o tu carpeta personal.
- Todo es opcional. Sin ninguna configuración, divide usa Div tal como viene.
- Una entrada incorrecta se omite y el resto sigue valiendo. Aparece en la [[ventana Mensajes|Checking Templates]] como `SETUP: .div/setup.json: ...` (Enter lleva a ella), y en el editor mientras editas el archivo.

En el editor, una entrada que se omite queda marcada, y con el cursor sobre ella la línea de estado dice por qué (`Aviso: parser.max_cycles: ...`); en otro sitio las cuenta (`JSON ok · 2 avisos`).

![setup.json en el editor: las entradas que divide omite quedan marcadas, y la línea de estado dice por qué](images/div-setup-json.png)

## Qué configura

```json
{
  "engine": "vendor/autoload.php",
  "paths": {"packages": "templates", "repository": "templates", "include": ["shared"]},
  "files": {"template_ext": "tpl", "data_ext": "json"},
  "parser": {"max_cycles": 100, "max_filename": 250, "error_reporting": "E_ALL & ~E_NOTICE"},
  "dialect": "erb.dialect",
  "data": {"globals": {"site": "Shop"},
           "defaults": [{"search": null, "replace": "-"}],
           "defaults_by_var": [{"var": "price", "search": "0", "replace": "free"}],
           "system_vars": ["server", "session"]},
  "php": {"allowed_functions": ["array_sum"], "modifiers": {"rev:": "strrev"}},
  "request": {"get": {"page": 1}, "server": {"HTTP_HOST": "shop.test"}, "session": {"user": "rafa"}}
}
```

| Ajuste | Lo que recibe Div |
|---|---|
| `engine` | el Div que se usa (`autoload.php` o `div.php`). Orden: `DIVIDE_DIV_PHP`, la configuración del proyecto, la tuya, **Opciones > Motor Div**, el `vendor/` del proyecto. |
| `paths.packages`, `paths.repository` | `PACKAGES` y `DIV_REPO`: dónde busca Div las plantillas y los includes |
| `paths.include` | `div::addIncludePath()` para cada carpeta |
| `files.template_ext`, `files.data_ext` | `DIV_DEFAULT_TPL_FILE_EXT`, `DIV_DEFAULT_DATA_FILE_EXT`. divide las sigue: los archivos con la extensión de plantilla son plantillas de Div (también plantillas `.html`), `{% ` las completa sin ella, y el archivo de datos de una plantilla es `pagina.<data_ext>`. |
| `parser.max_cycles`, `parser.max_filename` | `DIV_MAX_PARSE_CYCLES`, `DIV_MAX_FILENAME_SIZE` |
| `parser.error_reporting` | `div::setErrorReporting()`: un número o los niveles de PHP (`E_ALL & ~E_NOTICE`). Los avisos de PHP de las fórmulas que excluye tampoco van a la ventana Mensajes. |
| `dialect` | el dialecto del proyecto: un archivo `.dialect`, o las propias etiquetas `DIV_TAG_*` |
| `data.globals` | `div::setGlobal()`: variables que recibe cada plantilla (los datos de la plantilla ganan). `{$` las completa. |
| `data.defaults`, `data.defaults_by_var` | `div::setDefault()`, `div::setDefaultByVar()`: un valor que se muestra en lugar de otro |
| `data.system_vars` | `div::enableSystemVar()`: `div.ascii`, `div.server`, `div.session`, `div.script_name` (Div activa siempre `div.now`, `div.get`, `div.post`, `div.version`, `div.level`) |
| `php.allowed_functions` | `div::setAllowedFunction()`: funciones de PHP que las plantillas pueden llamar en fórmulas y condiciones |
| `php.modifiers` | `div::addCustomModifier()`: `{rev:nombre}` pasa el valor por la función de PHP |
| `request` | la petición que ven las plantillas: `get`, `post`, `server` (se añade al de PHP), `session`, `cookie` llenan `$_GET`, `$_POST`, `$_SERVER`, `$_SESSION`, `$_COOKIE` antes de que Div trabaje, para `div.get`, `div.post`, `div.server`... |

Los valores por defecto siguen al JSON de Div: un número de un archivo de datos sale de `jsonDecode()` como float, y Div compara los valores por defecto con `serialize()`, así que `"search": 0` nunca coincide con un `0` leído de un archivo de datos. Busca el texto `"0"`, o `null`.

## El dialecto del proyecto

Con un `dialect`, ese es el lenguaje del proyecto:

- una plantilla sin `@_DIALECT` está escrita en él (divide la colorea, la verifica y la completa así);
- las etiquetas que le faltan a un archivo de dialecto son las del dialecto del proyecto, como hace Div al completarlas con sus etiquetas en curso. El [[Dialector|Dialector]] y [[Traducir plantillas|Translating Templates]] lo usan como base; su menú local y el diálogo de traducción pueden cambiar al dialecto por defecto de Div.

Div juzga el dialecto antes que nada. Uno que rechaza se omite, con el motivo de Div en la ventana Mensajes: si no, Div se detendría en cada render.

## Confianza

`php` permite a las plantillas llamar a PHP. Una configuración que llegó con un proyecto (un clon, por ejemplo) podría hacer llamable `system`, así que los ajustes `php` del proyecto esperan a que confíes en ellos: divide pregunta una vez al encontrarlos, y **Opciones > Configuración de Div**, Alt+F10, **Confiar en los ajustes PHP del proyecto** vuelve a preguntar. Tu respuesta se guarda en `~/.div/trust.json` con una huella de esos ajustes: si cambian, divide vuelve a preguntar. Tu propio `~/.div/setup.json` siempre es de confianza.

Mientras tanto se aplica el resto de la configuración, y la ventana Mensajes dice qué espera.

![la pregunta cuando la configuración de un proyecto permite a las plantillas llamar a PHP](images/div-setup-trust.png)

## Lo que no se configura aquí

Los hooks (`beforeBuild`, `afterParse`...), las subclases de `div`, las closures y los sub-parsers son código PHP. divide no ejecuta el código de tu aplicación para diseñar sus plantillas, así que no forman parte de la configuración. La sección `Código PHP propio` de la ventana lo explica.

## La ventana

**Opciones > Configuración de Div...** abre la configuración del proyecto (un `.div/setup.json` nuevo si no hay: **F2** lo crea).

- **Izquierda: las secciones.** Motor y rutas, Extensiones de archivo, Parser, Dialecto, Datos, Funciones PHP, Petición simulada, Código PHP propio. Cada fila dice cuántos ajustes tiene este archivo (`2/4`) y lleva una marca: `•` con ajustes, `!` algo en ella se omite.
- **Derecha: lo que está en vigor** para la sección: cada ajuste, su valor y de dónde viene (`proyecto`, `usuario`, `proyecto + usuario` o `Div`).
- **Debajo de las secciones:** de qué trata la sección; lo que divide omite del archivo tal como está; y el veredicto de Div sobre la configuración guardada: si el dialecto es válido, cuántas rutas de inclusión tiene, las funciones de PHP que no encuentra.

| Tecla | |
|---|---|
| **Enter** / doble clic | editar la sección en un diálogo: rutas con **...** (Examinar), listas separadas por `;` o `,`, valores JSON (se comprueban antes de aceptarlos), variables de sistema como casillas |
| **Supr** | devolver la sección a los valores por defecto de Div en este archivo |
| **F2** | guardar el archivo de configuración (Div ve el archivo guardado) |
| **Ctrl+Z / Ctrl+Y** | deshacer / rehacer |
| **Ctrl+T** | el archivo como JSON |
| **Alt+F10** / **Shift+F10** | menú local: la configuración del usuario o la del proyecto, editar como JSON, el dialecto en el Dialector, confiar en los ajustes PHP del proyecto, verificar con Div |

![editar la sección Datos: globales como JSON, variables de sistema como casillas](images/div-setup-dialog.png)

![el menú local (Alt+F10)](images/div-setup-menu.png)

Como el Dialector, la ventana es una vista del archivo: cada cambio es una edición de su buffer. Antes del primer cambio, si el archivo tiene comentarios, la ventana pregunta antes de reescribirlo como JSON estándar.
