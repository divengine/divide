# Ejecutar PHP

En un script PHP, **Ctrl+F9** (Ejecutar > Ejecutar) lo ejecuta con `php`, como lo harías en una shell, y muestra lo que imprimió. En una plantilla, la misma tecla la renderiza (ver [[Renderizado|Rendering]]).

![Ctrl+F9 en index.php: el cuadro con el veredicto y la salida detrás](https://raw.githubusercontent.com/wiki/divengine/divide/images/run-php.png)

## Mientras se ejecuta

Un cuadro como el *Compiling* de Turbo Pascal indica qué se está ejecutando: el script, sus argumentos, cuánto ha impreso hasta ahora y el tiempo. **Esc** detiene el script.

Cuando termina, el cuadro da el veredicto: **Correcto**, **Avisos**, **Errores**, **Código de salida N** o **Detenido**, con el código de salida y la cuenta de mensajes de PHP. Los resultados ya están en pantalla detrás, y cualquier tecla cierra el cuadro. También se cierra solo: a los dos segundos si todo fue bien, a los cinco en otro caso.

## Qué obtienes

- **La ventana Salida**, blanco sobre negro como la de Turbo Pascal, muestra lo que imprimió el script (stdout). Si PHP o el script escribieron en stderr, aparece debajo de una línea `── stderr ──`. La línea de estado indica el código de salida, el tiempo y el tamaño.
- **La ventana Mensajes** lista los avisos y errores de PHP con su lugar: `index.php(12): Warning: Undefined variable $nope`, `index.php(13): Fatal error: Uncaught Exception: boom`. **Enter** abre el archivo en esa línea, incluso un archivo de `vendor/`. Se le pide a PHP que imprima sus errores como texto plano en stderr (`display_errors=stderr`, `html_errors=0`), así que nunca se mezclan con la salida.

## Cómo se ejecuta

- **Qué se ejecuta**: el script PHP activo, o el último que ejecutaste cuando estás en otra ventana.
- **Se guarda antes**: PHP ejecuta los archivos del disco, así que divide guarda todos los archivos PHP modificados antes de ejecutar. Un script sin nombre tiene que guardarse primero (F2).
- **El directorio de trabajo** es la carpeta del script, como con `cd folder && php script.php`.
- **Sin teclado**: la entrada estándar del script está cerrada, así que un script que hace una pregunta recibe un fin de archivo en vez de esperar para siempre. Para esos, usa *Ejecutar en terminal*.

## Argumentos

**Ejecutar > Argumentos…** define los argumentos de línea de comandos del script, como los escribirías en una shell: `--verbose "two words"`. Llegan en `$argv` y se recuerdan por script (en `~/.config/divide/config.json`). Ctrl+F9 y el [[depurador|Debugging PHP]] los pasan.

## Ejecutar en terminal

**Ejecutar > Ejecutar en terminal** entrega el terminal real al script: el escritorio desaparece, el script se ejecuta con tu teclado y tu pantalla, y **Enter** trae de vuelta divide cuando termina. Úsalo para scripts interactivos y para scripts cuya salida tiene colores o mueve el cursor.

## Renderizar desde PHP

Un script que renderiza con Div (`echo new div('index.tpl', $data);`) muestra la página renderizada en la ventana Salida. Para ver la plantilla sola, con su archivo de datos, abre la plantilla y pulsa Ctrl+F9 allí.

## Páginas web

Las páginas no se ejecutan desde la línea de comandos: **Ejecutar > Servidor web…** las sirve con `php -S`, y mientras está en marcha Ctrl+F9 en una página la abre en el navegador. Ver [[Servidor web|Web Server]].

Siguiente: [[Depurar PHP|Debugging PHP]].
