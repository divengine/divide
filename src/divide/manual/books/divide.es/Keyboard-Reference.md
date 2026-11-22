# Referencia de teclado

## En todas partes

| Tecla | Acción |
|---|---|
| **F10** | barra de menús (abre el primer menú) |
| **Alt+letra** | abre ese menú (Alt+A, Alt+E, Alt+B, Alt+J, Alt+D, Alt+V, Alt+H, Alt+O, Alt+Y; en inglés, las letras rojas de sus menús: ver [[El escritorio\|The Desktop#idioma]]) |
| **F2** / **Ctrl+S** | guardar |
| **F3** | abrir un archivo (Archivo > Abrir carpeta: una carpeta) |
| **Alt+F3** / **Ctrl+W** | cerrar la ventana |
| **F5** | ampliar la ventana |
| **F6** / **Shift+F6** | ventana siguiente / anterior (también Ctrl+PgDn / Ctrl+PgUp) |
| **Alt+1 … Alt+9** | ir a la ventana *n* |
| **Ctrl+B** | ventana de proyecto |
| **Ctrl+P** | ir a archivo (con un `>` delante: los comandos), ver [[Buscar archivos y comandos\|Finding Files and Commands]] |
| **Alt+P** | paleta de comandos |
| **Shift+F2** | buscar en archivos |
| **Ctrl+F9** | ejecutar: renderizar la plantilla, ejecutar el script PHP, ejecutar un [[Flow de Runner\|Running Flows]] (en el depurador: continuar; con el [[Servidor web\|Web Server]] en marcha: abrir la página en el navegador) |
| **Alt+F5** | ventana Salida |
| **Alt+F9** | verificar: cuadro de progreso y después la ventana Mensajes |
| **Alt+F8** / **Alt+F7** | error siguiente / anterior |
| **Ctrl+T** | árbol de datos ⇄ código; en un Flow de Runner, su última vista ([[ventana Flow\|Flow Structure]] o [[diseñador de Flows\|Flow Designer]]) ⇄ código |
| **F1** | ayuda sobre la ventana activa |
| **Shift+F1** / **Ctrl+F1** / **Alt+F1** | índice de la ayuda / buscar tema: el tema de la palabra bajo el cursor, si no Ayuda > Buscar con ella (en PHP con un servidor de lenguaje: qué es el símbolo) / tema anterior |
| **Alt+X** / **Ctrl+Q** | salir |

## Editor

| Tecla | Acción |
|---|---|
| **Ctrl+Space** | autocompletado |
| **Ctrl+A** | seleccionar todo |
| **Ctrl+O** | esquema de la plantilla o del archivo PHP, ver [[Esquema\|Outline]] |
| **Ctrl+Enter** / **Ctrl+J** / Ctrl+clic | ir a la plantilla incluida; en PHP, abrir el archivo que nombra una cadena, o ir a la definición (con un servidor de lenguaje) |
| **Ctrl+F** / **Ctrl+R** | buscar / reemplazar |
| **Ctrl+L** | buscar de nuevo |
| **Ctrl+G** | ir a línea |
| **Ctrl+Z** / **Ctrl+Y** | deshacer / rehacer |
| **Ctrl+X** / **Ctrl+C** / **Ctrl+V** | cortar / copiar / pegar |
| **F7** | en una plantilla: la [[Traza del render\|Render Trace]]; en PHP: trazar dentro, ver abajo |

## Depurador (PHP)

| Tecla | Acción |
|---|---|
| **F8** | pasar por encima (la primera vez arranca el script; con el [[Servidor web\|Web Server]] en marcha, en una de sus páginas: la siguiente petición se detiene) |
| **F7** | trazar dentro |
| **Shift+F8** | salir de la función |
| **F4** | ir al cursor |
| **Ctrl+F9** | ejecutar hasta el siguiente punto de ruptura |
| **Ctrl+F2** | reiniciar programa |
| **Ctrl+F8** | poner o quitar un punto de ruptura |
| **Ctrl+F7** | añadir vigilancia |
| **Ctrl+F4** | evaluar |
| **Ctrl+F3** | pila de llamadas |

## Cuadro de progreso

| Tecla | Acción |
|---|---|
| **Esc** | detener el render o el script mientras se ejecuta |
| cualquier tecla | cerrar el cuadro tras el veredicto (también se cierra solo: a los 2 segundos si todo fue bien, a los 5 con avisos o errores) |

## Listas y árboles

Cada árbol y cada lista tiene encima una línea de filtro, ver [[El escritorio|The Desktop]].

| Tecla | Acción |
|---|---|
| una letra, un dígito, un signo | añadirlo al filtro: solo quedan los elementos que lo contienen (da igual mayúsculas o minúsculas) |
| **Retroceso** | quitar una letra |
| **Esc** | vaciar el filtro (con el filtro vacío, Esc hace lo de siempre) |

## Lista de autocompletado

| Tecla | Acción |
|---|---|
| **↑ ↓ PgUp PgDn** | moverse |
| **Enter** / **Tab** | insertar |
| **Esc** | cerrar |

## Ventana de proyecto

| Tecla | Acción |
|---|---|
| **Enter** / doble clic | abrir un archivo / plegar una carpeta (un clic pone la barra sobre un archivo, y abre o pliega una carpeta); sobre un miembro de un archivo, abrir el archivo allí |
| **→** / **←** | desplegar / plegar una carpeta, o un archivo en sus miembros (en uno plegado, **←** sube a lo que lo contiene) |
| **Ins** | archivo nuevo |
| **F7** | carpeta nueva |
| **F2** | renombrar (una ruta lo mueve: `../nombre`) |
| **Supr** | eliminar |
| **Ctrl+X** / **Ctrl+C** / **Ctrl+V** | cortar / copiar / pegar en la carpeta bajo la barra (**Esc** olvida lo cortado) |
| arrastrar sobre una carpeta | mover allí, tras preguntar |
| **Ctrl+R** | actualizar |
| **Alt+F10** / **Shift+F10** / clic derecho | menú local |

## Árbol de datos

| Tecla | Acción |
|---|---|
| **Enter** | editar elemento |
| **Ins** | añadir elemento |
| **Supr** | eliminar elemento |
| **Ctrl+↑ / Ctrl+↓** | mover elemento |
| **Ctrl+Z / Ctrl+Y** | deshacer / rehacer |
| **F2** | guardar |

## Diseñador de Flows

| Tecla | Acción |
|---|---|
| **flechas** | de Step a Step en un carril, de carril a carril |
| **Inicio / Fin** | el título del carril / su último Step |
| **Tab / Mayús+Tab** | las conexiones de lo elegido |
| **Enter** | seguir la conexión escogida; si no, editar el Step o el Block |
| **Esc** / **Retroceso** | dejar la conexión o la elección de destino / volver |
| **C / J** | conectar un `call` / `jump`: elegir el destino, Enter |
| **X** | el contexto del Step, como árbol o como JSON |
| **F** | los Modules y las Functions del Flow |
| **T** | probar la Function del Step |
| **Ins** / **B** | Step nuevo / Block nuevo |
| **Supr** | borrar el Step o el Block, o quitar la conexión escogida |
| **Ctrl+↑ / Ctrl+↓** | mover el Step dentro de su Block |
| **Ctrl+← / Ctrl+→** | mover el Block |
| **Ctrl+D** | el árbol de la ventana Flow ⇄ el tablero |
| **Ctrl+Z / Ctrl+Y** | deshacer / rehacer |

## Functions del Flow

| Tecla | Acción |
|---|---|
| **Intro** | abrir la Function (en su `return`), ir al Step, o crear la Function que falta |
| **Ins** / **Shift+Ins** | Function nueva (en el Module bajo el cursor) / Module nuevo |
| **Ctrl+F9** | probar la Function: ejecutarla o depurarla con un contexto JSON |
| **Alt+F10** / **Shift+F10** | menú: Function..., Module..., Ajustes (`.div/runner.json`) |
| **Ctrl+R** | leer el disco otra vez |

## Dialector

| Tecla | Acción |
|---|---|
| **↑ ↓** | elegir una sección (la vista previa la sigue) |
| **Enter** / doble clic | editar la sección |
| **Supr** | devolver la sección a los valores por defecto de Div |
| **Ctrl+Z / Ctrl+Y** | deshacer / rehacer |
| **Alt+F10** / **Shift+F10** | menú local: transformar, importar, exportar, ejemplo, traducir |
| **F2** | guardar el archivo de dialecto |

## Diálogos

| Tecla | Acción |
|---|---|
| **Tab** / **Shift+Tab** | control siguiente / anterior |
| **Alt + letra amarilla** | ir a ese control |
| **Enter** | el botón por defecto (también desde una línea de entrada o un grupo de opciones) |
| **Esc** | cancelar |
| **↓** en una línea de entrada con `▐↓▌` | su historial: **↑ ↓** eligen, **Enter** lo pone en la línea, **Esc** lo cierra |

En los diálogos con una ruta, el botón **...** / **Examinar...** abre el diálogo de archivos. Ver [[El escritorio|The Desktop#di%C3%A1logos]].

## Ventana Mensajes

| Tecla | Acción |
|---|---|
| **Enter** / doble clic | ir al lugar del mensaje |

## Ir a archivo y paleta de comandos

| Tecla | Acción |
|---|---|
| letras | deja lo que las tiene, en ese orden |
| **↑ ↓** / **PgUp PgDn** | mover la barra (las teclas se quedan en la línea) |
| `>` al principio | los comandos (al borrarlo: los archivos) |
| **Enter** / doble clic | abrir el archivo / ejecutar el comando |
| **Esc** | cerrar |

## Ventana Buscar en archivos

| Tecla | Acción |
|---|---|
| **Enter** / doble clic | abrir el archivo en la coincidencia, seleccionada |

## Ventana Paquetes Composer

| Tecla | Acción |
|---|---|
| **Ins** | añadir un paquete |
| **Supr** | quitar el paquete |
| **Enter** / doble clic | su carpeta en la ventana de proyecto (en un grupo o un vendor: plegarlo o desplegarlo) |
| **Espacio** / **→** / **←** | plegar / desplegar un grupo o un vendor |
| **Ctrl+R** | leer de nuevo composer.json y composer.lock |
| **Alt+F10** / **Shift+F10** | menú local: actualizar, instalar, versiones nuevas, validar, autoloader, nuevo composer.json |

Ver [[Composer|Composer]].

## Ventana de bienvenida

| Tecla | Acción |
|---|---|
| **Enter** / doble clic | hacerlo: un archivo nuevo, abrir un archivo o una carpeta, la ayuda; abrir la carpeta o el archivo reciente |
| **Supr** | quitar una carpeta o un archivo reciente de su lista |
| escribir | filtrar las filas |

Ver [[El escritorio|The Desktop#una-carpeta-un-archivo-o-nada]].

## Ventanas Git

| Tecla | Acción |
|---|---|
| **Espacio** | Cambios: preparar el archivo o quitarlo (un conflicto: marcarlo resuelto) |
| **Enter** | Cambios: abrir el archivo · Historial: el diff del commit · Ramas: cambiar a ella (un stash: recuperarlo) · Pull requests e issues: abrir en el navegador |
| **Supr** | Cambios: descartar los cambios del archivo · Ramas: borrar la rama, borrar el stash |
| **Ins** | Ramas: una rama nueva · Pull requests e issues: una pull request nueva (en las issues, una issue nueva) |
| **Ctrl+K** | Cambios: hacer commit |
| **Tab** | Cambios: al diff y de vuelta |
| **Ctrl+R** | leer de nuevo |
| **Alt+F10** / **Shift+F10** | menú local: preparar todo, enmendar, stash, fusionar, rama nueva aquí, copiar el hash, pull, push, fetch... |
| **Ctrl+Enter** | en el mensaje del commit: hacer commit |

En un diff: **N** / **P** el cambio siguiente / anterior, **S** lado a lado o unificado, **← →** desplazar una línea larga, **Enter** abrir el archivo en esa línea. En la autoría: **Enter** el commit de la línea.

Ver [[Git]].

## Ventana Configuración de Div

| Tecla | Acción |
|---|---|
| **↑ ↓** | elegir una sección (sus ajustes en vigor se ven al lado) |
| **Enter** / doble clic | editar la sección |
| **Supr** | devolver la sección a los valores por defecto de Div |
| **Ctrl+Z / Ctrl+Y** | deshacer / rehacer |
| **Ctrl+T** | el archivo de configuración como JSON |
| **Alt+F10** / **Shift+F10** | menú local: configuración del usuario o del proyecto, JSON, dialecto, confianza, verificar con Div |
| **F2** | guardar el archivo de configuración |

Ver [[Configuración de Div|Div Setup]].

## Ventana Esquema

| Tecla | Acción |
|---|---|
| **Enter** / doble clic | ir a la parte bajo la barra |
| **Espacio** / clic en **►** **▼** | plegarla o desplegarla |
| **← / →** | plegar / desplegar (a la parte que la contiene / a la primera que contiene) |

Ver [[Esquema|Outline]].

## Ventanas Vigilancias y Pila de llamadas

| Tecla | Acción |
|---|---|
| **Ins** | añadir una vigilancia |
| **Supr** | quitar la vigilancia bajo el cursor |
| **Enter** (Pila de llamadas) | mostrar esa llamada; Vigilancias y Evaluar miran desde ahí |

## Ventana Traza del render

| Tecla | Acción |
|---|---|
| **↑ / ↓** | fila anterior / siguiente |
| **F8** | siguiente fila del mismo análisis (por encima de los sub-análisis) |
| **F7** | siguiente fila (dentro de los sub-análisis) |
| **Shift+F8** | salir al análisis que inició este |
| **Espacio** | la plantilla antes / después de la mutación |

Ver [[Traza del render|Render Trace]].

## Ventana de ayuda

| Tecla | Acción |
|---|---|
| **Tab** / **Shift+Tab** | referencia cruzada siguiente / anterior |
| **Enter** / clic | seguirla (una página web se abre en el navegador) |
| **Alt+F1** / **Backspace** | tema anterior |
| **Esc** | cerrar |

## Ayuda > Buscar

| Tecla | Acción |
|---|---|
| palabras | las secciones que las tienen, las mejores primero |
| **↑ ↓** / **PgUp PgDn** | mover la barra (las teclas se quedan en la línea) |
| **Enter** / doble clic | abrir la ayuda en esa sección |
| **Esc** | cerrar |
