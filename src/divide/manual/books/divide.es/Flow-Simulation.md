# Simulación de Flows

La **simulación** ejecuta un Flow de [Runner](https://github.com/divengine/runner) sin ejecutar sus Functions. Runner responde cada `condition` y `activity` con los **dobles de prueba** que declaras, registra lo que hace el Flow como una lista de eventos, y divide reproduce esos eventos en el tablero del Flow. Recorres los eventos de uno en uno, hacia delante y hacia atrás, y el tablero muestra qué Steps se ejecutaron, cuáles se saltaron, qué `call` y `jump` se recorrieron, dónde se pausó el Flow y cómo cambió el contexto.

Simular y reproducir son una sola función. La simulación se ejecuta una vez, en un proceso PHP propio. Reproducir sus eventos nunca vuelve a ejecutar nada.

Es Runner quien simula el Flow, no divide. Usa su propio compilador y su propio motor, los mismos de una ejecución real: los mismos Blocks, Steps, `call`, `jump`, `pause`, `_flow_state` y `_flow_stack`. No hay un segundo intérprete.

| | **Ejecución real** (Ctrl+F9) | **Simulación** (Shift+F9) |
|---|---|---|
| Las Functions del Flow | se ejecutan, con sus efectos (archivos, bases de datos, red) | nunca se cargan ni se llaman: responden los dobles |
| Runner necesario | 0.2.0 o posterior | 0.3.0 o posterior |
| Lo que obtienes | el contexto, guardado para reanudar ([[Ejecutar Flows\|Running Flows]]) | cada evento, reproducido en el tablero |
| Pausa y reanudación | desde el contexto guardado en `.div/runner/` | desde la sesión de simulación de Runner en `.div/simulation/` |

## Qué necesitas

- **PHP 8.1** o posterior en el `PATH`.
- **Runner 0.3.0** o posterior instalado en el proyecto:

  ```bash
  composer require divengine/runner:^0.3
  ```

  Con un Runner anterior, la simulación lo dice y no ejecuta nada. Ejecutar (Ctrl+F9) sigue ejecutando el Flow de verdad.

El ejemplo `examples/runner` del repositorio está listo para probar. Ejecuta `composer install` en él, abre `flows/fulfil.yml` y pulsa **Shift+F9**: sus dobles ya están en `.div/simulations/flows/fulfil.yml.doubles.json`.

## Simular un Flow

Abre el diálogo **Simular Flow** desde el código de un Flow, su ventana del Flow o su tablero, de cualquiera de estas formas:

- **Shift+F9**;
- **Ejecutar > Simular Flow con dobles**;
- **S** en el tablero del [[Diseñador de Flows|Flow Designer]].

El diálogo tiene:

- **Contexto inicial**: un archivo JSON, o un objeto JSON escrito en el campo. Vacío: un contexto vacío.
- **Dobles**: el archivo de dobles, en el formato `--simulate` de Runner (abajo). Por defecto, `.div/simulations/<flow>.doubles.json`. Es un archivo del proyecto que el equipo puede compartir y guardar en Git.
- **Conservar mensajes de error y log en la traza**: el `--trace-messages` de Runner. Está desactivado por defecto. Sin él, el mensaje de un error o de un log queda fuera de la traza, porque es texto libre que podría contener un secreto. La clase del error y el nivel del log se conservan.

Bajo los campos, el diálogo dice cuántas funciones del Flow necesitan un doble, cuáles no tienen todavía, y qué le pasa al archivo. **Una simulación se rechaza antes de ejecutar nada** en dos casos:

- una referencia del Flow (o de un Flow anidado que nombra un doble) no tiene doble;
- el archivo no es lo que admite Runner: dos resultados en un doble, una condition que pausa, una clave de contexto que empieza por `_`, un Flow anidado que no está, un presupuesto desconocido.

Runner vuelve a comprobar el archivo al simular.

Los botones:

- **Simular** ejecuta la simulación, en un cuadro que **Esc** detiene. Después se abre la ventana de simulación en el último evento.
- **Editar dobles** abre el archivo de dobles en un editor. Si el archivo todavía no existe, antes escribe uno con un doble para cada función (una condition devuelve `true`, una activity `null`). Si al archivo le faltan dobles, primero pregunta y después los añade; el resto del archivo queda como estaba.
- **Reproducir** abre la última simulación grabada de este Flow, sin ejecutar PHP.

Un Flow modificado se simula tal como está en el editor. Su YAML se copia en la carpeta de la simulación (una **copia**), y **tu archivo no se guarda ni se escribe**. Sus cambios sin guardar siguen sin guardar.

## El archivo de dobles

El archivo de dobles es el propio archivo `--simulate` de Runner:

```json
{
    "description": "A small order: the stock short once, the invoice paused",
    "doubles": {
        "compute_total": {"returns": 25, "context": {"total": 25}},
        "needs_approval": {"returns": false},
        "stock_short": {"sequence": [{"returns": true}, {"returns": false}]},
        "billing:total": {"returns": 20},
        "invoice_sum": {"pause": true, "context": {"sum": 25}},
        "format_receipt": {"returns": "Receipt: 25"}
    },
    "budget": {"steps": 200, "transfers": 50, "seconds": 5}
}
```

La clave de un doble es la referencia tal como la escribe el Step: `module:nombre` para un Step con `module`, si no, el nombre.

| Doble | Qué hace |
|---|---|
| `{"returns": valor}` | Devuelve `valor`. Una condition toma su verdad en PHP. |
| `{"throws": "mensaje"}` | Lanza una excepción: el Step falla. |
| `{"pause": true}` | Pausa el Flow en este Step. Solo activities. |
| `{"sequence": [resultado, ...]}` | Un resultado por llamada: la primera llamada recibe el primero. Una llamada de más falla. |
| `{"flow": "hijo.yml"}` | Se usa como activity un Flow YAML anidado, simulado con los mismos dobles. La ruta es relativa al proyecto. |

Cada doble funciona así:

- **Contexto.** Un resultado puede añadir `"context": {...}`, que se mezcla en el contexto como lo haría la función.
- **Presupuesto.** `budget` detiene un Flow que no termina: `steps` (10000 por defecto), `transfers` (calls y jumps, 10000) y `seconds` (10). divide detiene PHP si pasa 20 segundos más.
- **Opciones de la traza.** `trace` lleva las opciones de traza de Runner (`max_events`, `redact_keys`...).

## La ventana de simulación

La ventana tiene el tablero del Flow tal como se simuló. Es **de solo lectura**: ninguna tecla edita el Flow en ella.

Sobre el tablero, la tarjeta de cada Step lleva una marca a la izquierda de su título:

| Marca | El Step |
|---|---|
| **►** | actual: el evento bajo el cursor es de este Step |
| **√** | visitado: se ejecutó |
| **-** | saltado: su condition fue false, o estaba antes del destino de un call o jump |
| **»** | esperando su `call`: el Block que llamó todavía no ha vuelto |
| **=** | en pausa: el Flow se pausó tras él |
| **X** | falló: su función lanzó una excepción, o no tenía doble |

Las líneas de `call` y `jump` recorridas hasta el momento aparecen **subrayadas**. Un `call` sigue siendo una línea simple y un `jump` una doble, como en el diseñador. Las marcas son caracteres, no colores, así que se leen igual en todos los temas, también en los de fósforo.

El panel de la derecha (bajo el tablero con menos de 100 columnas) muestra:

- **SIMULACIÓN**, el número del evento y su segmento, en vídeo inverso;
- **el evento**, con su Block.Step y lo que dice (ver abajo);
- **los cambios del contexto** en ese evento: `+` añadida, `~` cambiada (antes -> después), `-` quitada;
- **el log** de ese Step;
- **los calls** que esperan volver, del más antiguo al más reciente;
- **la tarjeta seleccionada**: cuántas veces se ejecutó y su estado;
- **abajo**, cómo terminó la simulación: terminada, en pausa (dónde), o el error. Si la traza se recortó, dice cuánto. Si el Flow o sus dobles han cambiado desde la simulación, también lo dice.

### Teclas

| Tecla | Qué hace |
|---|---|
| **F7** / **Shift+F7** | El evento siguiente / anterior |
| **F8** / **Shift+F8** | El Step siguiente / anterior (empezado o saltado) |
| **Ctrl+Inicio** / **Ctrl+Fin** | El primer / último evento |
| **F4**, o **Enter** en una tarjeta | El siguiente evento del Step seleccionado (desde el principio tras el último) |
| **F** | Seguir o no con la selección al Step actual |
| **X** | El contexto en el evento, como JSON, en la ventana Salida |
| **Ctrl+F2** | Volver al primer evento |
| **Ctrl+F9** | Reanudar una simulación en pausa; en una terminada, el diálogo Simular Flow |
| **flechas**, **Inicio / Fin**, **Tab**, **Retroceso** | Moverse por el tablero y sus conexiones, como en el [[Diseñador de Flows\|Flow Designer]] |

Mover el cursor solo cambia lo que se muestra. Los eventos, el contexto, el YAML y todos los archivos quedan como estaban.

### El evento

Los detalles del evento dependen de su tipo:

- `run.start` y `run.end` dan el estado, el error y el checkpoint: el `_flow_state` y el `_flow_stack` exactos de Runner.
- `block.enter` da por qué se ejecuta el Block: el inicio, una reanudación, un call, un jump, una vuelta.
- `step.skip` da por qué el Step no se ejecutó.
- `condition` da la función y su resultado, y lo que ese resultado hace con el Step.
- `activity.end` da el resultado, que se guarda bajo el id del Step.
- `activity.error` da el error.
- `call` da el destino y dice que **vuelve aquí cuando termina el Block**.
- `jump` da el destino y dice que **sigue allí, no vuelve**.
- `call.return` da el Step al que vuelve, y si ese frame venía de un checkpoint.
- `pause` da el checkpoint.
- `double` da qué llamada del doble respondió, y cómo.
- `function.missing` y `budget.exhausted` explican por qué falló la ejecución.

Los tipos de evento que este divide no conoce se muestran con sus campos.

## Pausa y reanudación

Cuando una simulación se pausa, **Ctrl+F9** en su ventana la reanuda. Un **proceso PHP nuevo** continúa desde la sesión de simulación de Runner: el contexto simulado, las llamadas a cada doble (una `sequence` sigue donde iba) y una huella de las fuentes. El segmento nuevo se añade a la misma reproducción, tras el primero. Un `call` que se pausó vuelve a su Step desde el `_flow_stack` que guardó el checkpoint, y `call.return` lo dice.

Una reanudación usa aquello con lo que empezó la simulación:

- **La copia.** Si el Flow o el archivo de dobles han cambiado desde entonces, divide pregunta antes: Reanudar simula la copia, no los cambios. Shift+F9 empieza una simulación nueva con ellos.
- **Los Flows anidados.** Se leen del proyecto. Si uno ha cambiado, Runner rechaza la reanudación (su huella), y divide lo dice. Empieza una simulación nueva.

Una simulación nunca toca el checkpoint de una ejecución real:

- Su sesión está en `.div/simulation/`, nunca en `.div/runner/`.
- Runner rechaza un archivo que no sea una sesión de simulación.

## Dónde se guarda

Cada simulación tiene una carpeta en el `.div/simulation/` del proyecto. divide crea esa carpeta con un `.gitignore` que la deja fuera de Git. La carpeta de una simulación contiene:

| Archivo | Qué es |
|---|---|
| `flow.yml` | el YAML del Flow tal como se simuló (la copia) |
| `doubles.json`, `context.json` | los dobles y el contexto inicial con los que empezó |
| `session.json` | la sesión de Runner, desde la que se reanuda una pausa |
| `trace-1.json`, `trace-2.json`... | una traza por segmento: lo que se reproduce |
| `divide-session.json` | de dónde salió (el Flow, el archivo de dobles) y cómo terminó cada segmento |

divide conserva las 20 simulaciones más recientes, hasta 64 MiB en total. Las más antiguas se borran al empezar una nueva, salvo las que estén abiertas en una ventana. Solo se borran carpetas que haya creado divide.

## Secretos y tamaño

La traza es de Runner, con las protecciones de Runner:

- los valores bajo claves que parecen secretas (`password`, `token`, `api_key`, `card_number`...) se sustituyen por `{"$type": "redacted"}`;
- los mensajes quedan fuera salvo que los conserves;
- las cadenas, las listas y la traza entera tienen límites (4 MiB por defecto).

Una traza que llegó a un límite lo dice: la ventana indica cuántos eventos se descartaron o compactaron. Un contexto reconstruido con valores recortados avisa de que es aproximado. El archivo de sesión de Runner contiene todo el contexto simulado, como cualquier contexto guardado. Se queda en la caché del proyecto, que Git ignora.

## Cómo funciona

Para cada segmento, divide ejecuta la propia línea de comandos de Runner en la carpeta del proyecto:

```bash
php vendor/divengine/runner/bin/run.php --json --simulate doubles.json --session session.json \
    --trace trace-1.json [--context context.json] -- flow.yml
```

El código de salida de Runner dice cómo terminó el segmento: 0 terminado, 3 en pausa, 1 error, 2 no ejecutado. La traza (protocolo `divengine.runner.trace`, versión 1) tiene los eventos. divide solo lee esa versión. Ignora los campos y tipos de evento que no conoce, como pide el protocolo. Una traza de otra versión se rechaza con un mensaje claro.

Una simulación no es un sandbox. Runner garantiza que las funciones del Flow no se cargan ni se llaman, pero PHP sigue compilando y ejecutando el YAML, y un archivo de dobles puede nombrar Flows anidados que se compilan. Los Flows y los dobles son entradas de confianza. Para ejecutar y depurar código real están [[Ejecutar Flows|Running Flows]], [[Depurar PHP|Debugging PHP]] y Probar Function en [[Functions del Flow|Flow Functions]].

## Límites

- **Solo YAML.** Runner solo simula Flows YAML. Un Flow anidado solo se simula mediante un doble `{"flow": "hijo.yml"}`.
- **El tablero solo muestra el Flow simulado.** Los eventos de un Flow anidado están en la reproducción y el panel nombra su ámbito, pero sus Steps no están en el tablero. Mientras se ejecutan, el Step que ejecuta el Flow anidado es el actual.
- **Los dobles son datos, no PHP.** Un doble de condition no puede pausar.
- **Cambios de primer nivel.** Los cambios del contexto comparan las claves de primer nivel. Un cambio dentro de un array anidado muestra la clave entera, antes y después.
- **Sin pasos por PHP.** La simulación avanza por los eventos del Flow, no por las sentencias PHP. Para eso, ver [[Depurar PHP|Debugging PHP]] y Probar Function.
- **De una en una.** Se ejecuta una simulación a la vez. Una reproducción necesita su carpeta: cuando la caché la borra, ya no se puede reproducir.
