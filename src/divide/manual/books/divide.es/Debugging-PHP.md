# Depurar PHP

divide depura scripts PHP como Turbo Pascal depuraba programas: avanzas por el código línea a línea, la línea que está a punto de ejecutarse es una barra cian, los puntos de ruptura son barras rojas y la ventana Vigilancias muestra lo que contienen tus variables.

![detenido en un punto de ruptura en index.php, con las ventanas Vigilancias y Pila de llamadas](images/debug.png)

![un punto de parada, paso a paso, una expresión vigilada y la salida](images/debugging.gif)

## Qué necesita

El depurador es [Xdebug](https://xdebug.org), la extensión de PHP. Instálalo:

- Debian / Ubuntu: `sudo apt install php-xdebug`
- en otros sistemas: `pecl install xdebug`, o el paquete de tu sistema (ver la [guía de instalación de Xdebug](https://xdebug.org/docs/install)).

Cuando `php -m` lista Xdebug, divide lo usa tal cual. Si prefieres no cargar Xdebug en cada PHP que ejecutas, déjalo fuera de `php.ini` y da la ruta de `xdebug.so` en **Opciones > Xdebug…**: divide lo carga solo para los scripts que depura.

No hace falta configurar nada más. divide inicia el script con Xdebug en modo depuración, apuntando a un puerto libre propio en `127.0.0.1`, diga lo que diga tu `php.ini` sobre `xdebug.mode` o el puerto del cliente.

## Teclas

Estas teclas pertenecen al depurador en los archivos PHP. En las plantillas, F7 abre la [[Traza del render|Render Trace]].

| Tecla | Menú | Acción |
|---|---|---|
| **F8** | Ejecutar > Pasar por encima | ejecuta la línea; las llamadas se ejecutan enteras. El primer F8 inicia el script y se detiene en su primera línea |
| **F7** | Ejecutar > Trazar dentro | ejecuta la línea, entrando en las funciones que llama (incluso en `vendor/`) |
| **Shift+F8** | Ejecutar > Salir de la función | ejecuta hasta que la función actual retorna |
| **F4** | Ejecutar > Ir al cursor | ejecuta hasta la línea del cursor |
| **Ctrl+F9** | Ejecutar > Ejecutar | ejecuta hasta el siguiente punto de ruptura, o hasta el final |
| **Ctrl+F2** | Ejecutar > Reiniciar programa | termina el script ahora |
| **Ctrl+F8** | Depurar > Punto de ruptura | un punto de ruptura en la línea del cursor, o lo quita |
| **Ctrl+F7** | Depurar > Añadir vigilancia | una expresión para la ventana Vigilancias |
| **Ctrl+F4** | Depurar > Evaluar | el valor de cualquier expresión PHP, donde se detuvo el script |
| **Ctrl+F3** | Depurar > Pila de llamadas | las llamadas que llevaron a esta línea |

Sin puntos de ruptura, Ctrl+F9 ejecuta el script hasta el final; con uno, inicia el depurador y se detiene ahí. Todas las formas de iniciar pasan los [[argumentos|Running PHP]] de Ejecutar > Argumentos.

![el menú Depurar](images/menu-debug.png)

## Puntos de ruptura

**Ctrl+F8** sobre una línea la pinta de rojo. Se pueden poner antes de iniciar o mientras el script está en pausa, y se quedan en sus números de línea (editar líneas por encima no los mueve). Duran hasta que se cierra divide.

## Vigilancias y variables

**Depurar > Vigilancias** abre la ventana Vigilancias abajo a la izquierda. Como las ventanas del depurador de Turbo Pascal, es cian con texto negro, y la línea bajo el cursor es blanca sobre rojo (también en la Pila de llamadas). En cada parada muestra:

- tus expresiones vigiladas y sus valores: `count($data['products']) = 3`. **Ins** (o Ctrl+F7) añade una, **Supr** quita la que está bajo el cursor;
- debajo de `── variables locales ──`, todas las variables de la función donde se detuvo el script, con el primer nivel de arrays y objetos: `$data = array(6)`, `  title = 'the divide shop'`.

**Ctrl+F4** evalúa una expresión una vez, en un recuadro: `$sum + $x * 10 = 10`. Empieza con la palabra bajo el cursor. Las expresiones se ejecutan en el script, así que una llamada con efectos secundarios ocurre de verdad.

## Pila de llamadas

**Ctrl+F3** abre la ventana Pila de llamadas abajo a la derecha: primero la función donde se detuvo el script, `{main}` al final. **Enter** sobre una llamada muestra su línea, y a partir de entonces Vigilancias y Evaluar miran las variables de esa llamada. El siguiente paso vuelve a la más interna.

## Páginas web

**Ejecutar > Servidor web…** sirve el proyecto con `php -S`, y sus peticiones se detienen en los mismos puntos de ruptura: ver [[Servidor web|Web Server]].

## Salida y errores

Lo que imprime el script aparece en la ventana Salida a medida que lo imprime. Cuando el script termina, las ventanas Salida y Mensajes se llenan como después de [[Ctrl+F9|Running PHP]].

## Límites

- Un script a la vez, ejecutado desde la línea de comandos (`php script.php`). Las páginas web se depuran a través del [[Servidor web|Web Server]] (`php -S`).
- Los valores se muestran con un nivel de profundidad; pide uno más profundo con una vigilancia o con Evaluar (`$data['products'][0]`).
