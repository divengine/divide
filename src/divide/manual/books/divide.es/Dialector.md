# Dialector

Un dialecto de Div cambia las etiquetas del lenguaje: `{$name}` puede pasar a ser `<%$name%>`, `[$list]` puede pasar a ser `<% each $list %>`. Escribir uno a mano supone acertar con unas 120 etiquetas y asegurarse de que ninguna choque con otra. El dialector es un asistente para eso. Es la versión de terminal del [dialector web](https://github.com/divengine/dialector), con una vista previa en vivo, y el propio Div verifica cada cambio.

![el dialector: secciones, vista previa y veredicto de Div](images/dialector.png)

## Abrirlo

**Herramientas > Dialector...** lo abre sobre:

- el archivo `.dialect` que estás editando;
- o el dialecto de la plantilla que estás editando (su `@_DIALECT`);
- o un archivo de dialecto nuevo. divide pide un nombre (`my.dialect`); **Examinar...** elige un archivo existente.

El dialector es una vista del archivo `.dialect`, como el árbol de datos lo es de un archivo JSON. **F2** guarda el archivo, **Ctrl+Z / Ctrl+Y** deshacen y rehacen, y cerrar el archivo cierra el dialector. El archivo guarda solo las etiquetas que difieren de las de Div por defecto, como JSON estándar.

Div lee el archivo: el dialector lo decodifica con el propio `jsonDecode()` de Div, como hace Div cuando una plantilla carga el dialecto, así que funcionan las comillas simples y las claves sin comillas. Si Div no puede decodificarlo, el título dice `[invalid JSON]` y el recuadro del veredicto da el motivo de Div; corrígelo en el código. Antes del primer cambio, si el archivo tiene algo que el JSON estándar perdería (comentarios, comillas simples, claves que no son etiquetas de Div), el dialector pregunta antes de reescribirlo. Sin Div, divide lee el archivo por su cuenta.

## La ventana

- **Izquierda: las secciones del lenguaje.** Las secciones son Reemplazos, Modificadores, Varios modificadores, Variables de plantilla, Bucles e iteraciones, Condiciones, Includes y locations, Formatos y fórmulas, Funciones de agregación, Bloques, Cápsulas y sub-parsers, y Caracteres especiales. Cada fila dice cuántas de sus etiquetas cambiaste (`4/11`) y lleva una marca:
  - `•`: la sección tiene cambios;
  - `!`: Div rechaza una etiqueta de esta sección;
  - `≈`: Div lee esta sección de forma distinta a como la escribiste (ver más abajo).
- **Derecha: la vista previa.** Una plantilla de ejemplo que usa todas las construcciones, escrita en tu dialecto y resaltada por divide en tu dialecto. Las etiquetas de la sección seleccionada aparecen marcadas. Al moverte por las secciones, la vista previa se desplaza hasta ellas.
- **Debajo de las secciones:** de qué trata la sección, y el veredicto de Div.

Unas líneas dividen la ventana en estos tres recuadros y la vista previa. Los paneles usan los colores del editor; la sección seleccionada se marca como sus etiquetas en la vista previa.

## Editar una sección

**Enter** (o un doble clic) abre la sección en un diálogo:

- un campo por etiqueta, con la de Div por defecto al lado;
- una vista previa del ejemplo de la sección que sigue lo que escribes, con la etiqueta del campo actual marcada;
- el veredicto de Div para esa sección, en vivo.

**OK** aplica los cambios, **Por defecto** devuelve al diálogo las etiquetas de Div y **Cancelar** descarta los cambios. **Tab** pasa de un campo a otro.

![editar una sección](images/dialector-section.png)

**Supr** devuelve la sección seleccionada a las etiquetas de Div por defecto (Ctrl+Z lo deshace).

## El veredicto de Div

divide no decide si un dialecto funciona: lo decide Div, en dos pasos.

1. **¿Es válido?** Las etiquetas se le dan a Div antes de que cargue, y el propio `isValidCurrentDialect()` de Div las juzga. Comprueba que estén las etiquetas obligatorias y que las que deben ser únicas lo sean. Si una etiqueta está mal, Div dice por qué, por ejemplo `DIV_TAG_BREAK must be unique and not equal to DIV_TAG_EMPTY`, y la sección que contiene la etiqueta recibe un `!`.
2. **¿Lo lee Div?** El ejemplo, escrito en tu dialecto, lo traduce de vuelta el `translateFrom()` de Div y se compara, sección por sección, con el mismo ejemplo en el dialecto por defecto de Div. El veredicto dice cuántas secciones vuelven exactamente igual. Para la primera que no, muestra la línea que escribiste y lo que leyó Div.

El veredicto aparece debajo de las secciones y en cada diálogo de sección, y se actualiza tras cada cambio. Necesita PHP y Div (ver [[Instalación|Installation]]).

## El menú local

**Alt+F10** (o Shift+F10):

![el menú local](images/dialector-menu.png)

| Elemento | |
|---|---|
| **Editar sección...** | el diálogo de la sección (Enter) |
| **Restaurar la sección** | la sección vuelve a las etiquetas de Div (Supr) |
| **Transformar todas las etiquetas...** | reemplaza un trozo de texto en todas las etiquetas a la vez, p. ej. `{` → `{{`. El diálogo lista las etiquetas que cambian antes de que aceptes. |
| **Restaurar todo** | todas las etiquetas vuelven a las de Div por defecto |
| **Importar etiquetas...** | toma las etiquetas de otro archivo de dialecto (decodificado con el propio `jsonDecode()` de Div, comillas simples incluidas, así que funcionan los archivos guardados por el dialector web), o de un archivo PHP con líneas `define('DIV_TAG_…', '…')`. Las etiquetas que el archivo no menciona vuelven a las de Div por defecto. |
| **Exportar como código PHP** | el dialecto como líneas `define()` de PHP, en una ventana nueva. Incluye ese archivo antes de `div.php` para que el dialecto sea el de por defecto en todo un proyecto PHP. |
| **Guardar plantilla de ejemplo...** | escribe el ejemplo en tu dialecto como una plantilla que empieza con `@_DIALECT = your.dialect`, y la abre. Antes se guarda tu archivo de dialecto. |
| **Traducir una plantilla...** | el asistente de [[Traducir plantillas\|Translating Templates]], con este dialecto como destino |
| **Verificar con Div** | preguntar de nuevo a Div ahora |

## Usar un dialecto

Una plantilla usa un dialecto nombrándolo en sus primeras líneas:

```
@_DIALECT = erb.dialect
<h1><%$title%></h1>
```

divide resalta, verifica y autocompleta la plantilla con ese dialecto. Div traduce la plantilla cuando la renderiza. El `examples/shop/erb.dialect` del repositorio es un pequeño dialecto de este estilo.
