# Servidor MCP

divide tiene su propio servidor [Model Context Protocol](https://modelcontextprotocol.io). Permite que un agente de programación con IA, o cualquier cliente MCP, use lo que divide hace mientras desarrollas un generador: la [[configuración de Div|Div Setup]] del proyecto, las [[verificaciones del editor|Checking Templates]], un [[render|Rendering]] y la [[traza del render|Render Trace]], con el motor Div real y el mismo código que ejecuta el IDE.

Es el MCP del IDE, no el de un generador. Un generador que deba usarse desde agentes implementa su propio CLI, API HTTP o servidor MCP en su propio proyecto, y funciona sin divide.

Viene con divide: no hay nada más que instalar. Renderizar necesita PHP y Div, como en el IDE ([[Instalación|Installation]]).

## Iniciarlo en divide

**Opciones > Servidor MCP...** lo inicia, lo detiene y lo configura. Sirve la carpeta abierta en

```
http://127.0.0.1:8765/mcp
```

![Opciones > Servidor MCP, en marcha, tras las primeras llamadas de un agente](images/mcp-server.png)

- **Iniciar** (Intro) sirve la carpeta abierta; mientras está en marcha, el botón es **Reiniciar**. **Detener** lo termina. El diálogo sigue abierto: las primeras líneas dicen si está en marcha, su dirección, el proyecto, las peticiones atendidas (y las que están en curso) y los clientes que dijeron quiénes son. Cuando no puede iniciarse, dicen por qué: un puerto en el que escucha otro programa, un host que no es de esta máquina.
- **Host** y **Puerto**: `127.0.0.1` y `8765` por defecto. Aquí se elige otro puerto cuando ese está ocupado.
- **Iniciar junto con divide**: desactivado por defecto. Marcado, el servidor se inicia cada vez que divide se abre con una carpeta.
- **Exigir un token**: ver [Confianza y seguridad](#confianza-y-seguridad).
- **Copiar para el cliente** copia al portapapeles la configuración para un cliente MCP (abajo), con el token cuando se exige uno.

Tiene que haber una carpeta abierta: el servidor la sirve. Sigue al proyecto: cuando **Archivo > Abrir carpeta** abre otra, un servidor en marcha pasa a servir esa (con la misma dirección); **Archivo > Cerrar carpeta** lo detiene. Se detiene cuando divide termina. El host, el puerto y las dos opciones se recuerdan (`config.json`, la clave `mcp`).

## Conectar un cliente

La mayoría de los clientes aceptan una configuración como esta (**Copiar para el cliente** la da con tu dirección):

```json
{
  "mcpServers": {
    "divide": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

Con token, añade `"headers": {"Authorization": "Bearer <token>"}`. Algunos clientes llaman al transporte `streamable-http` o solo piden `url`; la dirección es la misma. El servidor no guarda sesiones: cuando lo reinicias desde divide, los clientes siguen sin volver a conectarse.

El servidor habla las dos generaciones del protocolo: **2026-07-28** (cada petición dice su versión; `server/discover`) y **2024-11-05 a 2025-11-25** (el saludo `initialize`), que es la que hablan hoy la mayoría de los clientes. Responde cada petición con una respuesta JSON (sin flujo de eventos).

### Sin la interfaz: stdio

`divide --mcp PROYECTO` sirve las mismas herramientas por stdio, para los clientes que inician sus servidores como procesos. El protocolo va por stdout y todo lo demás por stderr; termina cuando el cliente cierra su stdin.

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

Los argumentos se comprueban con el esquema de cada herramienta: un tipo equivocado o un argumento desconocido vuelve como error de la herramienta, que el agente lee. El servidor guarda las últimas cuatro trazas para paginarlas; un `trace_id` más antiguo pide volver a usar `div_trace`.

## Confianza y seguridad

- **Un render ejecuta el PHP del proyecto.** Div es PHP: el motor que nombra el proyecto, las funciones y los modificadores que permite su configuración. Es código de confianza que se ejecuta con tus permisos, no una caja de arena. Inicia el servidor solo en proyectos en los que confías, como cuando los abres en divide.
- **Tus decisiones de confianza siguen siendo tuyas.** Los ajustes `php` de un proyecto en los que no has confiado en **Opciones > Configuración de Div...** se quedan fuera: los renders van sin ellos, y `project_info` y cada render lo dicen (`untrusted_php`), junto con cómo confiar en ellos desde divide. El servidor nunca confía en ellos, nunca escribe `~/.div/trust.json` y nunca pregunta.
- **Solo esta máquina, por defecto.** El servidor escucha en `127.0.0.1`. Comprueba las cabeceras `Host` y `Origin`, así que una página web no puede alcanzarlo (ni siquiera con DNS rebinding), y nunca responde a la consulta CORS de un navegador.
- **El token.** En una dirección de red (`0.0.0.0`, una dirección de la red local) siempre se exige un token; **Exigir un token** lo pide también en `127.0.0.1`, lo que deja fuera a los demás usuarios de una máquina compartida. Los clientes lo envían como `Authorization: Bearer <token>`. Se guarda en `mcp-token`, junto al `config.json` de divide, legible solo por ti; divide nunca lo muestra ni lo anota: **Copiar para el cliente** lo pone en el portapapeles. El tráfico no va cifrado: para llegar al servidor desde otra máquina, usa un túnel SSH a `127.0.0.1` (`ssh -L 8765:127.0.0.1:8765 host`), o pon delante un proxy inverso con TLS.
- **Limitado al proyecto.** Plantillas, archivos de datos y archivos de dialecto deben estar dentro de la carpeta del proyecto, después de seguir los enlaces simbólicos: `../`, una ruta absoluta a otro sitio o un enlace que lleva afuera se rechazan. Div sigue resolviendo includes y dialectos como en producción, con las rutas de inclusión de la configuración.
- **No se escribe nada.** El servidor lee el proyecto; no guarda plantillas, datos ni ajustes. El texto que pasas como `source` o `data` se renderiza, no se guarda. (Lo que haga una función PHP tuya de confianza cuando una plantilla la llama depende de ella.)
- **Acotado.** PHP se detiene al agotarse el tiempo y cuando el cliente cancela una llamada (cierra la conexión; por stdio envía `notifications/cancelled`). Salidas, mensajes, páginas de traza y textos se cortan a los límites de arriba, y la respuesta dice cuándo se cortó algo. Se rechazan peticiones de más de 16 MB, plantillas y datos de más de 4 millones de caracteres y más de 32 conexiones a la vez; cuatro llamadas se ejecutan a la vez, las siguientes esperan.
- **Sin shell, sin archivos, sin red propia.** No hay herramienta para ejecutar comandos, listar o editar archivos ni usar git.

## Limitaciones

- Trabaja con los archivos del proyecto y con el texto que le pasas. No ve los editores abiertos de divide, sus cambios sin guardar, la plantilla activa ni su selección, y no edita nada.
- El servidor no conoce el archivo de datos que elegiste para una plantilla en **Ejecutar > Archivo de datos**: pasa `data_file`.
- Un proyecto por servidor: la carpeta abierta en divide (o la que se da a `divide --mcp`).
- Solo herramientas: ni recursos, ni prompts, ni notificaciones.
