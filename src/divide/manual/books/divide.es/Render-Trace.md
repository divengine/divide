# Traza del render

**Depurar > Traza del render** (**F7** en una plantilla) renderiza la plantilla como lo hace [[Ctrl+F9|Rendering]], y guarda cada cambio que Div hizo por el camino, para que puedas reproducir cómo la plantilla se convirtió en su salida.

![la fila donde Div decide una condición: lo que se queda, en verde](images/trace.png)

## Por qué no línea a línea

Una plantilla Div no se ejecuta de arriba abajo. Div reescribe la plantilla entera una y otra vez: decide las condiciones, pega los includes, despliega las listas, reemplaza las variables, formatea los números… Cada reescritura puede traer etiquetas nuevas (un include trae las suyas), así que Div sigue hasta que un ciclo entero no cambia nada: un **punto fijo**. Partes de la plantilla se analizan aparte, cada una con un motor propio: cada elemento de una lista, la expresión de una condición.

Así que la traza no es una lista de líneas sino una lista de **mutaciones**: lo que era la plantilla, en qué se convirtió y qué paso de Div lo hizo.

## La ventana

- **Las filas**, abajo, una por mutación, en el orden en que Div las hizo:
  - `► Plantilla`: la plantilla tal como Div empieza con ella.
  - `-30   Condition: {$cart.items} > 0 > The condition 2 > 0 is true`: un cambio. El número es cuántos caracteres añadió o quitó; las palabras son las de Div, de su registro de lo que estaba haciendo.
  - `► Sub-parse: Item 0 of the list 'products'`: Div empieza a analizar una parte aparte. Sus filas van sangradas debajo.
  - `■ Fixed point: nothing changes after 3 cycles`: ese análisis ha terminado.
  - `■ Salida: lo que devuelve Div`: el resultado, el mismo que da Ctrl+F9.
- **La plantilla**, arriba, tal como quedó tras la fila seleccionada. Lo que escribió la mutación se marca en verde.
- **El marco** dice dónde estás: `6/33 · cycle 1 · -30 · after`. La línea de estado muestra la fila completa.

**Espacio** muestra en cambio la plantilla *antes* de la mutación seleccionada, con lo que quitó marcado en rojo. Espacio otra vez vuelve a después.

![la misma fila antes de la mutación: la condición que desapareció, en rojo](images/trace-before.png)

## Teclas

Las teclas del depurador, sobre las filas:

| Tecla | Acción |
|---|---|
| **↑ / ↓** | la fila anterior / siguiente |
| **F8** | la fila siguiente del mismo análisis, por encima de sus sub-análisis |
| **F7** | la fila siguiente, dentro de los sub-análisis |
| **Shift+F8** | salir: la fila siguiente del análisis que empezó este |
| **Espacio** | antes / después de la mutación |

## Cómo funciona

Div no se modifica. divide renderiza con una subclase de Div cuyo `logger()` (Div lo llama en cada paso de su analizador cuando su modo de registro está activo, `div::logOn()`) anota el paso, el motor y la plantilla entera cada vez que cambió. Las etiquetas son los mensajes de registro de Div, abreviados. La salida es lo que Div renderizó, la misma que sin la traza.

## Límites

- Es una reproducción: el render ya ha ocurrido cuando se abre la ventana. Te mueves por él en los dos sentidos, pero no puedes cambiar los datos a mitad.
- El analizador de Div decide cuánto abarca cada fila: un paso puede hacer varios cambios a la vez (todas las coincidencias de un ciclo, por ejemplo), y un paso que no cambia nada no tiene fila.
- Los renders muy largos se cortan (64 MB de instantáneas, 50 000 pasos); la caja de progreso lo indica.

Volver: [[Renderizado|Rendering]].
