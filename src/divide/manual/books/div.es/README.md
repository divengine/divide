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
    A["Input: Template (text)"] --> B["Dialector: Normalize to canonical Div"]
    B --> C["Div instance (src, items, config)"]
    C --> D["Parsing pass: Structure detection"]

    subgraph T["Transformers (per phase)"]
      T0["(group)"]
      T1["Includes"]
      T2["Conditions"]
      T3["Loops / Lists"]
      T4["Replacements / Variables"]
      T5["Modifiers"]
      T6["Macros / Formulas"]
      T7["Capsules / Strip / Ignore / Comment"]
      T0 --> T1
      T0 --> T2
      T0 --> T3
      T0 --> T4
      T0 --> T5
      T0 --> T6
      T0 --> T7
    end

    D --> T0
    T1 --> E["Transformed text"]
    T2 --> E
    T3 --> E
    T4 --> E
    T5 --> E
    T6 --> E
    T7 --> E
    E --> F{"Did it change? (CRC)"}
    F -- Yes --> D
    F -- No --> G["Output: Final text (HTML/code/etc.)"]
```

## Convergencia y recursión

```mermaid
flowchart LR
    A["Init parse()"] --> B["crc_prev = crc32(src)"]
    B --> C["Apply phase: detect and transform blocks"]
    C --> D["crc_now = crc32(src)"]
    D --> E{"crc_now != crc_prev?"}
    E -- "Yes" --> F["cycles = cycles + 1"]
    F --> G{"cycles > MAX?"}
    G -- "Yes" --> H["Abort with error"]
    G -- "No" --> B
    E -- "No" --> I["Convergence reached: return src"]
```

## Dialectos

```mermaid
flowchart LR
    A["Input: Template (Dialect syntax)"] --> C["Dialector: Normalize to canonical Div"]

    B1["Dialect config: mapping tables"] --> C
    B2["Delimiters & keywords"] --> C
    B3["Tags & block markers"] --> C
    B4["Modifiers & separators"] --> C
    B5["Escape rules & collision handling"] --> C

    C --> D["Canonical Div (text)"]
    D --> E["Div instance (src, items, config)"]
    E --> F["Parsing pass: structure detection"]
    F --> G{"Did it change? (CRC)"}
    G -- "Yes" --> F
    G -- "No" --> H["Final output (HTML/code/etc.)"]
```

## Ámbito de los bucles y subinstancias

```mermaid
sequenceDiagram
    participant E as Engine (div)
    participant T as Template (list block)
    participant D as Data (items[])
    Note over E,T: E detects a list block [ $ items ]
    E->>T: Extract inner block template
    loop For each item in items
        E->>E: Create sub-instance div (isolated scope)
        E->>E: Set items = item (shadowing/merge)
        E->>E: parse() (local multipass)
        E-->>E: Partial result (fragment)
    end
    E->>E: Concatenate fragments in order
    E-->>T: Replace block with concatenation
    E-->>E: Continue global multipass parse
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
