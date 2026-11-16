# Ventana de proyecto

**Ctrl+B** abre el árbol del proyecto a la izquierda (y lo trae al frente, o lo cierra si ya está encima). Se abre solo cuando divide arranca sin archivos.

![el menú local de la ventana de proyecto](https://raw.githubusercontent.com/wiki/divengine/divide/images/project-menu.png)

**Enter** abre un archivo, o pliega y despliega una carpeta. Con el ratón, un clic pone la barra sobre un archivo y un doble clic lo abre; un clic en una carpeta la pliega o la despliega. Las carpetas de control de versiones y de caché (`.git`, `__pycache__`, `.venv`, `node_modules`, cachés de herramientas) se ocultan; `vendor/` sigue visible.

## Marcas de tipo de archivo

El árbol muestra las carpetas con los `►` y `▼` de Turbo Vision. **Opciones > Marcas de tipo de archivo** pone una marca de color delante de cada archivo, en la celda donde una carpeta tiene su flecha, así que el árbol mantiene su ancho. **Opciones > Símbolos simples** vuelve atrás. divide recuerda la elección.

![la ventana de proyecto con marcas de tipo de archivo](https://raw.githubusercontent.com/wiki/divengine/divide/images/project-marks.png)

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

![creando un archivo](https://raw.githubusercontent.com/wiki/divengine/divide/images/project-new-file.png)

Conviene saber:

- Eliminar es permanente (nada va a una papelera), por eso divide siempre pregunta.
- Las ventanas de archivos eliminados se cierran, salvo las que tienen cambios sin guardar: tu trabajo sigue abierto y puede guardarse de nuevo.
- Un archivo de datos elegido con Ejecutar > Archivo de datos sigue con su plantilla cuando se renombra cualquiera de los dos.
- Se rechazan los nombres que saldrían del proyecto (`../x`).
- Los archivos creados fuera de divide aparecen con Ctrl+R; los creados con Guardar como aparecen solos.
- Después de cualquiera de estas operaciones, los includes se verifican de nuevo (ver [[Verificación de plantillas|Checking Templates]]).
