# Ventana de proyecto

**Ctrl+B** abre el árbol del proyecto a la izquierda (y lo trae al frente, o lo cierra si ya está encima). Se abre solo cuando divide arranca con una carpeta y sin archivos. Sin carpeta, Ctrl+B ofrece abrir una (**Archivo > Abrir carpeta**).

![el menú local de la ventana de proyecto](images/project-menu.png)

**Enter** abre un archivo, o pliega y despliega una carpeta. **→** despliega una carpeta (o un archivo, ver abajo) y **←** la pliega, o sube a la carpeta que contiene la barra. Con el ratón, un clic pone la barra sobre un archivo y un doble clic lo abre; un clic en una carpeta la pliega o la despliega. Las carpetas de control de versiones y de caché (`.git`, `__pycache__`, `.venv`, `node_modules`, cachés de herramientas) se ocultan; `vendor/` sigue visible.

Escribe con el árbol enfocado y solo quedan los archivos y carpetas cuyo nombre lo contiene, de todo el proyecto, también de carpetas que nunca abriste (ver [[El escritorio|The Desktop]]). **Esc** vacía el filtro.

![la ventana del proyecto: una carpeta desplegada, un archivo nuevo, las marcas de tipo](images/project.gif)

En un repositorio git cada archivo cambiado lleva una letra tras su nombre (`M`, `A`, `?`...), una carpeta con cambios lleva `•`, los archivos ignorados se ven atenuados y el borde inferior muestra la rama: ver [[Git]].

## Los miembros de un archivo

Un archivo de un lenguaje con [[esquema|Outline]] (plantillas, PHP, HTML, Markdown, CSS, JavaScript, SQL, JSON, YAML...) también lleva un `►`: desplegado, muestra sus miembros debajo, el mismo árbol que **Buscar > Esquema**: un archivo PHP sus clases, sus métodos y propiedades, sus funciones; una plantilla sus etiquetas; un archivo Markdown sus encabezados; un archivo JSON sus claves...

- **→** o un clic en el `►` despliega el archivo, sin abrirlo; una clase o un bloque se despliega igual. Un archivo con una sola clase o un solo espacio de nombres lo muestra ya desplegado.
- **Enter** o un doble clic sobre un miembro abre el archivo con ese miembro seleccionado. Sobre el archivo, Enter lo abre, como siempre.
- Los miembros se leen al desplegar el archivo: de su ventana si está abierto (también los cambios sin guardar), del disco si no. Guardar el archivo los actualiza, conservando lo desplegado.
- **F2** y **Supr** sobre un miembro no le hacen nada al archivo: solo renombran y eliminan archivos y carpetas.

Con las marcas de tipo de archivo (abajo), un archivo que se despliega muestra su marca mientras está plegado, y `▼` del color de la marca mientras está desplegado; un clic en la marca lo despliega.

## Marcas de tipo de archivo

El árbol muestra las carpetas con los `►` y `▼` de Turbo Vision. **Opciones > Marcas de tipo de archivo** pone una marca de color delante de cada archivo, en la celda donde una carpeta tiene su flecha, así que el árbol mantiene su ancho. **Opciones > Símbolos simples** vuelve atrás. divide recuerda la elección.

![la ventana de proyecto con marcas de tipo de archivo](images/project-marks.png)

| Marca | Archivos |
|---|---|
| `{` | plantillas Div (`.tpl`, `.div`) |
| `%` | dialectos |
| `?` | PHP (`<?php`) |
| `:` | JSON |
| `#` | Markdown |
| `<` | HTML, XML |
| `*` | CSS |
| `;` | JavaScript |
| `@` | Python |
| `$` | scripts de shell |
| `^` | imágenes |
| `&` | `composer.json`, `composer.lock` |
| `!` | `.gitignore` |
| `-` | cualquier otro archivo |

Las marcas son ASCII simple a propósito: todos los terminales, fuentes y plataformas las dibujan con una celda de ancho, así que nunca pueden desplazar una línea ni romper un marco, aquí o por SSH.

## Trabajar con archivos

| Tecla | |
|---|---|
| **Ins** | archivo nuevo en la carpeta bajo el cursor; `parts/menu.tpl` crea también `parts/`. El archivo se abre. |
| **F7** | carpeta nueva; se admiten rutas anidadas como `assets/css` |
| **F2** | renombrar; el nombre sin su extensión aparece seleccionado. Una ruta también lo mueve: `../nombre`, `parts/nombre`. Las ventanas abiertas siguen al archivo. |
| **Supr** | eliminar, tras confirmar. Las carpetas se van con todo lo que contienen (divide te dice cuántos elementos). |
| **Ctrl+R** | actualizar desde el disco (los cambios hechos fuera de divide se ven solos; ver abajo) |
| **Ctrl+X**, **Ctrl+C**, **Ctrl+V** | cortar, copiar, pegar (ver Mover archivos y carpetas, abajo) |
| **Alt+F10**, **Shift+F10**, clic derecho | el menú local con todo lo anterior |

![creando un archivo](images/project-new-file.png)

Conviene saber:

- Eliminar es permanente (nada va a una papelera), por eso divide siempre pregunta.
- Las ventanas de archivos eliminados se cierran, salvo las que tienen cambios sin guardar: tu trabajo sigue abierto y puede guardarse de nuevo.
- Un archivo de datos elegido con Ejecutar > Archivo de datos sigue con su plantilla cuando se renombra cualquiera de los dos.
- Se rechazan los nombres y rutas que saldrían del proyecto.
- Después de cualquiera de estas operaciones, los includes se verifican de nuevo (ver [[Verificación de plantillas|Checking Templates]]).

## Cambios hechos fuera de divide

Los archivos y carpetas que otros programas crean, borran, renombran o mueven aparecen solos en la ventana de proyecto, normalmente en menos de medio segundo. Eso incluye git, Composer, un generador, una terminal u otro editor. Un archivo movido de una carpeta abierta a otra sale de la primera y aparece en la segunda.

- **Qué se vigila**: la carpeta del proyecto y las carpetas que tienes abiertas en el árbol, cada una por sí sola, sin sus subcarpetas. Una carpeta cerrada se lee al abrirla, así que siempre muestra lo que tiene en ese momento.
- **No pierdes tu sitio**: la barra sigue en el mismo archivo, las carpetas abiertas siguen abiertas, la vista no se desplaza y el filtro que escribiste se mantiene.
- **No se sondea nada**: divide usa las notificaciones del propio sistema (inotify en Linux, FSEvents en macOS, las notificaciones de cambios de carpeta en Windows). Mientras no cambia nada, no pasa nada. Una ráfaga de cambios, como un checkout o un `composer install`, se agrupa, y cada carpeta afectada se lee una vez.
- **Los editores abiertos no se tocan**: un archivo cambiado fuera de divide no recarga su ventana de edición, así que nunca se pisan cambios sin guardar.
- **Límites**:
  - Se vigilan como mucho 64 carpetas a la vez. Con más abiertas, divide lo dice, y el resto se actualiza con **Ctrl+R**.
  - Si el sistema se niega a vigilar una carpeta, divide lo dice una vez, y **Ctrl+R** actualiza. Pasa al llegar a los límites de inotify en Linux (`fs.inotify.max_user_watches`, `max_user_instances`), o en un sistema de archivos sin notificaciones, como muchas unidades de red, SSHFS, algunos volúmenes de Docker o la vista que WSL tiene de las unidades de Windows.
  - Por SSH no cambia nada: divide vigila la máquina en la que se ejecuta.

## Mover archivos y carpetas

![cortar y pegar, Mover a... y arrastrar sobre una carpeta](images/moving.gif)

Tres formas, la que te quede más a mano:

- **Cortar y pegar.** **Ctrl+X** sobre un archivo o una carpeta lo corta: queda tenue en el árbol hasta que va a algún sitio. **Ctrl+V** con la barra sobre una carpeta lo mueve a esa carpeta; sobre un archivo, a la carpeta de ese archivo. **Esc** olvida lo cortado.
- **Copiar y pegar.** **Ctrl+C** copia, **Ctrl+V** pega una copia; lo copiado se puede pegar otra vez, en tantas carpetas como quieras. Pegada en su propia carpeta, la copia se llama `nombre copy` (`nombre copy 2`...).
- **Mover a...** en el menú local (**Alt+F10**): escribe una carpeta del proyecto o elígela con **Examinar**; si la carpeta aún no existe, se crea. **F2** hace lo mismo con una ruta: `../card.tpl`, `parts/card.tpl`.
- **Con el ratón.** Arrastra un archivo o una carpeta sobre una carpeta: la carpeta se resalta mientras avanzas, y el árbol se desplaza al llegar arriba o abajo. Al soltar, divide pregunta antes de moverlo, porque en un terminal es fácil que un arrastre se escape. **Esc** durante el arrastre lo cancela. Tu terminal tiene que informar del movimiento del ratón con el botón pulsado (casi todos lo hacen).

El menú local y **Editar > Cortar / Copiar / Pegar** hacen lo mismo cuando la ventana de proyecto es la activa.

Conviene saber:

- Una carpeta nunca va dentro de sí misma, y dos carpetas nunca se fusionan: si ya hay una carpeta con ese nombre, divide lo dice y no hace nada.
- Un archivo que ya existe con ese nombre solo se reemplaza tras preguntar. Nunca se reemplaza un archivo abierto en una ventana con cambios sin guardar.
- Las ventanas abiertas, el archivo de datos elegido para una plantilla y los puntos de ruptura siguen a lo que se movió; la barra también.
- Mover nunca saca nada del proyecto.
