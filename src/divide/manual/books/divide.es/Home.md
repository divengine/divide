# divide

**Un IDE para desarrollar generadores con el ecosistema Divengine.**

divide es un entorno de desarrollo especializado para construir, probar, depurar y mantener generadores que usan las bibliotecas de [Divengine](https://github.com/divengine). Un generador es un proyecto propio que transforma modelos de entrada en código fuente, configuración, plantillas u otros artefactos mediante reglas explícitas y reutilizables, por ejemplo con plantillas de [Div](https://github.com/divengine/div) y sus datos. Lo desarrollas en divide; el generador terminado se despliega y se ejecuta sin divide.

Podrías escribir el mismo software en cualquier editor. Lo que aporta divide es el conocimiento del ecosistema: edición que entiende Div en el dialecto de cada plantilla, la configuración de Div del proyecto para el diseño, render y verificación con el motor real, y la traza de cómo llegó Div a su salida. La generación determinista de código es un caso de uso central: ver [[Los generadores y lo que no está decidido|Home#los-generadores-y-lo-que-no-está-decidido]].

Está hecho con el espíritu de los IDE de Borland: un escritorio de ventanas superpuestas, menús desplegables, diálogos con sombra y una línea de estado que siempre te dice la tecla siguiente. El nombre es *div* + *ide*, y la palabra inglesa *divide*.

![divide: proyecto, plantilla y salida renderizada lado a lado](images/hero.png)

## Lo que puedes hacer hoy

Los ejemplos del manual generan HTML, la salida más fácil de leer; las mismas herramientas sirven para plantillas que generan código o cualquier otro texto.


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
- **Div configurado para el diseño.** El `.div/setup.json` del proyecto le da al Div que ejecuta divide sus carpetas, dialecto, datos globales y funciones permitidas mientras trabajas. No configura el Div que ejecuta tu aplicación en producción: ver [[Configuración de Div|Div Setup]].
- **Control de versiones y paquetes.** El menú Git muestra los cambios, los diffs, el historial, las ramas y el blame, y los pull requests de GitHub o Gitea: ver [[Git|Git]]. Herramientas > Paquetes Composer gestiona los paquetes PHP del proyecto: ver [[Composer|Composer]].
- **Una ventana de proyecto que hace cosas.** Crea, renombra, mueve y elimina archivos y carpetas sin salir del IDE.
- **Funciona dondequiera que haya un terminal**: por SSH, dentro de tmux, en el servidor donde viven las plantillas. En inglés o en español (Opciones > Idioma).

## Los generadores y lo que no está decidido

divide es el IDE, no el generador, ni el lugar donde los generadores se ejecutan en producción. Un proyecto generador puede usar Div, Nodes, Ways, PHP o lo que necesite, y puede implementar su propia orquestación de etapas, comandos CLI, una API HTTP o un servidor MCP; las herramientas y los agentes de programación con IA usan después el generador desplegado mediante esas interfaces. El [[servidor web|Web Server]] de divide puede ayudar mientras desarrollas un generador HTTP, pero no es una API de generadores ni una plataforma MCP. El [[servidor MCP|MCP Server]] propio de divide (Opciones > Servidor MCP) es para desarrollar: permite que un agente de programación con IA verifique, renderice y trace las plantillas del proyecto a través de divide.

**Aún no está decidido**: qué es un generador como unidad, y qué responsabilidades en torno a la orquestación y a las interfaces de los generadores corresponden a divide (herramientas para desarrollarlas, inspeccionarlas, depurarlas o probarlas) y cuáles a los proyectos generadores. **Div está integrado en divide**, y los Flows de [Runner](https://github.com/divengine/runner) se ejecutan con la línea de comandos del propio Runner ([[Ejecutar Flows|Running Flows]]); [Nodes](https://github.com/divengine/nodes) y [Ways](https://github.com/divengine/ways) son bibliotecas PHP independientes que un generador puede usar, y su papel en el desarrollo de generadores está por decidir.

divide pretende complementar a los agentes de programación con IA como Claude Code, Codex u OpenCode, no ser uno de ellos: un agente no debería tener que escribir grandes cantidades de código predecible que un generador validado puede producir.

La generación con Div es reproducible cuando se controlan sus entradas y condiciones: la misma plantilla con los mismos datos da la misma salida solo si también se controla todo lo demás que interviene (Div puede leer además la hora, la petición, valores aleatorios y las funciones PHP que se le permiten). Y una salida reproducible no es necesariamente correcta: eso depende de las reglas, los modelos y las verificaciones del generador.

## Empieza aquí

1. [[Instalación|Installation]]: Python, PHP y Div.
2. [[Primeros pasos|Getting Started]]: un recorrido de cinco minutos.
   ¿Nuevo en Div? Su lenguaje se describe en la [documentación de Div](https://github.com/divengine/div/tree/master/docs), que también está dentro de divide: ver [[Ayuda|Help]].
3. Después, los capítulos: [[El escritorio|The Desktop]], [[Edición de plantillas|Editing Templates]], [[Edición de PHP|Editing PHP]], [[Esquema|Outline]], [[Buscar archivos y comandos|Finding Files and Commands]], [[Servidores de lenguaje|Language Servers]], [[Autocompletado|Completion]], [[Verificación de plantillas|Checking Templates]], [[Renderizado|Rendering]], [[Traza del render|Render Trace]], [[Ejecutar PHP|Running PHP]], [[Depurar PHP|Debugging PHP]], [[Servidor web|Web Server]], [[Archivos de datos|Data Files]], [[Otros archivos|Other Files]], [[Ventana de proyecto|Project Window]], [[Dialector|Dialector]], [[Traducir plantillas|Translating Templates]], [[Configuración de Div|Div Setup]], [[Composer|Composer]], [[Git|Git]].
4. [[Referencia de teclado|Keyboard Reference]] y [[Solución de problemas|Troubleshooting]] cuando los necesites.

El manual completo también está dentro de divide: pulsa **F1** (ver [[Ayuda|Help]]).

divide es parte de [Divengine](https://github.com/divengine). Código fuente: [divengine/divide](https://github.com/divengine/divide).
