# Ejecutar Flows

divide ejecuta, pausa y reanuda los Flows de [Divengine Runner](https://github.com/divengine/runner), el motor del Sequential Flow Model (SFM): un Flow de Blocks, cada uno con sus Steps, que hacen `call` y `jump` a otros Blocks y `pause`. **Los ejecuta Runner, no divide**: divide inicia la línea de comandos de Runner de la instalación de Composer de tu proyecto y muestra lo que dice. Runner analiza el YAML, ejecuta los Steps, sigue los calls y guarda el contexto.

![Ctrl+F9 en un Flow: pausado dentro de dos calls, el registro de Runner y el contexto en la ventana Salida](images/run-flow.png)

## Lo que necesitas

- **PHP 8.1** o posterior en el `PATH`.
- **Runner 0.2.0** o posterior instalado en el proyecto con Composer:

  ```bash
  composer require divengine/runner
  ```

  divide ejecuta `php vendor/divengine/runner/bin/run.php` (la carpeta de `config.vendor-dir` cuando composer.json la cambia). Sin él, Ctrl+F9 en un Flow dice cómo instalarlo.

El directorio `examples/runner` del repositorio es un proyecto listo para probar: `composer install` en él, ábrelo en divide y pulsa Ctrl+F9 en `flows/order.yml`.

## Ejecutar un Flow

Un Flow es un archivo YAML (`.yml`, `.yaml`) cuya raíz tiene `blocks`. En uno, **Ctrl+F9** (Ejecutar > Ejecutar) abre **Ejecutar Flow**; en un script PHP la misma tecla sigue ejecutando el script, y en una plantilla la renderiza. **Ejecutar > Argumentos...** abre el mismo diálogo. Un Flow modificado se guarda antes.

![El diálogo Ejecutar Flow antes de la primera ejecución: el contexto se guarda en .div/runner/, todavía no hay nada guardado y Reanudar está desactivado](images/run-flow-new.png)

- **Contexto inicial**: el contexto con el que empieza el Flow (el `--context` de Runner): un archivo JSON, o un objeto JSON escrito en el campo (`{"name": "Ana"}`). Vacío: un contexto vacío. Tiene que ser un objeto JSON; divide lo comprueba antes de ejecutar.
- **Raíz de funciones**: la carpeta de los archivos de actividades y condiciones (el `--root` de Runner). Vacío: el `_root_folder` del contexto, si no el `.div/runner.json` del proyecto (la etiqueta lo dice entonces), si no la carpeta del proyecto. Los módulos son carpetas dentro (`<raíz>/billing/total.php` para `module: billing`), o los `_modules` del contexto o de `.div/runner.json`. Ver [[Functions del Flow|Flow Functions]], que también los crea.
- **Guardar el contexto en**: el archivo donde Runner escribe el contexto resultante (`--save-context`), por defecto un archivo por Flow en la carpeta `.div/runner/` del proyecto (`flows/order.yml` se guarda en `.div/runner/flows/order.yml.context.json`). divide crea esa carpeta, con un `.gitignore` que deja los checkpoints fuera de Git. Cualquier otro archivo lo eliges tú. Vacío: no se guarda nada, y una ejecución pausada no podrá reanudarse.
- Debajo, lo que guarda ahora ese archivo: nada todavía, una ejecución pausada (dónde se detuvo) o el final de la última ejecución.
- **Ejecutar** inicia el Flow. **Reanudar** continúa la ejecución pausada guardada en el archivo; es el botón por defecto (Intro) cuando hay una. **Examinar...** elige un archivo o carpeta para el campo en el que estabas.

Los tres campos se recuerdan para cada Flow. Las rutas relativas son del proyecto: Runner se ejecuta en la carpeta del proyecto, así que el `_root_folder` y los `_modules` de un contexto también se toman desde ahí.

## Mientras se ejecuta

Un cuadro de progreso dice el Flow, el contexto, dónde se guarda y cuánto ha impreso el Flow. **Esc** lo detiene: PHP se termina.

Cuando acaba, el cuadro da el veredicto:

| Veredicto | Significa |
|---|---|
| **Hecho** | El Flow terminó (código de salida 0 de Runner). |
| **Pausado** | Un Step lo pausó (código de salida 3). No es un fallo: Reanudar lo continúa. |
| **Error** | Un Step o el Flow fallaron (código de salida 1): el error está en el informe y en Mensajes. |
| **No se ejecutó** | Runner rechazó la invocación (código de salida 2): un archivo que falta, un contexto que no es un objeto JSON, una opción no válida. El Flow no se ejecutó. |
| **Contexto no guardado** | El Flow se ejecutó, pero su contexto no pudo guardarse ni codificarse en JSON (un objeto o un closure dentro). El archivo guardado sigue como estaba. |
| **PHP terminó** | PHP murió antes de que Runner pudiera responder (`exit()`, un error fatal). No se guardó nada. |
| **Detenido** | Lo detuviste tú. No se guardó nada. |

## Lo que obtienes

La **ventana Salida** muestra el informe:

- **Estado**: `done`, `pausado en approval.ask (dentro de 2 call(s))`, `error`... y, para una ejecución reanudada, `reanudado, done`.
- **Resultado** y, tras un error, **Error**: el `_runner_result` y el `_runner_error` de Runner.
- Dónde se guardó el contexto, o por qué no se guardó.
- **── registro ──**: el registro de Runner de la ejecución (cada Step, call, retorno y pausa).
- **── contexto ──**: el contexto resultante, en JSON (con `_flow_state` y `_flow_stack` cuando está pausado).
- **── stderr ──**: lo que imprimió el Flow y los diagnósticos de Runner. La línea de comandos de Runner los mantiene separados del contexto.

La **ventana Mensajes** lista los diagnósticos de Runner (`runner: ...`) y los avisos y errores de PHP, con su lugar cuando PHP lo da.

![Un Flow ejecutado sin su raíz de funciones: el error en Salida, el diagnóstico de Runner en Mensajes](images/run-flow-error.png)

## Pausar y reanudar

La posición de una ejecución pausada está en el contexto guardado: `_flow_state` (el Block y el Step donde se detuvo) y `_flow_stack` (los marcos de retorno de los calls dentro de los que estaba). **Reanudar** ejecuta de nuevo el Flow, en un proceso PHP nuevo, con ese archivo como contexto y el mismo archivo para guardar, como hace la reanudación del propio Runner:

```bash
php vendor/divengine/runner/bin/run.php flows/order.yml --context .div/runner/flows/order.yml.context.json --save-context .div/runner/flows/order.yml.context.json
```

La ejecución continúa después del Step que pausó y vuelve por cada call pendiente; los Steps que ya se ejecutaron no se repiten. El campo Contexto inicial no se usa al reanudar.

![El diálogo Ejecutar Flow con una ejecución pausada guardada: Intro la reanuda](images/run-flow-dialog.png)

divide protege una ejecución pausada:

- **Reanudar necesita una ejecución pausada.** Cuando el archivo falta, guarda una ejecución terminada o no es un contexto de Runner, Reanudar está desactivado y dice por qué. divide nunca empieza el Flow de nuevo en su lugar.
- **Empezar de nuevo pregunta.** **Ejecutar** cuando el archivo guarda una ejecución pausada pregunta antes, y también sobre un archivo que elegiste tú (fuera de `.div/runner/`) y que ya existe. Una ejecución terminada o fallida en el checkpoint propio de divide se reemplaza sin preguntar. En cualquier caso, el archivo solo se reemplaza cuando termina la nueva ejecución.
- **Una ejecución detenida no cambia nada.** Runner escribe el contexto solo cuando la ejecución termina, reemplazando el archivo de una vez; una ejecución que detienes con Esc deja el contexto guardado como estaba, así que la ejecución pausada todavía puede reanudarse.
- **Un contexto que no puede guardarse se dice**, y el archivo conserva el último bueno.

## Límites

- Los Flows son código PHP de confianza: las actividades y condiciones se ejecutan con tus permisos. Runner no es una caja de arena, y divide tampoco.
- divide ejecuta un Flow de principio a fin o hasta su pausa: no avanza Block a Block ni Step a Step. Sus Blocks y Steps se muestran y se editan en la [[ventana Flow|Flow Structure]] (Ctrl+T), como un árbol, no como un diagrama.
- Solo Flows en YAML: un Flow escrito en PHP es un script PHP, y Ctrl+F9 lo ejecuta como tal.
- Una ejecución a la vez, sin planificador, cola ni historial de trabajos: el informe de una ejecución queda en la ventana Salida hasta la siguiente.
- El contexto pasa por JSON, como lo guarda la línea de comandos de Runner: un objeto vacío `{}` vuelve como `[]`.
