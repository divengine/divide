# Renderizado

**Ctrl+F9** (Ejecutar > Ejecutar) en una plantilla la renderiza a través de PHP y del motor Div real, y muestra el resultado junto al código. (En un script PHP la misma tecla ejecuta el script: ver [[Ejecutar PHP|Running PHP]].)

![plantilla y salida lado a lado](images/hero.png)

## El recuadro de progreso

Mientras Div trabaja, un recuadro como el *Compiling* de Turbo Pascal muestra la plantilla, el archivo de datos, el motor y un reloj; las plantillas grandes pueden tardar un rato, y **Esc** detiene el render.

Debajo corre una barra al estilo de Norton Commander, dibujada con los bloques del propio juego de caracteres del PC: `█` y `▓` llenan una pista de `░`. Div no dice cuánto le falta, así que un bloque va y viene por la pista mientras trabaja; cuando termina, la barra se llena, sea cual sea el veredicto; solo una detención (**Esc**) deja la pista como estaba. El mismo recuadro, y la misma barra, aparecen al ejecutar PHP (ver [[Ejecutar PHP|Running PHP]]), al verificar (**Alt+F9**) y en la [[Traza del render|Render Trace]].

![el recuadro de progreso mientras Div trabaja](images/progress-running.png) Cuando termina, el recuadro da el veredicto, **Correcto**, **Avisos** o **Errores**, con la versión de Div, el tamaño de la salida y el número de mensajes. La salida ya está detrás; cualquier tecla cierra el recuadro. También se cierra solo: a los dos segundos si todo fue bien, a los cinco cuando hay avisos o errores, para que te dé tiempo a leerlos (también están en la ventana Mensajes).

![el recuadro de progreso tras un render](images/render-box.png)

## Qué se renderiza

- **La plantilla**: la activa; o, desde un archivo de datos, la plantilla a la que pertenece; o la última renderizada. Sus **cambios sin guardar se incluyen**, y a Div se le da su ruta real para que funcionen los includes relativos. Las plantillas sin título no se renderizan: ver *Save first* en [[Verificación de plantillas|Checking Templates]].
- **Los datos**: por convención de Div, `page.tpl` toma `page.json`, a su lado. **Ejecutar > Archivo de datos…** elige otro archivo; **Ejecutar > Editar datos** lo abre (creándolo si hace falta). Si el archivo de datos está abierto, se usa el buffer del editor.
- **El directorio de trabajo** es la carpeta del proyecto, como en las verificaciones de includes.

El primer render coloca la plantilla a la izquierda y la Salida a la derecha. La ventana Salida es de solo lectura y está resaltada, así que las etiquetas de Div que quedaron sin procesar destacan. Su línea de estado dice qué se renderizó: `index.tpl + index.json · Div 6.1.2 · 0.08s`.

## Renderizar de nuevo

Mientras la ventana Salida está abierta, **guardar la plantilla o sus datos vuelve a renderizar** en segundo plano, sin mover el foco y sin el recuadro (un indicador gira en la línea de estado). **Alt+F5** trae de vuelta la ventana Salida; si no hay ninguna, renderiza.

## Mensajes

Los avisos propios de Div, los notices de PHP y los problemas con los datos van a la [[ventana Mensajes|Checking Templates]], debajo de las verificaciones de la plantilla. Por ejemplo `DATA: Div could not decode the data as an object; rendering without data` cuando el JSON está roto; los datos se decodifican con el propio `jsonDecode()` de Div, así que lo que ves es lo que recibe la plantilla.

Un comportamiento de Div que conviene conocer: un archivo de datos se decodifica antes de que exista ninguna variable, así que las `$references` dentro de `page.json` salen vacías. divide añade una nota cuando ocurre. Las referencias sí funcionan en el JSON dentro de las plantillas, p. ej. `{= card: {"who": $person.name} =}`.

## Elegir el motor

Ver [[Instalación|Installation]]: `DIVIDE_DIV_PHP`, la [[configuración de Div|Div Setup]] del proyecto, **Opciones > Motor Div…**, o el `vendor/` del proyecto. Cuando no se encuentra Div, Ctrl+F9 te dice cómo instalarlo.

Div renderiza con la [[configuración de Div|Div Setup]] del proyecto (`.div/setup.json`): sus carpetas de plantillas, extensiones, dialecto, globales, funciones y petición simulada, como los configuraría tu aplicación.

## Cómo llegó Div ahí

**Depurar > Traza del render** renderiza de la misma forma y te deja reproducir cada cambio que Div hizo en la plantilla, paso a paso, hasta el punto fijo en el que ya no cambia nada. Ver [[Traza del render|Render Trace]].
