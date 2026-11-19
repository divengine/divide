# Servidor MCP

`divide --mcp PROYECTO` sirve el servidor [Model Context Protocol](https://modelcontextprotocol.io) propio de divide para un proyecto, por stdio y sin la interfaz. Permite que un agente de programación con IA, o cualquier cliente MCP, use lo que divide hace mientras desarrollas un generador: la [[configuración de Div|Div Setup]] del proyecto, las [[verificaciones del editor|Checking Templates]], un [[render|Rendering]] y la [[traza del render|Render Trace]], con el motor Div real y el mismo código que ejecuta el IDE.

Es el MCP del IDE, no el de un generador. Un generador que deba usarse desde agentes implementa su propio CLI, API HTTP o servidor MCP en su propio proyecto, y funciona sin divide.

## Instalación

El servidor MCP necesita el SDK oficial de MCP para Python, una dependencia opcional (el extra `mcp`). Los paquetes listos para usar (Homebrew, Scoop, los instaladores) todavía no lo incluyen: instala divide desde el código fuente con el extra.

```bash
git clone https://github.com/divengine/divide.git
cd divide
tools/install.sh                    # el comando divide, como en Instalación
.venv/bin/pip install -e ".[mcp]"   # y el SDK de MCP en su .venv
```

O con pipx:

```bash
pipx install "divide[mcp] @ git+https://github.com/divengine/divide.git"
```

Sin el SDK, `divide --mcp` lo dice y termina. Renderizar necesita PHP y Div, como en el IDE ([[Instalación|Installation]]).

## Iniciarlo

```bash
divide --mcp /ruta/al/proyecto
```

La carpeta es el proyecto: todo archivo que el servidor toma debe estar dentro de ella. El protocolo va por stdout; lo que el servidor tenga que decir va por stderr. Termina cuando el cliente cierra su stdin. Lo inicia tu cliente MCP; la mayoría acepta una configuración como esta:

```json
{
  "mcpServers": {
    "divide": {
      "command": "divide",
      "args": ["--mcp", "/ruta/al/proyecto"],
      "env": {"DIVIDE_LANGUAGE": "en"}
    }
  }
}
```

`DIVIDE_LANGUAGE` es opcional. Los textos propios del servidor están en inglés; los hallazgos de las verificaciones de divide y de la configuración de Div están en el idioma de divide, como en el IDE, y `en` lo da todo en inglés. `DIVIDE_DIV_PHP` elige el motor, como en todo divide.

## Herramientas

Las rutas son relativas al proyecto. Cuando una herramienta acepta `source`, ese texto se verifica o renderiza en lugar del archivo guardado (el archivo no tiene que existir todavía), y los includes y el archivo de datos se siguen buscando desde la ruta de la plantilla, como hace Div.

| Herramienta | Qué hace | Parámetros |
|---|---|---|
| `project_info` | La carpeta del proyecto, la versión de PHP, el motor Div y dónde se encontró (`DIVIDE_DIV_PHP`, la configuración, Opciones > Motor Div, `vendor/`), la configuración de Div en vigor y sus archivos, el dialecto del proyecto, las extensiones de plantilla y de datos, lo que divide dejó fuera de la configuración (archivo, línea, columna, por qué), los ajustes PHP del proyecto que esperan tu confianza y el veredicto de Div sobre la configuración. De la petición simulada y de las globales da solo los nombres. | ninguno |
| `div_check` | Las verificaciones del editor (Alt+F8): bloques sin cerrar, etiquetas que Div dejaría como texto, JSON roto en `{= =}`, un `@_DIALECT` roto, includes que Div no encuentra. Cada hallazgo con su gravedad, mensaje, posiciones, línea y columna. El dialecto y los includes son respuestas de Div; sin PHP o sin Div las verificaciones se hacen igual, con la suposición de divide sobre el dialecto, y los includes no se comprueban (la respuesta lo dice). | `template`, `source` |
| `div_render` | Renderiza como Ctrl+F9: la salida, los mensajes de Div y de PHP (con la línea del archivo de configuración cuando tratan de la configuración), `status` (`ok`, `warnings`, `fatal`), la versión de Div y el tiempo. | `template`, `data_file` (por defecto: el de la plantilla, por la convención de Div), `source`, `data` (texto JSON de Div), `use_data_file`, `max_output_chars` (por defecto 20000, hasta 200000), `timeout_seconds` (por defecto 20, hasta 120) |
| `div_trace` | Renderiza guardando cada mutación que Div hizo hasta el punto fijo, como la traza del render: un resumen (mutaciones, cambios, subanálisis, el nivel de análisis más profundo, los ciclos de cada punto fijo), la salida y la primera página de mutaciones. Cada cambio dice qué se quitó y qué se insertó (dónde, y hasta 400 caracteres), los pasos de Div detrás, su nivel de análisis, su ejecución (1 la plantilla, 2... sus subanálisis) y su ciclo. Devuelve un `trace_id`. | como `div_render`, más `limit` (la primera página, por defecto 50, hasta 200); `timeout_seconds` por defecto 60 |
| `div_trace_page` | Otra página de una traza, opcionalmente de un solo tipo (`start`, `change`, `end`) o de una sola ejecución. | `trace_id`, `offset`, `limit`, `kind`, `run` |
| `div_trace_mutation` | Una mutación completa: el texto de la plantilla antes y después, y los pasos de Div. | `trace_id`, `index`, `max_chars` |
| `div_check_dialect` | El veredicto de Div sobre un dialecto, como lo pide el [[Dialector]]: un archivo de dialecto del proyecto (decodificado por Div), sustituciones `DIV_TAG_*` o el dialecto del proyecto. | `dialect_file` o `tags` |

El servidor guarda las últimas cuatro trazas para paginarlas; un `trace_id` más antiguo pide volver a usar `div_trace`.

## Confianza y seguridad

- **Un render ejecuta el PHP del proyecto.** Div es PHP: el motor que nombra el proyecto, las funciones y los modificadores que permite su configuración. Es código de confianza que se ejecuta con tus permisos, no una caja de arena. Inicia el servidor solo en proyectos en los que confías, como cuando los abres en divide.
- **Tus decisiones de confianza siguen siendo tuyas.** Los ajustes `php` de un proyecto en los que no has confiado en **Opciones > Configuración de Div...** se quedan fuera: los renders van sin ellos, y `project_info` y cada render lo dicen (`untrusted_php`), junto con cómo confiar en ellos desde divide. El servidor nunca confía en ellos, nunca escribe `~/.div/trust.json` y nunca pregunta.
- **Limitado al proyecto.** Plantillas, archivos de datos y archivos de dialecto deben estar dentro de la carpeta del proyecto, después de seguir los enlaces simbólicos: `../`, una ruta absoluta a otro sitio o un enlace que lleva afuera se rechazan. Div sigue resolviendo includes y dialectos como en producción, con las rutas de inclusión de la configuración.
- **No se escribe nada.** El servidor lee el proyecto; no guarda plantillas, datos ni ajustes. El texto que pasas como `source` o `data` se renderiza, no se guarda. (Lo que haga una función PHP tuya de confianza cuando una plantilla la llama depende de ella.)
- **Acotado.** PHP se detiene al agotarse el tiempo y cuando el cliente cancela una llamada; salidas, mensajes, páginas de traza y textos se cortan a los límites de arriba, y la respuesta dice cuándo se cortó algo. Se rechazan plantillas y datos de más de 4 millones de caracteres.
- **Sin shell, sin archivos, sin red.** No hay herramienta para ejecutar comandos, listar o editar archivos ni usar git, y el servidor no escucha en ningún puerto: solo stdio.

## Limitaciones

- Trabaja con los archivos del proyecto y con el texto que le pasas. No ve los editores abiertos de divide, sus cambios sin guardar, la plantilla activa ni su selección, y no edita nada.
- El servidor no conoce el archivo de datos que elegiste para una plantilla en **Ejecutar > Archivo de datos**: pasa `data_file`.
- Un proyecto por servidor. Inicia uno por proyecto.
- Los paquetes listos para usar todavía no incluyen el SDK de MCP (ver Instalación).
