# Traducir plantillas

Div puede reescribir una plantilla de un dialecto a otro. **Herramientas > Traducir una plantilla...** lo convierte en un asistente. También está en el menú local del [[Dialector]], con el dialecto del dialector como destino.

![traducción de index.tpl a un dialecto parecido a ERB](images/translate.png)

## Los tres campos

- **Plantilla:** la plantilla que traducir. Se propone la plantilla activa. Si la plantilla está abierta, se usa el texto de su editor, guardado o no.
- **Dialecto de origen:** el dialecto en el que está escrita la plantilla. Normalmente se sabe: una plantilla escrita en otro dialecto lo dice con `@_DIALECT`, y una que no dice nada está en el dialecto por defecto de Div. Así que divide lo **sugiere**. Lee el `@_DIALECT` de la plantilla y deja que Div encuentre el archivo igual que al renderizar (`getTplPath()`), o sugiere el de Div por defecto cuando no hay ninguno. Una nota bajo el campo dice de dónde viene la sugerencia. Aún puedes escribir otro dialecto; en cuanto lo haces, divide deja de sugerir.
- **Dialecto de destino:** el dialecto al que traducir. Déjalo vacío para el dialecto por defecto de Div.

Las rutas son relativas al proyecto, y un dialecto vacío significa el de Div por defecto. Cada campo tiene un botón **...** que abre el diálogo de archivos y escribe la ruta **absoluta** del archivo elegido. Acórtala a una relativa si lo prefieres. Elegir un archivo con **...** previsualiza enseguida.

## Previsualizar, guardar, abrir

- **Vista previa** (Enter) pide a Div que traduzca (`div::translate()`, con los archivos de dialecto decodificados por el propio `jsonDecode()` de Div). El resultado se resalta en el dialecto de destino.
- **Guardar como...** escribe la traducción junto a la plantilla (se propone `index.erb.tpl`; **Examinar...** elige otro lugar) y la abre.
- **Abrir** pone la traducción en una ventana nueva, sin guardar.

La plantilla original nunca se modifica. El `@_DIALECT` de la traducción sigue al destino: nombra el dialecto de destino, relativo a donde se guarda el archivo, o desaparece cuando el destino es el dialecto por defecto de Div.

## Lo que Div no traduce

La traducción es la de Div, tal como Div la hace hoy. Conviene revisar dos cosas en la vista previa:

- Los includes preprocesados `{%% path:data %%}` pierden su separador `:`.
- Los includes dentro de un bucle o una condición se quedan en el dialecto de origen.

El veredicto del [[Dialector]] muestra lo primero como una sección que Div lee de otra forma (`≈`).
