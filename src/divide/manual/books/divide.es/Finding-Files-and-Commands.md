# Buscar archivos y comandos

Tres formas de llegar a algún sitio sin los menús ni el árbol del proyecto: **Ir a archivo** abre un archivo escribiendo unas pocas letras de su nombre, la **paleta de comandos** ejecuta cualquier entrada del menú de la misma forma, y **Buscar en archivos** busca un texto en todos los archivos del proyecto.

![ir a un archivo, la paleta de órdenes, buscar en archivos](images/finding.gif)

## Ir a archivo

**Ctrl+P** (o **Buscar > Ir a archivo**) abre una línea donde escribir, con los archivos del proyecto debajo. Escribe unas pocas letras del nombre y la lista se queda con los archivos que las tienen, en ese orden, los mejores primero. Las letras que escribiste aparecen resaltadas, y las carpetas se atenúan para que destaquen los nombres de los archivos.

![Ir a archivo](images/go-to-file.png)

- Las letras no tienen que estar juntas: `phd` encuentra `parts/header.tpl`. Un archivo cuyo nombre las tiene al principio de sus palabras, o una tras otra, sale primero.
- Sin nada escrito, primero salen los archivos abiertos en editores, el de encima primero.
- **↑ ↓** (y **PgUp PgDn**) mueven la barra mientras sigues escribiendo. **Enter** o un doble clic abre el archivo, **Esc** cierra.
- Cuando el proyecto es un repositorio git, la lista es la del propio git: los archivos rastreados y los nuevos que git no ignora. Si no, contiene todos los archivos excepto las carpetas que oculta la [[Ventana de proyecto|Project Window]] (`.git`, `node_modules`, `.venv`, cachés).

## Paleta de comandos

**Alt+P** (o **Buscar > Paleta de comandos**) contiene todas las entradas de la barra de menús, nombradas por su menú (`Run > Check`), con su tecla a la derecha. Funciona como Ir a archivo: escribe unas pocas letras y **Enter** ejecuta el comando, como si lo hubieras elegido en el menú.

![la paleta de comandos](images/command-palette.png)

- Un `>` al principio de la línea en Ir a archivo la convierte en la paleta de comandos, y borrar el `>` vuelve a los archivos.
- VS Code abre su paleta con Ctrl+Shift+P, pero Windows Terminal reserva esa tecla para su propia paleta, y muchos terminales la envían como Ctrl+P. Por eso divide usa Alt+P. Donde el terminal sí deja pasar Ctrl+Shift+P, también funciona.
- Sin nada escrito, primero salen los comandos que ejecutaste desde la paleta más recientemente.

## Buscar en archivos

**Buscar > Buscar** busca en el archivo que estás editando. **Buscar > Buscar en archivos** (**Shift+F2**, la tecla de Tools > Grep de Borland Pascal) busca en todos los archivos del proyecto: la misma lista que Ir a archivo. Ctrl+Shift+F de VS Code es la búsqueda propia de Windows Terminal, así que solo es una alternativa, para los terminales que la dejan pasar.

![Buscar en archivos](images/find-in-files-dialog.png)

- **Texto a buscar**: lo que hay que buscar. Cuando hay texto seleccionado en una línea, se rellena con él.
- **Archivos**: en qué archivos buscar, con comodines separados por `;` (`*.tpl;*.php`). Deja `*` para todos. Un comodín también puede incluir carpetas: `components/*`.
- **Opciones**: mayúsculas y minúsculas, palabras completas y expresión regular, como en **Buscar**.

Las dos líneas recuerdan lo que escribiste en ellas (consulta [[El escritorio|The Desktop#historial-de-las-l%C3%ADneas-de-entrada]]). Los archivos abiertos en editores se buscan tal como están, guardados o no. Los archivos binarios y los de más de 2 MB se omiten.

Lo que encuentra va a la ventana **Buscar en archivos**, abajo en el escritorio, como el grep de Turbo Pascal lo ponía en la ventana Mensajes. La primera línea dice cuántas coincidencias encontró y en cuántos archivos. Después hay una fila por cada línea con una coincidencia: `file(line): the line`. **Enter** o un doble clic abre el archivo ahí, con la coincidencia seleccionada. Hacer otra búsqueda reemplaza la lista.

![la ventana Buscar en archivos](images/find-in-files.png)
