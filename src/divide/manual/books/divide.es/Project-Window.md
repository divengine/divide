# Ventana de proyecto

**Ctrl+B** abre el árbol del proyecto a la izquierda (y lo trae al frente, o lo cierra si ya está encima). Se abre solo cuando divide arranca sin archivos.

![el menú local de la ventana de proyecto](images/project-menu.png)

**Enter** abre un archivo, o pliega y despliega una carpeta. **→** despliega una carpeta (o un archivo, ver abajo) y **←** la pliega, o sube a la carpeta que contiene la barra. Con el ratón, un clic pone la barra sobre un archivo y un doble clic lo abre; un clic en una carpeta la pliega o la despliega. Las carpetas de control de versiones y de caché (`.git`, `__pycache__`, `.venv`, `node_modules`, cachés de herramientas) se ocultan; `vendor/` sigue visible.

![la ventana del proyecto: una carpeta desplegada, un archivo nuevo, las marcas de tipo](images/project.gif)

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
| **F2** | renombrar; el nombre sin su extensión aparece seleccionado. Las ventanas abiertas siguen al archivo. |
| **Supr** | eliminar, tras confirmar. Las carpetas se van con todo lo que contienen (divide te dice cuántos elementos). |
| **Ctrl+R** | actualizar desde el disco |
| **Alt+F10**, **Shift+F10**, clic derecho | el menú local con todo lo anterior |

![creando un archivo](images/project-new-file.png)

Conviene saber:

- Eliminar es permanente (nada va a una papelera), por eso divide siempre pregunta.
- Las ventanas de archivos eliminados se cierran, salvo las que tienen cambios sin guardar: tu trabajo sigue abierto y puede guardarse de nuevo.
- Un archivo de datos elegido con Ejecutar > Archivo de datos sigue con su plantilla cuando se renombra cualquiera de los dos.
- Se rechazan los nombres que saldrían del proyecto (`../x`).
- Los archivos creados fuera de divide aparecen con Ctrl+R; los creados con Guardar como aparecen solos.
- Después de cualquiera de estas operaciones, los includes se verifican de nuevo (ver [[Verificación de plantillas|Checking Templates]]).
