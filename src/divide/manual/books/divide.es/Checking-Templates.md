# Verificación de plantillas

divide verifica tu plantilla en cada edición, con su dialecto, y te dice con qué tropezaría Div o qué dejaría en silencio como texto plano.

![errores en el editor y en la ventana Mensajes](images/diagnostics.png)

![errores mientras escribes, la verificación del propio Div, la ventana Mensajes y un arreglo](images/checking.gif)

## Qué se verifica

**Errores** (blanco sobre rojo en el editor):

- bucles que nunca se cierran (`[$products]` sin `[/$products]`) y cierres sin apertura (`[/$orders]`);
- condiciones `{?( … )?}` sin su `{/?}`, y `{/?}` sin nada que cerrar;
- etiquetas a las que les falta el final, que Div dejaría como texto: `<!--{`, `{=`, `{@`, `{?(`, `(#`, `{#`, `{% `, `{%% `, `[:`, `(( `, `{txt}`, `{strip}`, `<!--|`, `{ignore}`;
- un `@_DIALECT` que Div no encuentra o no puede decodificar (Div carga el dialecto por sí mismo: consulta [[Edición de plantillas|Editing Templates]]).

**Avisos** (sobre marrón):

- includes que Div no puede resolver (ver más abajo);
- JSON mal formado en una variable de plantilla, `{= shipping: {"days": } =}`, en el carácter exacto.

## Cómo verlos

- En el editor, el problema se pinta donde está.
- La **línea de estado** muestra el mensaje bajo el cursor, o los totales: `Div · 2 errors, 1 warning (Alt+F8)`.
- **Alt+F9** (Ejecutar > Verificar) verifica el archivo bajo una caja de progreso (el archivo, su lenguaje, sus líneas, luego los errores y avisos encontrados; cualquier tecla la cierra) y abre la ventana **Mensajes** abajo, al estilo de Turbo Pascal: `checkout.tpl(3,1): Error: loop [$cart.lines] is never closed with [/$cart.lines]`. Sigue a la plantilla activa mientras escribes, y debajo se listan los mensajes del último render. **Enter** o un doble clic salta al lugar.
- **Alt+F8** / **Alt+F7** saltan al problema siguiente / anterior, incluso con la ventana Mensajes cerrada.

## Div resuelve los includes

Div encuentra las plantillas incluidas a su manera: relativas al directorio de trabajo, a la carpeta de la plantilla que incluye, a las plantillas incluidas antes, añadiendo `.tpl` cuando falta. divide no lo imita. Se lo pregunta al motor: el propio `getTplPath()` de Div, llamado a través de PHP con la ruta de la plantilla, el mismo directorio de trabajo que usa un render (la carpeta del proyecto) y, como historial de includes, la última plantilla que renderizaste. Solo se informa de lo que Div responde "no encontrado".

Así que los avisos de includes necesitan PHP y Div (consulta [[Instalación|Installation]]). Sin ellos no se informa de nada sobre los includes, en lugar de adivinar. Los includes construidos a partir de variables (`{% parts/{$name} %}`) solo se conocen al renderizar y no se verifican.

Las respuestas se vuelven a preguntar cuando cambian los includes de la plantilla, cuando vuelves a la plantilla, después de guardar y después de crear, renombrar o eliminar archivos en la [[Ventana de proyecto|Project Window]].

### Ir a la plantilla incluida

Pon el cursor sobre un include y pulsa **Ctrl+Enter**, o haz Ctrl+clic sobre él, o usa Buscar > Ir a la plantilla incluida. Se abre el archivo que Div incluiría. Si Div no lo encuentra, divide ofrece crearlo junto a la plantilla actual, que es el primer lugar donde busca Div.

Muchos terminales envían Ctrl+Enter como un salto de línea normal; divide también lo acepta como **Ctrl+J**, así que funciona de las dos formas.

## Primero guardar: una convención

Div puede recibir una plantilla como cadena, sin archivo. divide podría pasarle un buffer sin guardar, pero una plantilla sin archivo no tiene carpeta: Div no encontraría sus includes como lo hará en producción, y divide no sabría cuál es su archivo de datos (`page.tpl` → `page.json`). Así que divide sigue una convención sencilla: **las plantillas se guardan antes de que Div las vea.** Una plantilla sin título se verifica en todo lo demás, pero sus includes no se resuelven, y Renderizar e Ir al include te piden que la guardes primero (F2).

Una vez que una plantilla tiene archivo, sus ediciones sin guardar no son problema: renderizar y verificar siempre usan lo que hay en el editor.
