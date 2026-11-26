# Mock Simulation de una Function

Una **Mock Simulation** ejecuta una Function de [Runner](https://github.com/divengine/runner) con el contexto que le des y con **dobles** para las dependencias que declara. divide registra cada línea PHP que ejecuta la Function, y tú reproduces la ejecución línea a línea en el propio código de la Function: la línea que va a ejecutarse, sus variables locales, el contexto hasta ahí, lo que respondieron los dobles, lo que imprimió y cómo terminó.

> **MOCK SIMULATION: se ejecuta PHP real; solo se reemplazan las dependencias declaradas.** El código PHP de la Function se ejecuta de verdad, en un proceso PHP propio. Solo se reemplaza lo que pide a su contexto: otras Functions (`$context['_importer']`), el logger de Runner (`$context['_logger']`) y los objetos de servicio bajo claves del contexto. Las funciones propias de PHP (archivos, bases de datos, `curl`, `mail`, `time()`), el código de nivel superior del archivo y, si lo activas, las clases de Composer del proyecto se ejecutan de verdad. **No es un sandbox ni está libre de efectos secundarios.** Simula solo código en el que confías.

No es la [[Simulación de Flows|Flow Simulation]]. Cada forma en que divide ejecuta una Function hace algo distinto:

| | Qué se ejecuta | Qué obtienes |
|---|---|---|
| **Ejecutar** un Flow (Ctrl+F9, [[Ejecutar Flows\|Running Flows]]) | el Flow y sus Functions, de verdad | el contexto después |
| **Probar Function** (T, Ctrl+F9 en [[Functions del Flow\|Flow Functions]]) | una Function, de verdad, con sus dependencias reales | su informe en Salida |
| **Depurar** (Probar Function > Depurar, [[Depurar PHP\|Debugging PHP]]) | la misma llamada, de verdad, en el depurador | puntos de ruptura, F7 / F8, inspecciones |
| **Simulación de Flows** (Shift+F9) | la simulación del Flow que hace Runner: **no se ejecuta código de ninguna Function** | los eventos del Flow en su tablero |
| **Mock Simulation** (Shift+T) | el **PHP real** de una Function, con sus dependencias declaradas dobladas | sus líneas PHP, reproducidas en su código |

Una Mock Simulation nunca lee ni escribe el contexto guardado de un Flow (`.div/runner/`) ni una simulación de Flow (`.div/simulation/`), y el tablero del Flow nunca muestra líneas PHP.

## Qué necesitas

- **PHP 8.1** o posterior en el `PATH`.
- **Xdebug**, para la traza de líneas. Sin él, divide pregunta si simular sin la traza de líneas: entonces obtienes el resultado (el return, el contexto, las llamadas a los dobles, la salida) y ninguna línea. El PHP se ejecuta de verdad en los dos casos. Xdebug se encuentra como en [[Depurar PHP|Debugging PHP]]: en el `php.ini` del propio PHP, o con `xdebug.so` indicado en **Opciones > Xdebug…**.
- Una Function **escrita para inyección**: que toma de su contexto aquello de lo que depende. Una Function que abre archivos, crea servicios con `new` o llama métodos estáticos ejecuta esas partes de verdad, y la simulación no puede mostrar lo que no reemplazó.

No hace falta Runner: la Function la llama el arnés de divide, no Runner.

## Abrirla

Elige una Function de cualquiera de estas formas:

- **Shift+T** en un Step del [[Diseñador de Flows|Flow Designer]]: su activity, si no su condition (**T** sigue siendo Probar Function);
- **Function... > Simular...** en el diálogo del Step;
- **Alt+F10 > Simular...** en la ventana [[Functions del Flow|Flow Functions]], sobre una Function (allí **Ctrl+F9** sigue siendo Probar Function);
- **Ejecutar > Mock Simulation de una Function**: la Function bajo el cursor en la ventana Functions, o el archivo PHP que editas cuando es una de las Functions del proyecto.

La Function es la que cargaría una ejecución del Flow: la raíz de funciones y las carpetas de Module del Flow (ver [[Functions del Flow|Flow Functions]]).

Los archivos PHP sin guardar se guardan antes: PHP ejecuta lo que hay en disco.

## El diálogo

El diálogo **Mock Simulation** contiene un escenario. Su aviso siempre dice que se ejecuta PHP real, que no es un sandbox y que no es una simulación de Flow.

- **La primera línea**: el archivo de la Function y su **fijación** (abajo).
- **Escenario**: un nombre. **Guardar** escribe el escenario en el proyecto, en `.div/function-simulations/<module>/<nombre>.<escenario>.json` (`_root` para una Function sin Module), para el equipo en Git. **Abajo** ofrece los guardados, y elegir uno llena el diálogo. Tus propios ajustes recuerdan solo las opciones y el nombre del último escenario usado de cada Function, y solo después del permiso del proyecto: nunca su contexto ni sus dobles, que quedan en el archivo del escenario.
- **Contexto**: un objeto JSON, el contexto que recibe la Function, por referencia. Las claves que empiezan por `_` son de Runner y se rechazan.
- **Dobles**: un objeto JSON con `importer` (otras Functions, por `module:nombre` o `nombre`) y `services` (un objeto por clave del contexto, un resultado por método). Cada resultado es uno de los de `--simulate` de Runner: `returns`, `throws` (un mensaje) o `sequence` (un resultado por llamada), con un `context` opcional que se fusiona con el contexto.
- **Return esperado** y **Claves del contexto esperadas**: comprobaciones opcionales, como en Probar Function (las claves del contexto son un subconjunto que debe tener el contexto después).
- **Líneas**, **Segundos**, **Bytes de salida**: los límites. Pasadas las líneas, la traza se detiene y lo dice; pasados los segundos, PHP se termina; pasados los bytes de salida, lo que imprime la Function se corta.
- **Trazar las líneas PHP (Xdebug)**: activado por defecto.
- **Fijar a la versión del archivo**: activado para un escenario nuevo (abajo).
- **Tripwire (no es un sandbox)**: se desactivan las funciones de procesos, red y correo de PHP y las escrituras de archivo más comunes, y se cierran los archivos fuera del proyecto. Detiene algunos efectos secundarios directos; otros (`fopen`, PDO, estado estático) siguen ocurriendo.
- **Autoload de Composer (clases reales)**: desactivado por defecto. Sin él, una clase que la Function necesita es un error que la nombra, nunca una dependencia real silenciosa. Con él, esas clases son código real.
- **Editar...** abre todo el escenario como árbol o como JSON, el editor del contexto de un Step.

**Los dobles se rellenan solos.** divide lee el archivo de la Function (no lo ejecuta) y encuentra lo que pide a su contexto: `$context['_importer']('nombre', 'module')` y `$context['clave']->método(`, también a través de una variable a la que se asignaron. Cada uno que encuentra recibe un marcador que responde `null`, y la línea bajo los campos nombra los marcadores hasta que los cambies. **Simular** y **Guardar** preguntan antes de que un marcador responda `null`: **Mantener null** cuando `null` es la respuesta que quieres (es válida), o **Volver** para darle un valor. Un `null` de un escenario guardado es lo que se guardó, y no se vuelve a preguntar. Un import cuyo nombre se calcula al ejecutarse no se puede conocer: la línea dice dónde está.

`unknown` siempre es `fail`: **una dependencia sin doble nunca es la real**. La simulación lanza una excepción cuando la Function la pide.

### Un escenario se rechaza antes de ejecutar nada

**Simular** no ejecuta nada, y el diálogo sigue abierto con el motivo, cuando:

- el contexto, los dobles o una expectativa no son JSON;
- un resultado no es uno de `returns`, `throws` o `sequence`, o tiene dos;
- un límite está fuera de su rango (líneas hasta 100.000, segundos hasta 300, salida hasta 4 MiB);
- **una dependencia que usa el archivo no tiene doble**.

### La fijación

Un escenario está **fijado** cuando guarda el sha256 del archivo de la Function. Entonces la simulación comprueba el archivo antes de llamar a la Function: un archivo que cambió desde entonces está **desactualizado**, y no se ejecuta nada.

- Un escenario nuevo se fija al archivo tal como está ahora. Desmarca **Fijar a la versión del archivo** para quitar la fijación: el escenario ejecuta entonces el archivo tal como esté.
- Un escenario sin fijar nunca se muestra como fijado: el diálogo dice **NO fijado a una versión del código**, y lo mismo la reproducción y la traza guardada (`"pinned": false`).
- **Un escenario desactualizado solo se vuelve a fijar cuando tú lo dices.** El diálogo dice **DESACTUALIZADO** y muestra **Refijar**. Al simularlo, dice que el archivo cambió y pregunta: **Refijar y simular**, o **Cancelar**. Un escenario guardado solo cambia cuando lo **Guardas**.

La fijación dice que el archivo es aquel para el que se escribió el escenario. No dice nada de seguridad: una Mock Simulation fijada sigue ejecutando PHP real.

### La primera vez en un proyecto

La primera Mock Simulation de un proyecto te pide que la permitas, después de decir qué ejecuta. Tu respuesta se guarda en tus propios ajustes, no en el proyecto.

## Simular

**Simular** (Intro) ejecuta la Function una vez, en un cuadro que **Esc** detiene (PHP se termina). Con la traza de líneas, divide recorre la Function con una sesión de Xdebug propia, aparte del depurador y de tus puntos de ruptura; solo registra el archivo de la propia Function.

La ejecución se guarda en `.div/function-simulation/` (fuera de Git: divide escribe su `.gitignore`), con el escenario que ejecutó. Como en las simulaciones de Flows, se guardan las últimas 20 ejecuciones, hasta 64 MiB. **Reproducir**, en el diálogo, abre la última de la Function sin ejecutar PHP.

## La reproducción

La ventana **Mock Simulation** se abre en la primera línea. El archivo de la Function queda a la izquierda, de solo lectura, con la línea que va a ejecutarse marcada. A la derecha (debajo, en una ventana estrecha):

- **MOCK SIMULATION**, la línea y el evento, el aviso y la fijación;
- la **profundidad** de la línea (mayor que 0 dentro de un closure que define la Function) y cuántas sentencias más de la misma línea se ejecutaron sin cambiar ninguna variable;
- **Cambiado por las líneas anteriores**: lo que dejaron las líneas anteriores;
- **Cambiado por un doble que llama esta línea**: lo que cambió un doble mientras se ejecutaba la línea;
- **Variables locales** y **Contexto hasta aquí**: el estado **antes** de ejecutarse la línea;
- **Llamadas a dobles**, **Logger** y **Salida**: lo que respondieron los dobles, en orden, lo que se registró y lo que imprimió la Function;
- el resultado: lo que devolvió y su tipo, o la excepción o el error con su lugar (un doble que falta lo dice), y cada expectativa, `[OK]` o `[!!]`.

Moverse solo mueve un cursor: **no se vuelve a ejecutar nada**, y no cambia ningún archivo.

| Tecla | Acción |
|---|---|
| **F7** / **Shift+F7** | línea siguiente / anterior |
| **F8** / **Shift+F8** | línea siguiente / anterior a la misma profundidad (por encima de las líneas de un closure) |
| **F4** | la siguiente vez que se ejecutó la línea bajo el cursor |
| **Ctrl+Inicio** / **Ctrl+Fin** | primera / última línea |
| **X** | todo el contexto antes de la línea, en la ventana Salida |
| **S** | Guardar como escenario |

Lo que se muestra sigue cómo avanza Xdebug:

- Las variables de una línea son las de **antes** de ejecutarse.
- Una rama que no se tomó no tiene línea.
- La cabecera de un `foreach` aparece solo en su primera pasada.
- Los valores están acotados: las cadenas de más de 4 KiB se cortan, los arrays de más de 1.000 elementos se truncan y el anidamiento se detiene en la profundidad 16; el panel dice cuáles se cortaron.

Si el archivo de la Function cambió desde la ejecución, sus líneas no se marcan: el panel lo dice.

### Guardar como escenario

**S** guarda el escenario que se ejecutó, con un nombre, en `.div/function-simulations/`. **Esperar el return y los cambios de contexto de esta ejecución** los añade como sus expectativas, para comprobar con ellos ejecuciones posteriores. Su fijación es la de la ejecución: una ejecución sin fijar se guarda sin fijar.

## Límites

- Un doble reemplaza solo lo que la Function pide a su contexto. En un PHP estándar nada intercepta las funciones propias de PHP.
- `time()`, `rand()` y `uniqid()` no se controlan.
- Una Function que dirige el Flow (`_flow_state`, `_update_context`) es cosa de la [[Simulación de Flows|Flow Simulation]].
- La traza avanza unas 2.000 líneas por segundo.
