# Edición de PHP

Los archivos que terminan en `.php` (y `.phtml`) se abren en un editor de PHP: el código que llama a Div está junto a las plantillas, en el mismo escritorio.

![un archivo PHP con un error de sintaxis encontrado por PHP](images/php.png)

## Resaltado

Los colores vienen de la gramática de PHP de [tree-sitter](https://tree-sitter.github.io/), la misma que usan muchos editores. En la paleta Borland, las palabras reservadas son blancas, las variables cian claro como las de Div, las cadenas verde claro, los comentarios gris claro y las etiquetas `<?php` rojo claro. El HTML fuera de las etiquetas de PHP queda sin colorear.

## Errores del propio PHP

divide no juzga el código PHP: lo hace PHP. Cuando dejas de escribir un momento, divide pasa el buffer (guardado o no) a `php -l`, la verificación de sintaxis del propio PHP, y muestra su respuesta:

- la línea que señala PHP se pinta de rojo;
- la línea de estado da el mensaje de PHP;
- **Alt+F9** vuelve a preguntar a PHP bajo el cuadro de progreso y lista el error en la ventana Mensajes, **Enter** salta a él, **Alt+F8** / **Alt+F7** recorren los errores, como con las plantillas (consulta [[Verificación de plantillas|Checking Templates]]).

PHP se detiene en el primer error de sintaxis, así que hay uno cada vez. `php` debe estar en el `PATH`; sin él, la línea de estado dice que el archivo no se verifica.

## Esquema

**Ctrl+O** (Buscar > Esquema) lista las clases, métodos, propiedades y funciones del archivo en una ventana a la derecha; **Enter** va a uno de ellos. Consulta [[Esquema|Outline]].

## Abrir el archivo que nombra una cadena

Pon el cursor sobre una cadena que nombra un archivo y pulsa **Ctrl+Enter** (o Ctrl+clic): `new div('index.tpl', $data)` abre la plantilla, `require 'menu.php'` abre `menu.php`. divide busca junto al archivo PHP, luego en la carpeta del proyecto, y prueba también el nombre con `.tpl`.

## Con un servidor de lenguaje

Con [phpactor](https://phpactor.readthedocs.io) o [intelephense](https://intelephense.com) instalado, el editor de PHP completa funciones, clases y métodos con su documentación, muestra la firma de la llamada que estás escribiendo, muestra qué es un símbolo (**Ctrl+F1**), va a su definición (**Ctrl+Enter**) y añade los avisos del servidor a los errores de PHP. Consulta [[Servidores de lenguaje|Language Servers]].

## Ejecución y depuración

**Ctrl+F9** ejecuta el script y muestra lo que imprimió y los errores de PHP con su lugar (consulta [[Ejecutar PHP|Running PHP]]). **F8**, **F7** y **Ctrl+F8** lo recorren paso a paso con Xdebug, con puntos de ruptura, vigilancias y la pila de llamadas (consulta [[Depurar PHP|Debugging PHP]]).

Todo lo demás es el mismo editor que para las plantillas: buscar y reemplazar, las teclas de edición, deshacer (consulta [[Edición de plantillas|Editing Templates]]).
