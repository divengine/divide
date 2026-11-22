# Functions del Flow

Un Step de un Flow de [Runner](https://github.com/divengine/runner) hace su trabajo con **Functions**: su `condition` y su `activity` las nombran. Una Function es un archivo PHP que devuelve un callable, y Runner lo llama con el contexto compartido del Flow:

```php
<?php

declare(strict_types=1);

return function (array &$context): mixed {
    $context['seen'] = true;   // lo que pones en el contexto queda para los Steps siguientes
    return 'done';             // el resultado de una activity: Runner lo guarda en $context[<el id del Step>]
};
```

- Una **condition** devuelve true o false: true ejecuta la activity, el call o el jump del Step, y false los salta.
- Una **activity** hace el trabajo. Lo que devuelve se guarda bajo el id del Step.
- Un **Module** es una carpeta de Functions, nombrada por el `module` de un Step. Se aplica a la condition y a la activity del Step, no a su call ni a su jump. Un Module no es un Block, y una Function no es un Step.
- Por dentro, una Function es PHP normal: el autoload de Composer, `require` de otros archivos, y otras Functions con el importador de Runner, `$context['_importer']('name', 'module')`, que devuelve el callable de esa Function.

La **ventana Functions** muestra dónde están las Functions de un Flow, los Modules y las Functions de cada uno, qué Steps usan cada una y qué referencias no llevan a ningún sitio. Desde ella, y desde el diálogo del Step, creas Modules y Functions sin escribir tú las carpetas ni el `return function (...)`. Los archivos son archivos PHP normales, que se abren en el [[editor de PHP|Editing PHP]], con su lint, su servidor de lenguaje y su [[depurador|Debugging PHP]].

![Desde el diseñador de Flows: F, un Module nuevo y una Function dentro desde una plantilla, su PHP escrito y guardado, un Step nuevo que la usa, y el Flow ejecutado por Runner con el resultado del Step en el contexto](images/flow-functions.gif)

## Abrirla

- **F** en el tablero del [[diseñador de Flows|Flow Designer]].
- **Ejecutar > Functions del Flow**, desde el código de un Flow, su [[ventana Flow|Flow Structure]] o su tablero: la ventana de ese Flow. Desde cualquier otro sitio: la del proyecto.

La ventana tiene las Functions como un árbol a la izquierda y lo que es el elemento elegido a la derecha. A 80 columnas, la parte de la derecha va debajo del árbol.

![La ventana Functions del Flow del generador a 120 columnas: la raíz functions/ de .div/runner.json, sus Modules, render:php_class elegida y el Step que la usa](images/flow-functions-120.png)

![La misma ventana a 80 columnas: el Module validate elegido, lo que es debajo del árbol](images/flow-functions-80.png)

| Fila | Qué es |
|---|---|
| **Raíz de funciones** `functions/` | La raíz, y de dónde sale (ver abajo). Debajo, las Functions de la raíz: `load_model` es `functions/load_model.php` |
| **`render/`** | Un Module: `render:php_class` es `functions/render/php_class.php`. Un Module asignado a otra carpeta muestra `-> su carpeta`; uno fuera del proyecto, **(fuera: solo lectura)** |
| **`php_class`** `activity · 1 Step(s)` | Una Function, cómo la usan los Steps y cuántos. **→** despliega los Steps |
| **! No encontradas** | Las referencias de Steps que no llevan a ningún archivo. **?**: un nombre sin Module que Runner aún puede encontrar como callable de PHP (`strlen`, `ns\fn`, `Cls::method`) |

A la derecha, para una Function:
- su archivo y su Module;
- lo que devuelve el archivo, leído sin ejecutarlo: un closure y sus parámetros, una arrow function, u otro callable, que no se lee más;
- los Steps que la usan (`main.load (activity)`), en todos los Flows del proyecto, los abiertos tal como están en su editor, con los cambios sin guardar;
- las Functions que importa con `$context['_importer']('lint', 'quality')` y las que la importan. Una importación cuyo nombre se calcula se muestra como `?`, desconocida, nunca como un problema;
- lo que Runner no podría hacer con ella (ver Problemas).

En la fila de la raíz, el contrato de arriba y dónde busca Runner.

## Teclas

| Tecla | Qué hace |
|---|---|
| **↑ ↓ ← →** | Moverse, plegar, desplegar |
| **Intro** | En una Function: abrirla en el editor de PHP, en su `return`. En un Step: ese Step en el diseñador de Flows. En una referencia que falta: crearla (abajo). En un Module: plegarlo o desplegarlo |
| **Ins** | Una Function nueva, en el Module bajo el cursor (si no, en la raíz) |
| **Shift+Ins** | Un Module nuevo |
| **Alt+F10** (Shift+F10) | El menú de la ventana: Function..., Module..., Ajustes (`.div/runner.json`) |
| **Ctrl+F9** | Probar la Function bajo el cursor: ejecutarla o depurarla con un contexto JSON (abajo) |
| **Ctrl+R** | Leer el disco otra vez (también se hace al guardar un archivo PHP, un Flow o los ajustes) |
| escribir | Filtrar las filas |

## Crear un Module

**Shift+Ins** pide su nombre: letras, dígitos, `_` y `-`, como permite el `module` de Runner. Se crea como carpeta de la raíz (`functions/publish/`), o como la carpeta que le da `_modules`. Un Module que ya existe no se vuelve a crear.

## Crear una Function

**Ins** abre **Nueva Function**:
- **Module**: el Module (**Abajo** ofrece los que hay). Vacío: la raíz.
- **Nombre**: letras, dígitos, `_` y `-`. En un Module, también `carpeta/nombre` (`tax/compute`), como permite Runner. Sin `.php`: Runner lo añade.
- **Uso**: **Activity** o **Condition**.

![Nueva Function en el Module render: el nombre slug, su uso, y dónde se escribirá y qué dice un Step para usarla](images/flow-functions-new.png)

Debajo, el diálogo dice dónde quedará el archivo y qué dirá un Step para usarla (`module: render, activity: slug`), o por qué no se puede crear. **OK** escribe el archivo, crea sus carpetas si no están, y lo abre en el editor de PHP en su callable.

El archivo es una Function de PHP 8.1 mínima y válida: una condition devuelve `bool` (`true`), una activity devuelve `mixed` (`null`), cada una con un comentario que dice qué son el contexto y el valor devuelto. Es un comienzo, no un formulario que haya que mantener: escribe ahí cualquier PHP. divide nunca reescribe una Function, generada o no.

Lo que nunca se hace:
- escribir sobre un archivo que ya existe (ábrelo en su lugar);
- escribir fuera del proyecto, en la carpeta `vendor` de Composer o en una carpeta oculta. Un Module asignado allí se muestra, y aquí es de solo lectura;
- ejecutar el PHP de una Function para listarla o leerla.

**Intro en una referencia que falta** abre el mismo diálogo con su Module, su nombre y su uso puestos. El Step ya la nombra, así que el Flow no cambia.

## Desde un Step

En el diálogo del Step (Intro en una tarjeta, Ins para un Step nuevo, en el diseñador de Flows y en la ventana Flow):
- **Abajo** en Module ofrece los Modules, y en Condition o Activity las Functions de ese Module (o de la raíz).
- **Function...** trata de la activity del Step, o de su condition cuando ese es el campo en el que estabas:
  - **Abrir**: su archivo en el editor de PHP, una vez escrito el Step (como **OK**).
  - **Probar...**: el diálogo Probar Function para ella, una vez escrito el Step (ver Probar una Function).
  - **Nueva...**: el diálogo Nueva Function, con el Module del Step. Su **OK** rellena el `module` y la `activity` (o la `condition`) del Step y dice que el archivo se va a crear. Todavía no se escribe nada: el **OK** del diálogo del Step escribe el Step, como una sola edición del YAML (un Ctrl+Z), crea el archivo y lo abre. **Cancelar** no escribe ni crea nada. Si el Step no se puede escribir, el archivo nuevo se quita.

![El diálogo del Step después de Function... > Nueva...: module y activity rellenos, y la nota de que OK escribe el Step y crea functions/render/publish.php](images/flow-functions-step.png)

Un Step tiene un solo `module`, para su condition y su activity: se rechaza una Function nueva en otro Module que el de la otra Function del Step.

**Ctrl+Enter** en un Step (en el tablero, en la ventana Flow o en su línea del código) abre el archivo de su Function. Cuando no lo hay, dice dónde buscó Runner.

## Probar una Function

**Probar Function** llama a una Function sola, con el contexto que le des, y muestra lo que hizo: qué devolvió, cómo cambió el contexto, qué imprimió, y cualquier excepción o error con su lugar. No ejecuta un Flow ni un Step.

> **Ejecuta el código PHP real del proyecto.** La Function y todo lo que llama pueden escribir archivos, usar una base de datos o la red. La prueba se ejecuta en un proceso PHP propio, con un límite de tiempo y uno de memoria, pero eso no es un sandbox, y el depurador tampoco lo es. Prueba solo código en el que confías.

Se abre con:
- **Ctrl+F9** sobre una Function en la ventana Functions (sobre uno de sus Steps: como la usa ese Step);
- **T** sobre un Step en el diseñador de Flows: su activity, si no su condition;
- **Function... > Probar...** en el diálogo del Step: la activity, o la condition si ese era el campo en el que estabas.

La Function es la que cargaría una ejecución del Flow: la resuelve el propio importador de Runner, con la raíz de funciones y las carpetas de los Modules del Flow (ver Dónde busca Runner, abajo), incluidos los `_modules`. Con un Module, no se prueba nada fuera de su carpeta: nunca se ejecuta en su lugar el mismo nombre de otro Module.

El diálogo:
- **Contexto**: un objeto JSON, el contexto que recibe la Function, por referencia. **Editar...** lo abre como árbol o como texto JSON, el editor del contexto de un Step. La última entrada de cada Function se recuerda en tus propios ajustes, nunca en el proyecto.
- **Escenario**: un nombre para esta entrada. **Guardar** lo escribe en el proyecto, en `.div/function-tests/<module>/<nombre>.json`, como fixture para el equipo; no se guarda nada ahí si no lo guardas. **Abajo** ofrece los guardados, y elegir uno rellena los campos.
- **Valor devuelto esperado** (JSON) y **Contexto esperado después** (un objeto JSON: las claves que debe tener el contexto después, un subconjunto): comprobaciones opcionales.
- **Límite de tiempo**, en segundos (30 por defecto): pasado, PHP se termina.
- **Ejecutar** (Intro) la ejecuta, en un cuadro que **Esc** detiene. **Depurar** la ejecuta en el depurador.

Los archivos PHP sin guardar se guardan antes: PHP ejecuta lo que está en el disco.

### El informe

La ventana de salida tiene, cada parte por separado:
- el archivo que cargó el importador de Runner, y cómo terminó la llamada: devolvió, excepción, error fatal, `exit()`, no encontrada, límite de tiempo, detenida;
- lo esperado, `ok` o `FAIL`;
- **el valor devuelto**, como JSON (objetos, closures y recursos descritos), y su tipo. Es una llamada directa: en un Flow, Runner guardaría el resultado de una activity en `$context[<el id del Step>]`; aquí no se ejecuta ningún Step, así que solo se devuelve. Para una condition, el informe dice qué haría el valor con un Step (true lo ejecuta, false salta el resto);
- la clase, el mensaje, el archivo y la línea de una excepción, y su traza; el mensaje y el lugar de un error fatal;
- **los cambios del contexto**, clave por clave (`+` añadida, `~` cambiada, `-` quitada), y después el contexto antes y después;
- **stdout** y **stderr**, lo que imprimió la Function, nunca mezclado con el resultado.

El lugar de una excepción o de un error fatal, los avisos de PHP y lo esperado que falla van a Mensajes, donde Intro abre el archivo en esa línea.

### Depurar una Function

**Depurar** hace la misma llamada en el [[depurador|Debugging PHP]], con Xdebug. Cuando el archivo de la Function no tiene ningún punto de ruptura, el depurador se para en la primera línea de la Function; si no, va hasta tus puntos de ruptura, en la Function o en cualquier archivo PHP que llame. Después **F7**, **F8**, **Shift+F8**, **F4**, las inspecciones, la pila de llamadas y **Ctrl+F4** funcionan como en cualquier script PHP, **Ctrl+F9** sigue y **Ctrl+F2** termina. Al terminar, el mismo informe aparece en la ventana de salida.

### Cómo llama a la Function

Un pequeño harness PHP que viene con divide, en la carpeta del proyecto:
1. carga el autoload de Composer del proyecto (`vendor/autoload.php`) y Runner;
2. resuelve la Function con `runner::importer()`;
3. la llama como Runner llama a una condition o una activity, `$func($context)`, con `$context['_importer']` en el contexto para que pueda importar otras Functions;
4. escribe el resultado en un archivo temporal propio.

Nunca escribe el contexto guardado de un Flow (`.div/runner/`), la Function ni ningún archivo tuyo.

## Dónde busca Runner

La raíz y las carpetas de los Modules siguen las reglas de Runner, las mismas que en una ejecución ([[Ejecutar Flows|Running Flows]]). Cuenta lo primero que dé uno:

| | |
|---|---|
| **La raíz** | la **Raíz de funciones** del diálogo Ejecutar Flow (`--root`); si no, el `_root_folder` del contexto inicial; si no, el `root` de `.div/runner.json` del proyecto; si no, la carpeta del proyecto (lo que Runner usa por defecto, `./`) |
| **La carpeta de un Module** | los `_modules` del contexto inicial; si no, los `modules` de `.div/runner.json`; si no, `<raíz>/<module>` |
| **Un nombre sin Module** | `<raíz>/<nombre>.php`; si no, `<nombre>.php` desde la carpeta del proyecto; si no, un callable de PHP con ese nombre |

Con un `module`, Runner busca solo en la carpeta de ese Module: el mismo nombre en dos Modules son dos Functions, y una Function de la raíz con ese nombre es una tercera.

## Los ajustes del proyecto: .div/runner.json

Sin nada más, los campos del diálogo Ejecutar Flow se recuerdan para cada Flow y cada usuario. Para un proyecto cuyas Functions están siempre en la misma carpeta, `.div/runner.json` lo dice una vez, para todos los que clonen el proyecto:

```json
{
    "root": "functions",
    "modules": {"shared": "../shared/functions"}
}
```

- Las dos claves son opcionales, y el archivo también. Las rutas son relativas al proyecto.
- Es lo que el proyecto da por defecto, por debajo de lo que digan un Flow o un contexto (arriba). El contexto sigue siendo la entrada de negocio del Flow: no hace falta poner nada en él para que divide encuentre las Functions.
- Una ejecución le da a Runner lo que añade el archivo: su `root` como `--root` cuando ni el Flow ni el contexto dan uno, y sus `modules` añadidos a los `_modules` del contexto, donde el contexto no los asigna. Runner no lee el archivo.
- **Alt+F10 > Ajustes** lo crea, después de preguntar, con la raíz que muestra la ventana en ese momento, y lo abre.
- `examples/generator` tiene uno: `"root": "functions"`.

## Problemas

Lo que la ventana marca con **!** se marca también en el Flow, en la `activity` o la `condition` del Step, en el código, en el tablero y en Mensajes (**Alt+F9**):
- una referencia sin archivo donde busca Runner (un error, o un aviso cuando Runner aún puede encontrar un callable de PHP con ese nombre);
- un archivo que no devuelve nada (sin `return` en su nivel superior): Runner necesita un callable;
- un closure que necesita más de un argumento (Runner solo le pasa el contexto), o cuyo primer parámetro tiene otro tipo que array.

Solo la ventana dice, como nota, que un closure recibe el contexto por valor (`array $context`). Está bien para uno que solo lo lee, pero lo que cambie en él se pierde.

Cualquier otro callable no se juzga: un objeto invocable, el nombre de una función, `require` de otro archivo. Los errores de PHP de una Function son del editor de PHP, como en cualquier archivo PHP.

## Límites

- La ventana crea Modules y Functions; no los renombra, mueve ni borra. Eso es de la [[ventana de proyecto|Project Window]], y entonces las referencias del Flow las cambias tú.
- Una prueba de Function ejecuta PHP real, una vez; no simula una Function con mocks, ni un Flow. Ejecutar un Flow es de Runner ([[Ejecutar Flows|Running Flows]]).
- Las referencias se leen donde están escritas literalmente. Una importación cuyo nombre se calcula al ejecutar es desconocida.
