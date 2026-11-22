# Diseñador de Flows

El **diseñador de Flows** dibuja un Flow de [Runner](https://github.com/divengine/runner) como un tablero que trabajas con el teclado:
- sus Blocks como **carriles**, uno al lado del otro en el orden en que están escritos, con el primero marcado **ENTRADA** (donde empieza el Flow);
- los Steps de cada Block como **tarjetas** a lo largo de su carril, en el orden en que se ejecutan;
- cada `call` y cada `jump` como una **línea** desde el Step que lo tiene hasta el Step al que lleva.

Desde el tablero creas Blocks y Steps, los renombras, los reordenas y los borras, editas lo que hace un Step y conectas Steps eligiendo el destino en el tablero. Nunca escribes un destino `block.step`. Como la [[ventana Flow|Flow Structure]], verifica el Flow con Runner y lo ejecuta ([[Ejecutar Flows|Running Flows]]).

![El diseñador de Flows en fulfil.yml a 120 columnas: main.review elegido, su call a review.check escogido, el inspector a la derecha](images/flow-designer-120.png)

**El archivo YAML es el Flow.** El tablero no tiene un modelo propio. Nada del tablero, como su disposición o lo elegido, se guarda en ningún sitio:
- El tablero dibuja el buffer de la ventana de código que tiene el Flow abierto. Las líneas se calculan cada vez a partir de los valores de `call` y `jump`.
- Cada cambio hecho en el tablero es una edición de ese buffer. Deshacer (Ctrl+Z), Rehacer (Ctrl+Y), la marca de modificado y F2 funcionan como en el código.
- Escribir en el código vuelve a dibujar el tablero.
- Nada llega al disco hasta que guardas.

## Abrirlo

En la ventana de código de un Flow (un archivo YAML cuya raíz tiene `blocks`), usa **Ejecutar > Diseñador del Flow**. Se abre en el lugar del código, en el Step bajo el cursor.
- **Ctrl+T** va al código, con el Step o Block elegido seleccionado. Ctrl+T en el código vuelve al tablero: reabre la última vista del Flow que usaste.
- **Ctrl+D** cambia entre el tablero y el árbol de la [[ventana Flow|Flow Structure]], conservando el Step o Block elegido.

## El tablero

![El mismo tablero a 160 columnas: cuatro carriles, las líneas de call y jump entre ellos](images/flow-designer-160.png)

- **La línea de arriba** dice cuántos Blocks y Steps tiene el Flow, y qué significan las líneas.
- **El título de un carril** es el número y el id del Block, con **ENTRADA** en el primero, y debajo su descripción (o cuántos Steps tiene). Los títulos se quedan arriba mientras las tarjetas se desplazan.
- **Una tarjeta** es un Step. Su borde de arriba lleva su número y su id, y sus filas dicen lo que hace, en el orden en que lo hace Runner:

  | Fila | Qué es |
  |---|---|
  | `IF needs_approval()` | `condition`: el Step solo hace algo cuando devuelve true |
  | `SET approved: true` | `context`: los valores que pone el Step |
  | `CALL review.check` | `call`: ir allí y volver |
  | `DO billing:total()` | `activity`, con su `module` antes de los dos puntos |
  | `JUMP .reserve` | `jump`: seguir desde allí, sin volver |
  | `PAUSE` | `pause`: el Flow se pausa después del Step |

  Una tarjeta sin ninguna de estas filas dice *(nada que hacer)*.
  - Marcas en su borde de arriba: **!E** quiere decir que el Step tiene un error, **!W** un aviso, **RO** que está escrito de una forma que el tablero muestra pero no edita.
  - En su borde de abajo, **◄2** dice cuántos call y jump llevan a él.
- **Las líneas.** Cada `call` y cada `jump` sale de la fila `CALL` o `JUMP` de su tarjeta y termina en una flecha (`►` o `◄`) en la tarjeta de destino. Se distinguen sin color:
  - un **call** es una línea simple (`─ │`, salida `├`) y vuelve al Step que llamó cuando termina el Block llamado;
  - un **jump** es una línea doble (`═ ║`, salida `╞`) y sigue desde su destino sin volver;
  - un destino que el Flow no tiene termina en **`?`**.

  Las líneas van entre los carriles y entre las filas de tarjetas, nunca por encima de una tarjeta. Donde dos líneas se cruzan, el cruce se dibuja como un cruce (`┼ ╫ ╪ ╬`). Un `call` o un `jump` a `block.` (el primer Step del Block) lleva a ese primer Step, o al título del carril cuando el Block no tiene Steps.
- **Lo elegido.** La tarjeta (o el título) elegida se dibuja en vídeo inverso y sus líneas en negrita. La conexión que escoges con Tab también se dibuja en vídeo inverso. Funciona igual en todos los temas, incluidos los temas de fósforo monocromos.
- **El inspector**, a la derecha (debajo del tablero cuando la ventana tiene menos de 100 columnas), muestra lo elegido, como en la ventana Flow:
  - de un Step: sus atributos, adónde llevan su call y su jump, y el archivo de función de su activity o su condition;
  - de un Block: sus Steps y qué Steps llevan a él;
  - los problemas encontrados;
  - con una conexión escogida, qué es: un call o un jump, desde dónde y hacia dónde.
- **Debajo del inspector: el veredicto de Runner.**

A 80 columnas el tablero muestra dos o tres carriles y el inspector va debajo. Los terminales más anchos muestran más carriles y tarjetas más anchas. El tablero se desplaza con lo elegido.

## Teclas

| Tecla | Qué hace |
|---|---|
| **↑ ↓** | El Step anterior o siguiente del carril; ↑ desde el primer Step elige el título del carril (el Block) |
| **← →** | El carril de la izquierda o de la derecha, a la misma altura |
| **Inicio / Fin** | El título del carril, su último Step |
| **RePág / AvPág** | Desplazar |
| **Tab / Mayús+Tab** | Las conexiones de lo elegido, una a una: primero las que tiene, luego las que llevan a él |
| **Intro** | En una conexión escogida: ir a su otro extremo. En un Step: editarlo. En el título de un carril: editar el Block |
| **Esc** | Dejar la conexión escogida, o dejar de elegir un destino |
| **Retroceso** | Volver a donde estabas antes de seguir una conexión |
| **Ctrl+Intro** (Ctrl+J) | Ir al otro extremo de la conexión escogida, si no al destino del call o jump del Step; en un Step sin ninguno, abrir el archivo de su activity o su condition |
| **C / J** | Conectar el Step elegido con un `call` / `jump`: elige su destino en el tablero |
| **Ins** | Un Step nuevo después del elegido (en el título de un carril: al final del Block) |
| **B** | Un Block nuevo después del de lo elegido, con su primer Step |
| **Supr** | Borrar el Step o el Block (se pregunta antes), o quitar la conexión escogida |
| **Ctrl+↑ / Ctrl+↓** (también Alt) | Subir o bajar el Step dentro de su Block |
| **Ctrl+← / Ctrl+→** (también Alt) | Mover el Block a la izquierda o a la derecha |
| **Ctrl+D** | El árbol de la ventana Flow, en el mismo elemento |
| **Ctrl+T** | El YAML, en el Step o Block elegido |
| **Alt+F9** | Verificar el Flow, con los problemas en Mensajes |
| **Ctrl+F9** | Ejecutar el Flow ([[Ejecutar Flows|Running Flows]]) |
| **F2** | Guardar |
| **Ctrl+Z / Ctrl+Y** | Deshacer / rehacer, los del código |

El ratón es opcional: un clic elige una tarjeta o un título, y un doble clic lo edita.

## Construir un Flow

Un Flow nuevo solo necesita un `id` y un `blocks:` vacío en su archivo YAML. En el tablero:

1. **B** crea un Block. Da su id, una descripción opcional, el id de su primer Step y la activity de ese Step (**Abajo** ofrece los archivos de función). Se escribe después del Block elegido, sangrado como los demás.
2. **Ins** añade un Step después del elegido, con el mismo diálogo que en la ventana Flow: module, condition, activity, call, jump, context, pause.
3. **C** (o **J**) en un Step empieza una conexión. La línea de arriba dice `CALL desde main.greet: elige el destino...`. Ve a la tarjeta de destino y pulsa **Intro**: divide escribe `call: check.mark`, la forma explícita `block.step`. En el título de un carril, Intro escribe `check.`, que lleva al primer Step de ese Block, sea cual sea. **Supr** en cambio quita el call (o el jump) del Step, y **Esc** cancela.
4. **Alt+F9** pide a Runner que lo verifique, **F2** lo guarda y **Ctrl+F9** lo ejecuta.

![Eligiendo el destino del jump de stock.short: la línea de arriba dice qué hacen Intro, Supr y Esc](images/flow-designer-connect.png)

## Editar, renombrar, reordenar, borrar

- **Intro en un Step** abre su diálogo con su **id** primero. Cambiar el id renombra el Step. Todos los `call` y `jump` que llevan a él cambian con él, con las comillas con que está escrito cada uno, y también los `.step` escritos en su propio Block. El resultado de una activity se guarda en el contexto con el id de su Step, así que el código que lee `$context['id_viejo']` también tiene que cambiar; el diálogo lo dice.
- **Intro en el título de un carril** edita el Block: su id (un renombrado que cambia todos los `call` y `jump` que lo nombran) y su descripción.

  ![Editando el Block stock: su id y su descripción](images/flow-designer-block.png)
- **Ctrl+↑ / Ctrl+↓** mueve un Step dentro de su Block, lo que cambia el orden en que se ejecutan sus Steps.
  - Mover un Step al primer lugar, o sacarlo de él, cambia a qué lleva `block.`. Si algún `call` o `jump` está escrito así, se pregunta antes.
  - Un Step se queda en su Block. Para pasar un Step a otro Block, córtalo y pégalo en el código.
- **Ctrl+← / Ctrl+→** mueve el Block. El primer Block es donde empieza el Flow, así que mover un Block al primer lugar, o sacarlo de él, se pregunta antes, diciendo cuál será el Block de entrada.
- **Supr** borra el Step o el Block elegido, después de decir:
  - qué Steps llevan a él con un `call` o un `jump`;
  - que el Flow empezará en otro sitio, cuando es el Block de entrada;
  - cuántos comentarios tiene escritos.

  Borrar quita también esas líneas de `call` y `jump`, en la misma edición. Un Ctrl+Z lo devuelve todo. Un Flow conserva al menos un Block.
- **Supr en una conexión escogida** (antes, Tab) quita ese `call` o ese `jump`.

Cada una de estas operaciones es una edición: un Ctrl+Z la deshace, con sus referencias.

### Solo se escribe lo que tiene que cambiar

El tablero cambia el texto YAML en su sitio, como la ventana Flow ([[Solo se escribe lo que cambias|Flow Structure]]). Nunca vuelve a escribir el archivo desde un modelo:
- **Mover** intercambia dos Steps (o Blocks) vecinos, texto por texto. Cada uno conserva sus líneas exactamente como están escritas: sus comentarios, las líneas de comentario justo encima, las comillas y las líneas en blanco de dentro. Las líneas en blanco y los comentarios que hay entre los dos se quedan donde estaban.
- **Renombrar** sustituye los caracteres del id y de cada destino que lo nombra, y nada más. `call: 'review.check'   # back here` pasa a `call: 'review.inspect'   # back here`.
- **Un Block o un Step nuevo** son líneas nuevas, sangradas como sus hermanos (dos espacios, cuatro...).
- **Borrar** quita las líneas del propio elemento, con las líneas de comentario justo encima de él. Cada `call` o `jump` que llevaba a él pierde solo su propia línea.

divide vuelve a leer el resultado antes de quedárselo. Si cambiara algo más (otro valor, el orden de los Blocks, un comentario que no es del elemento borrado), la edición se deshace y se te dice.

**Lo que se rechaza**, con un mensaje que dice por qué y sin cambiar nada. Estos cambios se hacen en el código (Ctrl+T):
- quitar una línea de `call` o `jump` que tiene un comentario;
- quitar lo único que hace un Step: un Step vacío no es un Step válido, así que cambia o borra ese Step primero;
- mover dos elementos con distinta sangría, o con otra cosa escrita en la misma línea que su clave;
- renombrar a un id que el Flow ya tiene, o que empieza por `_` o tiene un punto (las reglas de Runner para los ids);
- borrar el único Block;
- renombrar o borrar mientras los Steps de un Block están escritos en estilo flow (`steps: {a: {jump: main.s}}`): un `call` o `jump` allí no se podría seguir.

Un Block o Step cuyo id ya usa uno anterior no se dibuja, y la línea de arriba lo nombra: Runner también lo rechaza, así que corrígelo en el código.

## Cuando el YAML no se puede leer

![El YAML roto en el código: el tablero conserva el último diseño que se leyó, de solo lectura](images/flow-designer-readonly.png)

Si el código deja de ser YAML válido (a medio escribir, o con un corchete sin cerrar), el tablero sigue mostrando **el último diseño que se leyó** y dice **SOLO LECTURA** en su línea de arriba. El inspector lista los problemas.
- Nada en el tablero edita el Flow: cada tecla que editaría dice *Corrige primero el YAML en el código*. Tu texto sin guardar nunca se toca.
- **Ctrl+T** va al código, al primer problema. Cuando el YAML vuelve a leerse, el tablero lo sigue y puede editar de nuevo.

## Problemas

El tablero, el código (como marcas bajo el texto) y Mensajes (**Alt+F9**) muestran los mismos problemas. Una tarjeta o un carril con un error dice **!E**, y uno con un aviso **!W**. Se encuentran como en la ventana Flow:
- con el propio compilador de Runner, sin ejecutar nada;
- con las búsquedas de divide de destinos que faltan y archivos de función que faltan.

Consulta [[Problemas|Flow Structure]].

## Límites

- El tablero es un espacio de diseño, no un depurador. No simula un Flow, no lo reproduce, no lo ejecuta paso a paso ni lo detiene en puntos de ruptura. Ejecutar es cosa de Runner, mediante [[Ejecutar Flows|Running Flows]].
- Los Steps solo se mueven dentro de su Block, y los Blocks se crean con su primer Step.
- Los destinos de `call` y `jump` de un Step se eligen en el tablero. Sus demás atributos se editan en el diálogo del Step. Un `context` es allí una línea, `{clave: valor, ...}`.
- La disposición es fija: carriles en el orden del YAML y tarjetas en el orden de sus Steps. Nada del tablero se guarda.
