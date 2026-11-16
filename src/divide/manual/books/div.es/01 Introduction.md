# 1. Introducción

Div es un motor de plantillas que se ejecuta en PHP.

En esencia, Div toma una plantilla y un modelo de datos y produce texto:

```php
echo new div($template, $data);
```

Ese es el contrato fundamental. La salida siempre es texto.

Div también se usa como generador de código y como herramienta de transformación de datos, porque las plantillas no se limitan a HTML. Una plantilla puede generar código fuente, archivos de configuración, datos estructurados o incluso otras plantillas. Lo que Div genera puede reutilizarse como entrada de ejecuciones posteriores del motor.

Div es la piedra angular de Divengine Software Solutions y se desarrolla de forma continua desde 2011.

El lenguaje de plantillas está diseñado para ser compacto (sintaxis mínima para las operaciones comunes), flexible (los dialectos permiten sintaxis alternativas) y descriptivo (las plantillas se leen como documentos que se explican solos). Div asume una clara división de responsabilidades:

- El modelo especifica qué datos y reglas están disponibles.
- La plantilla especifica la estructura de salida esperada.
- El motor proporciona el mecanismo de ejecución.

Las capacidades abarcan tanto la escritura de plantillas como la integración con sistemas:

- Reemplazo de variables, formato, modificadores, operaciones con subcadenas y acceso a propiedades de objetos dentro del modelo proporcionado.
- Listas, iteraciones, bloques condicionales y otras construcciones repetitivas o de bifurcación.
- Includes, herencia, ubicaciones y procesamiento recursivo hasta la convergencia.
- Fórmulas, macros, funciones de agregación y limpieza de la salida (incluida la conversión de HTML a texto).
- Configuración de valores por defecto, globales, funciones permitidas y variables ignoradas.
- Sub-parsers personalizados, hooks, registro (logging) y uso de una instancia de div como cadena.

Aplicado de forma consistente, este enfoque reduce el trabajo repetitivo, permite reutilizar modelos, admite salidas para múltiples destinos y mejora la colaboración entre las partes interesadas.
