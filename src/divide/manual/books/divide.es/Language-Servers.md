# Servidores de lenguaje

Un servidor de lenguaje es un programa que conoce un lenguaje a fondo: lee el proyecto entero y responde a las preguntas de un editor sobre el código bajo el cursor. divide habla el Language Server Protocol, así que el trabajo de esas herramientas llega al escritorio de Turbo Vision. Para PHP usa [phpactor](https://phpactor.readthedocs.io) o [intelephense](https://intelephense.com).

![autocompletado de un método de Div, con su documentación junto a la lista](https://raw.githubusercontent.com/wiki/divengine/divide/images/lsp.png)

## Qué aporta

| Tecla | |
|---|---|
| al escribir, o **Ctrl+Space** | autocompletado: las funciones, clases, métodos y variables del servidor, con sus tipos; después de `->`, `::`, `$` y `\` se abre solo; una clase de otro namespace trae su línea `use`. La documentación del elemento seleccionado se muestra junto a la lista |
| al escribir `(` o `,` | la firma de la llamada, sobre la línea, con el parámetro que estás escribiendo marcado; sigue al cursor dentro de los paréntesis y se va cuando se cierran (o con **Esc**) |
| **Ctrl+F1** | lo que el servidor sabe de la palabra bajo el cursor (su firma, su documentación), en un diálogo |
| **Ctrl+Enter** / Ctrl+clic | la definición del símbolo bajo el cursor, en su archivo; sobre una cadena con un nombre de archivo, ese archivo (consulta [[Edición de PHP\|Editing PHP]]) |
| | los errores y avisos del servidor se suman a los de PHP en el editor y en la ventana Mensajes (**Alt+F9**) |

El servidor se inicia cuando se abre el primer archivo PHP. Un indicador gira en la línea de estado mientras arranca y mientras indexa el proyecto; cuando el servidor dice cuánto lleva de indexación, una barra lo muestra: `phpactor: Indexing ████░░░░░░ 42%`; después la línea de estado nombra el servidor. Se detiene cuando divide sale.

![la firma de div::parse mientras se escriben sus argumentos](https://raw.githubusercontent.com/wiki/divengine/divide/images/lsp-signature.png)

## Proyectos Composer

En un proyecto con un `composer.json` y su `vendor/` instalado (`composer install`), el servidor también lee las clases de los paquetes. Con Div (`composer require divengine/div`):

- `new di` ofrece `div (divengine)`; al elegirlo escribe `div` y añade `use divengine\div;` al principio del archivo;
- `div::` lista los métodos estáticos de Div, `$tpl->` los métodos de un objeto `div`;
- `\divengine\` lista lo que contiene el namespace.

Las primeras preguntas después de que arranque el servidor pueden tardar un momento mientras lee `vendor/`.

## Instalar un servidor

Necesitas uno de ellos, en el proyecto o en el `PATH`:

| Servidor | Instalación | Se encuentra en |
|---|---|---|
| phpactor | `composer require --dev phpactor/phpactor`, o el `phpactor.phar` de sus releases | `vendor/bin/phpactor` del proyecto, `phpactor` en el `PATH` |
| intelephense | `npm install intelephense` (Node.js) | `node_modules/.bin/intelephense` del proyecto, `intelephense` en el `PATH` |

phpactor está escrito en PHP y es software libre. intelephense funciona sobre Node.js; sus funciones básicas son gratuitas, y algunas necesitan una licencia.

## Elegir el servidor

**Opciones > Servidores de lenguaje...**:

- **Automático** (por defecto): el primero que se encuentre, phpactor y luego intelephense;
- **phpactor** o **intelephense**: ese;
- **Ninguno**: sin servidor; se mantiene la verificación de sintaxis propia de PHP.

El campo **Comando** ejecuta el servidor elegido desde cualquier sitio, por ejemplo `/opt/phpactor.phar` (un `.phar` se ejecuta con `php`) o `/usr/local/bin/intelephense --stdio`. **Examinar** elige el archivo. El diálogo muestra lo que encuentra para cada servidor. divide recuerda la elección.

Si el servidor no arranca, divide dice por qué una vez, y funciona sin él.
