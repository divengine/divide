# Autocompletado

divide completa mientras escribes, a partir de lo que tu plantilla puede ver de verdad.

## Mientras escribes

La lista se abre sola después de:

| Escribes | Obtienes |
|---|---|
| `{$`, `{^$`, `{html:$`… (cualquier modificador) | variables, y el `}` de cierre |
| `[$` | listas que recorrer (primero los arrays); el bucle se cierra por ti con `[/$name]` |
| `[/$` | los bucles abiertos en ese punto |
| `?$` / `!$` | variables, y el `$name?` / `$name!` correspondiente |
| `$` dentro de `{?( … )?}`, `(# … #)` o `{= … =}` | variables |
| `{% ` / `{%% ` | carpetas y plantillas (sin `.tpl`, como se escriben los includes) |

Al escribir se acota la lista (primero por prefijo, luego en cualquier parte del nombre). **↑/↓**, **PgUp/PgDn** mueven, **Enter** o **Tab** inserta, **Esc** cierra, y un clic elige un elemento.

![variables dentro de un bucle](images/completion-variables.png)

## De dónde salen las variables

En este orden:

1. **Los bucles abiertos**, el más interno primero: el elemento (`value`, o el nombre que le diste: `[$products] product => …`), sus campos como `product.name` y también directamente como `name`, y las variables de bucle de Div `_index`, `_key`, `_order`, `_is_first`, `_is_last`, `_is_odd`, `_is_even`, `_list`, `_item`…
2. **El archivo de datos** de la plantilla (`page.tpl` → `page.json`, o el elegido en Ejecutar > Archivo de datos), con miembros con punto como `site.name`. Si el archivo de datos está abierto, se usa su texto sin guardar; mientras está roto, se usa la última versión buena.
3. **Las variables de plantilla** definidas con `{= name: … =}`.
4. **Los nombres ya usados** en otras partes de la plantilla.

Cada entrada muestra su tipo a la derecha: `string`, `number`, `bool`, `array[3]`, `object`, `loop products`, `variable de plantilla`…

## Ctrl+Space

**Ctrl+Space** (o Editar > Completar) abre la lista dondequiera que estés. Donde no se aplica ninguno de los casos anteriores, ofrece las construcciones de Div como fragmentos, escritas con las etiquetas de tu dialecto: reemplazo, bucle, condición (con y sin `@else@`), variable de plantilla, include, include preprocesado, fórmula, comentario, iteración, bloques ignore / txt / strip, location, macro, `@else@`, `@empty@`, `@break@`. Lo que escribiste antes del cursor los acota: `{?` deja las condiciones, `loop` el bucle.

![etiquetas de Div como fragmentos](images/completion-tags.png)

Los fragmentos que abren algo siguen adelante: elegir el bucle escribe `[$` y lista las listas; elegir el include escribe `{% ` y lista las plantillas; elegir una carpeta lista lo que contiene.

![rutas de include](images/completion-includes.png)
