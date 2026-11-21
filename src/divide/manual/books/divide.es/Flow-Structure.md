# Estructura del Flow

La **ventana Flow** muestra un Flow de [Runner](https://github.com/divengine/runner) por lo que lo compone: sus Blocks, cada uno con sus Steps, y lo que hace cada Step (`condition`, `activity`, `module`, `call`, `jump`, `context`, `pause`). Desde ella puedes:
- editar un Step, añadir uno o borrarlo;
- ir al destino de un `call` o un `jump`, o abrir el archivo de una actividad;
- verificar el Flow con Runner y ejecutarlo ([[Ejecutar Flows|Running Flows]]).

Todo se hace con el teclado.

![La ventana Flow en order.yml: los Blocks y Steps a la izquierda, el Step elegido a la derecha, el veredicto de Runner debajo](images/flow-window.png)

**El archivo YAML es el Flow.** La ventana no tiene un modelo propio, y no se guarda nada aparte del YAML. Muestra el buffer de la ventana de código que tiene el Flow abierto, y cada cambio hecho en ella es una edición de ese buffer:
- Deshacer (Ctrl+Z), Rehacer (Ctrl+Y), la marca de modificado y F2 funcionan como en el código.
- Escribir en el código actualiza la ventana.
- Nada llega al disco hasta que guardas.

## Abrirla

Un Flow es un archivo YAML (`.yml`, `.yaml`) cuya raíz tiene `blocks`. En su ventana de código, **Ctrl+T** (Ejecutar > Estructura del Flow) abre la ventana Flow en el lugar del código, en el Step bajo el cursor. Ctrl+T de nuevo vuelve al código, con el Step o Block elegido seleccionado. En otros archivos YAML Ctrl+T no hace nada; en JSON es el árbol de [[Archivos de datos|Data Files]].

## La ventana

- **Izquierda: el árbol.** Contiene el Flow, sus Blocks en el orden en que están escritos (el primero es donde empieza el Flow) y los Steps de cada Block con lo que hacen: `activity compute_total`, `call -> review.check`, `condition needs_approval, context, pause`. Un Step o Block con un problema lleva un **!** delante. Escribir filtra el árbol.
- **Derecha: lo elegido.**
  - De un Step: sus atributos, su línea, adónde lleva un `call` o un `jump` (`-> Block review, Step check (línea 14)`), el archivo del que sale una actividad o una condición (`-> functions/needs_approval.php`) y sus problemas.
  - De un Block: sus Steps y qué Steps hacen call o jump a él.
  - Del Flow: su id, su descripción, sus Blocks y sus Steps.
- **Debajo: el veredicto de Runner.** Dice "el Flow compila" o el mensaje de Runner, con el número de errores y avisos.

## Teclas

| Tecla | Qué hace |
|---|---|
| **↑ ↓** | Moverse por el árbol |
| **← →** | Cerrar o abrir un Block. ← desde un Step sube a su Block; → desde un Block abierto entra en su primer Step |
| **Intro** | Editar el Step (en un Block: abrirlo o cerrarlo) |
| **Ins** | Un Step nuevo después del elegido (en un Block: al final) |
| **Supr** | Borrar el Step. Antes pregunta, y dice qué Steps llevan a él |
| **Ctrl+Intro** (Ctrl+J) | Ir al destino del `call` o `jump`. En un Step sin ninguno, abre el archivo de su actividad o condición |
| **Ctrl+T** | El YAML, en el Step o Block elegido |
| **Alt+F9** | Verificar el Flow, con los problemas en Mensajes |
| **Ctrl+F9** | Ejecutar el Flow ([[Ejecutar Flows|Running Flows]]) |
| **F2** | Guardar |
| **Ctrl+Z / Ctrl+Y** | Deshacer y rehacer (los del código) |

## Editar un Step

**Intro** abre los atributos del Step:

![El diálogo del Step approval.ask](images/flow-step.png)

- **Module**: la carpeta de la que salen la actividad y la condición (opcional).
- **Condición**: una función; el Step se ejecuta solo si devuelve true.
- **Actividad**: la función que hace el trabajo.
- **Call** `block.step`: ir allí y volver. **Jump** `block.step`: seguir desde allí. Un Block vacío (`.step`) es el propio Block del Step. Un Step vacío (`block.`) es el primer Step del Block.
- **Contexto**: valores que pone el Step, como un mapping, `{approved: true, by: ana}`.
- **Pausar**: pausa el Flow después del Step.

**Abajo** en un campo ofrece lo que ya tiene el proyecto:
- los archivos de funciones de la raíz de funciones (o de la carpeta del Module), para la actividad y la condición;
- las carpetas de Module;
- los destinos `block.step` del Flow, para call y jump.

**Un campo vacío quita el atributo.** **Ins** abre el mismo diálogo con un **Id del Step** primero. El Step nuevo se escribe después del elegido, con la sangría de sus hermanos.

### Solo se escribe lo que cambias

divide cambia el texto YAML en su sitio. Nunca vuelve a escribir el archivo desde un modelo:
- **Un valor cambiado** reemplaza solo el valor. Un comentario detrás, en la misma línea, se queda: `activity: compute_total   # sums` pasa a ser `activity: compute_sum   # sums`.
- **Un atributo nuevo** es una línea nueva después del último del Step, con la sangría de los demás.
- **Un atributo quitado** quita solo sus líneas. Los comentarios en líneas propias se quedan.
- **Un contexto escrito como bloque** (una clave por línea) se cambia clave a clave:
  - un valor cambiado reemplaza solo ese valor, y el comentario detrás se queda;
  - una clave nueva es una línea más;
  - una clave que quitas pierde su línea;
  - las claves siguen en el orden en que están escritas.
- **Una edición nunca quita comentarios.** Un cambio que quitaría uno se rechaza con un mensaje, y no se cambia nada. Ese cambio lo haces en el código (Ctrl+T). Por ejemplo:
  - quitar `activity: compute_total   # sums`;
  - quitar una clave del contexto cuya línea tiene un comentario;
  - cambiar un valor del contexto que es a su vez un mapping.

  **Supr** sobre un Step dice cuántos comentarios tiene escritos antes de borrarlos con el Step.
- **Todo lo demás** queda exactamente como lo escribiste: comentarios, orden de las claves, líneas en blanco, comillas, sangría y claves que divide no conoce.
- **Comillas:** un valor se escribe sin comillas cuando YAML lo lee igual. Si no, va entre comillas dobles: `true`, `12`, `a: b`, `x #y`, `Class::run`.

Todos los cambios de un diálogo son una sola edición: un Ctrl+Z los deshace. divide relee el resultado antes de quedárselo. Si el Step no tiene exactamente lo que pediste, la edición se deshace y te lo dice.

### Lo que se edita en el código

Algunas cosas no se pueden cambiar en su sitio. La ventana las muestra pero no las edita, dice por qué, y Ctrl+T te lleva a ellas:
- un Step escrito en estilo flow (`after: {jump: main.receipt}`); su línea del árbol dice *(solo lectura)*;
- un Step o atributo con un ancla, un alias o una etiqueta;
- un atributo escrito como escalar de bloque (`|`, `>`);
- un archivo de Flow con varios documentos YAML.

**Cuando el YAML no se puede leer**, el árbol dice *[errores de YAML]* y la ventana no edita nada. El problema está en Mensajes y bajo el código. El archivo queda como está hasta que lo corrijas en el código.

## Problemas

![Un call a un Step que no existe y una actividad sin su archivo: en el árbol, en el Step elegido y en Mensajes](images/flow-problems.png)

Los problemas son los mismos en tres sitios:
- en la ventana Flow;
- en el código, como marcas bajo el texto;
- en Mensajes. **Alt+F9** los lista; **Alt+F8** y **Alt+F7** los recorren, e Intro va a la línea.

**El propio compilador de Runner verifica el Flow.** divide pide al Runner instalado en el proyecto (Runner 0.2.0 o posterior, ver [[Ejecutar Flows|Running Flows]]) que compile el Flow, sin ejecutarlo:
- el parser de Runner y su esquema: claves desconocidas como `activty:`, tipos equivocados, nombres de Module;
- su resolución de los destinos de `call` y `jump`.

Solo se carga el archivo fuente de Runner, no el código de tu proyecto. **No se ejecuta ninguna condición ni actividad.**

Runner se detiene en su primer error, así que divide también busca dos cosas por su cuenta, para marcar todos los sitios a la vez:
- **Destinos**: un `call` o `jump` a un Block o Step que no está en el archivo.
- **Archivos de funciones**: una actividad o condición cuyo archivo no está donde lo buscaría el importador de Runner:
  - con un Module: `<carpeta del module>/<nombre>.php`. La carpeta es la entrada `_modules` del contexto, si la hay, y si no `<raíz de funciones>/<module>`;
  - sin Module: `<raíz de funciones>/<nombre>.php`, y si no `<nombre>.php`.

  Una función de un Module que falta es un error. Una sin Module que falta es un error, salvo que PHP tenga una función con ese nombre, como `strlen`. Cuando divide no puede saberlo, es un aviso, porque Runner prueba entonces el nombre como un callable de PHP.

La raíz de funciones y los Modules son los que el [[diálogo Ejecutar Flow|Running Flows]] daría a Runner:
- la raíz es la **Raíz de funciones** del diálogo; si está vacía, el `_root_folder` de su **Contexto inicial**; si no hay ninguno, la carpeta del proyecto;
- los Modules salen del `_modules` del contexto.

Ejecutar > Argumentos los cambia.

Sin Runner instalado, el veredicto lo dice y solo se hacen las búsquedas de divide.

## Ejecutar el Flow editado

**Ctrl+F9** en la ventana Flow abre el [[diálogo Ejecutar Flow|Running Flows]] de ese Flow, como en su código. Un Flow modificado se guarda primero, y luego Runner ejecuta el archivo.

## Límites

- La ventana edita Steps: sus atributos, añadirlos y borrarlos. Los Blocks se añaden, renombran y reordenan en el código, y el id de un Step también.
- Muestra la estructura como un árbol, no como un diagrama. No simula un Flow, ni lo reproduce, ni lo ejecuta paso a paso, ni lo detiene en puntos de ruptura. La ejecución es de Runner, a través de [[Ejecutar Flows|Running Flows]].
- Los archivos de funciones se buscan por su nombre y solo se comprueba que existan; divide nunca los carga. Si devuelven lo que espera Runner se sabe al ejecutar el Flow.
