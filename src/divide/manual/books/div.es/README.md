> [!WARNING]
> Esta documentación está actualmente en plena construcción.  
> El contenido puede estar incompleto, cambiar o reorganizarse a medida que evoluciona el motor Div.  
> Úsala con precaución y vuelve a consultarla con regularidad para ver las novedades.

# Visión general

Requisitos: PHP >= 8.0.

Div es un motor de plantillas y generador de código escrito en PHP. Está pensado para separar la presentación de los datos y del comportamiento, y para dar soporte a flujos de trabajo dirigidos por modelos y generativos. El motor puede adaptar su sintaxis mediante dialectos sin perder una representación interna canónica para el análisis y la transformación.

## Flujo de procesamiento

```mermaid
flowchart TD
    A["Entrada: plantilla (texto)"] --> B["Dialector: normaliza a Div canónico"]
    B --> C["Instancia de Div (src, items, config)"]
    C --> D["Pasada de análisis: detección de estructuras"]

    subgraph T["Transformadores (por fase)"]
      T0["(grupo)"]
      T1["Includes"]
      T2["Condiciones"]
      T3["Bucles / listas"]
      T4["Reemplazos / variables"]
      T5["Modificadores"]
      T6["Macros / fórmulas"]
      T7["Cápsulas / strip / ignorar / comentarios"]
      T0 --> T1
      T0 --> T2
      T0 --> T3
      T0 --> T4
      T0 --> T5
      T0 --> T6
      T0 --> T7
    end

    D --> T0
    T1 --> E["Texto transformado"]
    T2 --> E
    T3 --> E
    T4 --> E
    T5 --> E
    T6 --> E
    T7 --> E
    E --> F{"¿Cambió? (CRC)"}
    F -- Yes --> D
    F -- No --> G["Salida: texto final (HTML/código/etc.)"]
```

## Convergencia y recursión

```mermaid
flowchart LR
    A["Inicio de parse()"] --> B["crc_prev = crc32(src)"]
    B --> C["Aplicar la fase: detectar y transformar bloques"]
    C --> D["crc_now = crc32(src)"]
    D --> E{"crc_now != crc_prev?"}
    E -- "Sí" --> F["cycles = cycles + 1"]
    F --> G{"cycles > MAX?"}
    G -- "Sí" --> H["Abortar con error"]
    G -- "No" --> B
    E -- "No" --> I["Convergencia alcanzada: devolver src"]
```

## Dialectos

```mermaid
flowchart LR
    A["Entrada: plantilla (sintaxis del dialecto)"] --> C["Dialector: normaliza a Div canónico"]

    B1["Configuración del dialecto: tablas de correspondencia"] --> C
    B2["Delimitadores y palabras clave"] --> C
    B3["Etiquetas y marcas de bloque"] --> C
    B4["Modificadores y separadores"] --> C
    B5["Reglas de escape y manejo de colisiones"] --> C

    C --> D["Div canónico (texto)"]
    D --> E["Instancia de Div (src, items, config)"]
    E --> F["Pasada de análisis: detección de estructuras"]
    F --> G{"¿Cambió? (CRC)"}
    G -- "Sí" --> F
    G -- "No" --> H["Salida final (HTML/código/etc.)"]
```

## Ámbito de los bucles y subinstancias

```mermaid
sequenceDiagram
    participant E as Motor (div)
    participant T as Plantilla (bloque de lista)
    participant D as Datos (items[])
    Note over E,T: E detecta un bloque de lista [ $ items ]
    E->>T: Extrae la plantilla interna del bloque
    loop Por cada item de items
        E->>E: Crea una subinstancia de div (ámbito aislado)
        E->>E: items = item (ocultación/fusión)
        E->>E: parse() (multipasada local)
        E-->>E: Resultado parcial (fragmento)
    end
    E->>E: Concatena los fragmentos en orden
    E-->>T: Reemplaza el bloque por la concatenación
    E-->>E: Sigue el análisis global multipasada
```

## Operaciones básicas

- Compilar: combinar una plantilla con un modelo y guardar el resultado.
- Transformar: convertir un modelo en otro reutilizando la compilación.
- Componer: ensamblar varias salidas en un artefacto final.

## Instalación

```bash
composer require divengine/div
```

## Actualización

```bash
composer upgrade
```

## Mapa de la documentación

- [[01 Introducción|01 Introduction]]
- [[02 Características de las plantillas|02 Template Features]]
- [[03 Características de PHP|03 PHP Features]]
- [[04 Mecanismos|04 Mechanisms]]
- [[05 Apéndices|05 Appendixes]]

Consulta también las [notas de versión](https://github.com/divengine/div/blob/master/releases/README.md).

#templates
