# Servidor web

**Ejecutar > Servidor web…** inicia el servidor web integrado de PHP (`php -S`) para el proyecto. Abres las páginas en el navegador, y el [[depurador|Debugging PHP]] detiene sus peticiones en tus puntos de ruptura, como detiene un script.

![Ejecutar > Servidor web: la dirección, la carpeta raíz y el enrutador](images/web-server-dialog.png)

## Iniciarlo

El diálogo pide:

- **Dirección**: `host:port`, `127.0.0.1:8000` al principio. Usa `0.0.0.0:8000` para llegar a él desde otras máquinas.
- **Carpeta raíz**: la carpeta cuyos archivos son el sitio (`-t`). Empieza siendo la carpeta del proyecto. **Carpeta…** elige otra carpeta: en la lista, entra en las carpetas con Enter, y luego OK sobre `.` (la línea del nombre) elige la carpeta mostrada.
- **Script enrutador** (opcional): un archivo PHP que recibe todas las peticiones, como usan los frameworks (`public/index.php`). **Enrutador…** lo elige.
- **Abrir en el navegador**: abre la dirección del sitio cuando el servidor arranca.

**Iniciar** ejecuta `php -S address -t root [router]`. Si PHP no puede servir (el puerto está ocupado, por ejemplo), una caja muestra lo que dijo PHP. Estos valores se recuerdan por proyecto.

Ejecutar > Servidor web otra vez, mientras el servidor está en marcha, ofrece **Abrir en el navegador** y **Detener el servidor**. Salir de divide también lo detiene.

## La ventana Servidor web

El registro del servidor se abre abajo, bajo la página que estabas editando: cada petición (`127.0.0.1:50658 [200]: GET /?page=2`) y los avisos y errores de PHP. Esos errores también van a la ventana **Mensajes** con su lugar, así que **Enter** abre el archivo en su línea, como después de [[Ejecutar PHP|Running PHP]].

Lo que imprimen las páginas va al navegador, no a la ventana Salida.

## Depurar peticiones

Con Xdebug (consulta [[Depurar PHP|Debugging PHP]] para instalarlo), cada petición que ejecuta PHP se conecta a divide:

- **Ningún punto de ruptura en su camino**: la petición se ejecuta entera, a velocidad normal.
- **Un punto de ruptura** (Ctrl+F8) en una línea que ejecuta: se pausa ahí. La barra cian, F7, F8, Shift+F8, F4, Vigilancias, Evaluar y la Pila de llamadas funcionan como con un script. La línea de estado dice qué petición es: `Paused at index.php:14 (GET /?page=2)`. El navegador espera la página hasta que dejas que la petición siga (Ctrl+F9).
- **F8 o F7 sin ninguna petición pausada**, en un archivo que sirve el servidor: la siguiente petición se detiene en su primera línea. **F4** hace que se detenga en la línea del cursor. Ctrl+F2 lo cancela.
- **Ctrl+F2** sobre una petición pausada la termina: el navegador recibe lo que la petición imprimió hasta entonces.

![una petición de la tienda pausada en un punto de ruptura, con el registro del servidor debajo](images/web-debug.png)

Sin Xdebug el servidor funciona igual, y sus páginas simplemente no se depuran.

## Ctrl+F9 en una página

Mientras el servidor está en marcha, **Ctrl+F9** en un archivo PHP bajo la carpeta raíz (o la carpeta del enrutador) no lo ejecuta desde la línea de comandos: abre su dirección en el navegador (`/shop/cart.php`; `/` para `index.php`, y para todo cuando hay enrutador). La petición se detiene entonces en sus puntos de ruptura. Detén el servidor para volver a ejecutar esos archivos desde la línea de comandos.

## Límites

- Una petición cada vez: `php -S` tiene un solo worker, así que mientras una petición está pausada las siguientes esperan, también las imágenes y estilos de la página cuando un enrutador los hace pasar por PHP.
- Las peticiones atendidas antes de poner un punto de ruptura no se vuelven a detener: recarga la página.
- Es un servidor de desarrollo, como dice PHP: no es para producción.

Volver: [[Depurar PHP|Debugging PHP]].
