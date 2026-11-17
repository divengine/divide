# El escritorio

divide es un escritorio Turbo Vision: una barra de menús arriba, ventanas superpuestas en el centro y una línea de estado abajo. Si usaste Turbo Pascal o Borland C++, tus dedos ya lo conocen.

![Ventana > Mosaico con el proyecto, una plantilla y un componente](images/window-tile.png)

## Menús

**F10** abre el primer menú, **Alt + la letra roja** abre un menú directamente (Alt+A Archivo, Alt+J Ejecutar, Alt+H Herramientas, Alt+V Ventana…). Dentro de un menú, las flechas mueven, la letra roja o **Enter** eligen y **Esc** cierra. El ratón también funciona.

![el menú Ejecutar](images/menu-run.png)

| Menú | Qué hay |
|---|---|
| **Archivo** | Nuevo, Abrir (F3), Guardar (F2), Guardar como, Guardar todo, Salir (Alt+X) |
| **Editar** | Deshacer, Rehacer, Cortar, Copiar, Pegar, Seleccionar todo, Completar (Ctrl+Space) |
| **Buscar** | Buscar, Reemplazar, Buscar de nuevo, Buscar en archivos (Shift+F2), Ir a línea, Ir a la plantilla incluida, Esquema (Ctrl+O: ver [[Esquema\|Outline]]), Ir a archivo (Ctrl+P), Paleta de comandos (Alt+P): ver [[Buscar archivos y comandos\|Finding Files and Commands]], Error anterior / Error siguiente |
| **Ejecutar** | Ejecutar (Ctrl+F9: renderizar una plantilla, ejecutar un script PHP), Pasar por encima (F8), Trazar dentro (F7), Salir de la función, Ir al cursor (F4), Reiniciar programa (Ctrl+F2), Argumentos, Ejecutar en terminal, Servidor web, Verificar (Alt+F9), Salida, Archivo de datos, Editar datos, Árbol de datos (Ctrl+T) |
| **Depurar** | Evaluar (Ctrl+F4), Vigilancias, Pila de llamadas (Ctrl+F3), Añadir vigilancia (Ctrl+F7), Punto de ruptura (Ctrl+F8): ver [[Depurar PHP\|Debugging PHP]]; Traza del render: ver [[Traza del render\|Render Trace]] |
| **Herramientas** | Dialector, Traducir una plantilla, [[Paquetes Composer\|Composer]] |
| **Ventana** | Proyecto (Ctrl+B), Mensajes, Mosaico, Cascada, Zoom, Siguiente, Anterior, Cerrar, Cerrar todas |
| **Opciones** | Colores (el tema y la profundidad de color), Idioma (de la interfaz), símbolos simples o marcas de tipo de archivo, servidores de lenguaje, motor Div, [[configuración de Div\|Div Setup]], Xdebug |
| **Ayuda** | Contenido, Libros, Índice (Shift+F1), Buscar tema (Ctrl+F1), Buscar (en los libros por palabras, por relevancia), Tema anterior (Alt+F1), Uso de la ayuda (F1), Acerca de: ver [[Ayuda\|Help]] |

## Ventanas

Cada ventana tiene un número en su borde superior (**Alt+1…9** va a ella) y, en los editores, `* line:col` en el borde inferior, donde `*` indica cambios sin guardar.

- **F6** / **Shift+F6** (también Ctrl+PgDn / Ctrl+PgUp): ventana siguiente / anterior.
- **F5**: amplía la ventana a todo el escritorio y la devuelve a su tamaño.
- **Alt+F3** o **Ctrl+W**: la cierra (divide pregunta por los cambios sin guardar).
- Arrastra una ventana por su título, cambia su tamaño desde una esquina inferior, haz clic en `[■]` para cerrarla y en `[▲]` para ampliarla.
- **Ventana > Mosaico** coloca todas las ventanas en una cuadrícula; **Cascada** las apila.

Las barras de desplazamiento están en el borde de la ventana activa, como en Turbo Pascal: la vertical en el borde derecho (`▲ ▒ ■ ▼`), la horizontal en el borde inferior después del `line:col` (`◄ ▒ ■ ►`), así el texto conserva la columna y la fila que ocuparía una barra dentro de la ventana. Una flecha mueve una línea, un clic en la pista una página, y el `■` se puede arrastrar; el foco se queda en el texto. Las ventanas en segundo plano muestran un borde simple, y una barra solo aparece cuando hay algo que desplazar.

Tipos de ventanas: editores (plantillas, datos, PHP y los [[otros archivos|Other Files]] de un proyecto: HTML, CSS, JavaScript, Markdown, YAML, CSV…), la [[Ventana de proyecto|Project Window]], la Salida de un render o de un script, la ventana Mensajes, las ventanas Vigilancias y Pila de llamadas del [[depurador|Debugging PHP]], el registro del [[Servidor web|Web Server]], el árbol de datos, el [[Dialector|Dialector]] y la ventana de [[Ayuda|Help]].

## Línea de estado

El lado izquierdo muestra las teclas que importan. El lado derecho te informa sobre la ventana en la que estás:

- en una plantilla, `Div` (más el nombre del dialecto cuando no es el de por defecto), o el error o aviso bajo el cursor, o la cuenta de problemas;
- en un archivo de datos, `JSON correcto` o el error de JSON con su línea y columna;
- en cualquier otro archivo, su lenguaje (`Markdown`, `YAML`, `CSV`…);
- en la ventana Salida, qué plantilla y qué archivo de datos se renderizaron, o qué script se ejecutó y su código de salida, y cuánto tardó;
- mientras depuras, dónde está pausado el script y las teclas del depurador;
- en la ventana de proyecto, el dialector y la ventana de ayuda, sus teclas;
- mientras algo se ejecuta en segundo plano (un render, por ejemplo), un indicador que gira (`|` `/` `-` `\`) y lo que se está ejecutando.

## Diálogos

Los diálogos funcionan como en Turbo Vision: **Tab** / **Shift+Tab** van de un control al siguiente, **Alt + la letra amarilla** salta a un control, **Enter** pulsa el botón por defecto (también desde una línea de entrada o un grupo de opciones), **Esc** cancela.

**Archivo > Abrir** (F3) y **Guardar como** están dispuestos como los de Turbo Pascal: la línea del nombre arriba, los archivos de la carpeta debajo sobre cian con su propia barra de desplazamiento, los botones en una columna a la derecha, y un panel abajo con la carpeta (y su comodín) y el archivo bajo la barra, con su tamaño y fecha. Escribe un comodín (`*.php`) para listar otros archivos, el nombre de una carpeta o `..` para ir allí, o una ruta completa.

![Archivo > Abrir](images/open-file.png)

### Historial de las líneas de entrada

Las líneas de entrada recuerdan lo que aceptaste en ellas, como en Turbo Pascal: el `▐↓▌` a la derecha de una línea abre las entradas anteriores, la más reciente primero. **↓** en la línea (o un clic en la flecha) abre la lista, **Enter** o un clic devuelve una entrada a la línea, **Esc** cierra la lista. Cada tipo de línea tiene su propio historial: nombres de archivo, textos a buscar y a reemplazar, números de línea, los argumentos de un programa, expresiones a vigilar… Una entrada se recuerda cuando el diálogo termina con OK, no con Cancelar, y los historiales se guardan en la configuración para la siguiente sesión.

![el historial del nombre de archivo](images/open-history.png)

## Colores

**Opciones > Colores** elige el tema de colores:

| Tema | Aspecto |
|---|---|
| **Turbo Pascal** (el de por defecto) | los colores de Turbo Vision: menús y diálogos grises, ventanas azules, texto amarillo |
| **Turbo C** | lo mismo, con las teclas rápidas de menú blanco sobre negro de Turbo C 2.01 |
| **Free Pascal** | la disposición de Turbo Vision con los colores Campbell de Windows Terminal, como se ve hoy el IDE de Free Pascal en Windows |
| **Moderno oscuro** | grises profundos, texto claro y un acento azul, alto contraste |

Al recorrer los temas con las flechas, todo el escritorio se pinta en cada uno (también el diálogo y su muestra de una plantilla). **OK** conserva el tema, también para el próximo inicio; **Cancelar** vuelve al que tenías. `divide --palette modern-dark` arranca con un tema sin cambiar el elegido. Las imágenes de este manual usan el tema Free Pascal.

![Opciones > Colores, con la vista previa de Moderno oscuro](images/colors-dialog.png)

![Moderno oscuro](images/theme-modern-dark.png)

![Turbo Pascal](images/theme-turbo-pascal.png)

![Colores de Turbo C y el menú Ventana](images/palette-turbo-c.png)

### Profundidad de color

divide envía sus colores según el terminal dice que puede mostrarlos: color real cuando lo anuncia (`COLORTERM=truecolor`, Windows Terminal, iTerm2, la mayoría de los terminales de Linux), la paleta de 256 colores si no (`TERM=xterm-256color`), y los 16 colores ANSI en un terminal básico. En 16 colores cada color pasa al que representa en su tema (un verde claro sigue siendo verde claro). El sistema operativo no interviene, solo lo que dice el terminal.

Por ssh o dentro de tmux `COLORTERM` suele perderse y el terminal parece uno de 256 colores. Si puede hacerlo mejor, elige **Color real** en **Profundidad de color** en **Opciones > Colores** (se aplica desde el próximo inicio), o arranca con `divide --colors truecolor`. El diálogo indica lo que recibe ahora el terminal.

## Idioma

divide habla inglés y español. Toma el idioma del sistema (`LANG`, `LC_ALL`…) cuando lo tiene, inglés si no. **Opciones > Idioma** elige otro, y divide lo recuerda; se aplica desde el próximo inicio.

![Opciones > Idioma](images/language-dialog.png)

Los menús, diálogos, pistas, mensajes y la línea de estado están traducidos, con teclas rápidas propias en cada idioma (**Alt+A** abre *Archivo*, **Alt+J** abre *Ejecutar*). Las teclas de los comandos no cambian: **F2** guarda y **Ctrl+F9** ejecuta en cualquier idioma. La ayuda sigue a la interfaz: en español, el manual y la documentación de Div se muestran en español (ver [[Ayuda|Help#la-ayuda-en-español]]).

![el menú Ejecutar en español](images/interface-spanish.png)

Para usar otro idioma en una sola ejecución, arranca con `divide --language es` (o `--language en`); la variable `DIVIDE_LANGUAGE` hace lo mismo y se impone a todo lo demás.
