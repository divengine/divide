# divide

**El IDE de plantillas Div que vive en tu terminal.**

divide es un IDE a pantalla completa, pensado para el teclado, para plantillas [Div](https://github.com/divengine/div), hecho con el espíritu de los IDE de Borland: un escritorio de ventanas superpuestas, menús desplegables, diálogos con sombra y una línea de estado que siempre te dice la tecla siguiente. Entiende Div como lo entiende Div: lee tu dialecto, verifica tus plantillas mientras escribes, autocompleta tus variables a partir de tus datos reales y renderiza con el motor Div real, junto al código.

![divide: proyecto, plantilla y salida renderizada lado a lado](images/hero.png)

## Por qué divide

- **Habla Div.** Cada etiqueta del lenguaje se resalta en el dialecto propio de tu plantilla (`@_DIALECT`), no en un modo HTML genérico con llaves.
- **Errores antes de renderizar.** Bucles sin cerrar, `[/$x]` huérfanos, condiciones sin `{/?}`, JSON roto en `{= x: … =}`, includes que Div no puede resolver: se pintan en el editor y se listan en una ventana Mensajes al estilo de Turbo Pascal.
- **Autocompletado desde tus datos.** Escribe `{$` y elige entre las claves de `page.json`; dentro de `[$products]` tienes los campos de un producto, el nombre del elemento y los `_index`, `_is_last`… de Div. Escribe `[$` y el bucle se cierra solo.
- **El motor real, no una imitación.** Ctrl+F9 renderiza con PHP y Div con tus cambios sin guardar; los includes se resuelven con el propio `getTplPath()` de Div; los datos se decodifican con el propio `jsonDecode()` de Div.
- **Datos como código o como árbol.** El JSON de Div (referencias, comentarios, comillas simples) se resalta y se valida; Ctrl+T convierte el mismo búfer en un árbol que puedes editar con diálogos.
- **Tus propios dialectos, con un asistente.** El [[Dialector|Dialector]] construye un dialecto de Div sección a sección, con una vista previa en vivo y el veredicto de Div en cada cambio. Un asistente traduce plantillas de un dialecto a otro con el propio traductor de Div.
- **PHP junto a las plantillas.** Los archivos `.php` se resaltan con la gramática PHP de tree-sitter y los verifica el propio PHP (`php -l`) mientras escribes; Ctrl+Enter sobre `new div('page.tpl')` abre la plantilla. Con phpactor o intelephense, también autocompletado, definiciones y sus avisos: ver [[Edición de PHP|Editing PHP]] y [[Servidores de lenguaje|Language Servers]].
- **Ejecuta y depura PHP, a la manera de Turbo Pascal.** Ctrl+F9 ejecuta el script bajo un cuadro de progreso y lista los errores de PHP con su lugar; F7 / F8 lo recorren paso a paso con Xdebug, con puntos de ruptura, vigilancias y la pila de llamadas: ver [[Ejecutar PHP|Running PHP]] y [[Depurar PHP|Debugging PHP]]. Ejecutar > Servidor web sirve el proyecto con `php -S` y depura sus peticiones del mismo modo: ver [[Servidor web|Web Server]].
- **Mira cómo llegó Div hasta ahí.** Depurar > Traza del render reproduce cada mutación que Div hizo a una plantilla, con las palabras de Div, con lo que cada una escribió y quitó, hasta el punto fijo: ver [[Traza del render|Render Trace]].
- **También el resto del proyecto.** Los archivos HTML, CSS, JavaScript, Markdown, SQL, XML, YAML, TOML, scripts de shell, `.env`, `php.ini` y CSV se abren con sus colores: ver [[Otros archivos|Other Files]].
- **Una ventana de proyecto que hace cosas.** Crea, renombra y elimina archivos y carpetas sin salir del IDE.
- **Funciona dondequiera que haya un terminal**: por SSH, dentro de tmux, en el servidor donde viven las plantillas. En inglés o en español (Opciones > Idioma).

## Empieza aquí

1. [[Instalación|Installation]]: Python, PHP y Div.
2. [[Primeros pasos|Getting Started]]: un recorrido de cinco minutos.
   ¿Nuevo en Div? Su lenguaje se describe en la [documentación de Div](https://github.com/divengine/div/tree/master/docs), que también está dentro de divide: ver [[Ayuda|Help]].
3. Después, los capítulos: [[El escritorio|The Desktop]], [[Edición de plantillas|Editing Templates]], [[Edición de PHP|Editing PHP]], [[Esquema|Outline]], [[Servidores de lenguaje|Language Servers]], [[Autocompletado|Completion]], [[Verificación de plantillas|Checking Templates]], [[Renderizado|Rendering]], [[Traza del render|Render Trace]], [[Ejecutar PHP|Running PHP]], [[Depurar PHP|Debugging PHP]], [[Servidor web|Web Server]], [[Archivos de datos|Data Files]], [[Otros archivos|Other Files]], [[Ventana de proyecto|Project Window]], [[Dialector|Dialector]], [[Traducir plantillas|Translating Templates]].
4. [[Referencia de teclado|Keyboard Reference]] y [[Solución de problemas|Troubleshooting]] cuando los necesites.

El manual completo también está dentro de divide: pulsa **F1** (ver [[Ayuda|Help]]).

divide es parte de [Divengine](https://github.com/divengine). Código fuente: [divengine/divide](https://github.com/divengine/divide).
