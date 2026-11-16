# 3. Características de PHP

Esta sección enumera la API pública de la clase div.

## 3.1 Métodos estáticos

**div::addCustomModifier(**string** $prefix, **string** $function)**

Registra un modificador de variable personalizado. La función del modificador debe aceptar un único parámetro.

**div::asThis(**mixed** $mixed)**

Devuelve un valor con formato HTML para depuración.

**div::atLeastOneString(**string** $haystack, **array** $needles)**

Devuelve true si al menos una de las agujas aparece en el pajar.

**div::delDefault(**mixed** $search)**

Elimina un reemplazo por defecto.

**div::delDefaultByVar(**string** $var, **mixed** $search)**

Elimina un reemplazo por defecto de una variable concreta.

**div::delGlobal(**string** $var)**

Elimina una variable global.

**div::disableSystemVar(**string** $var)**

Desactiva una variable del sistema para mejorar el rendimiento.

**div::enableSystemVar(**string** $var)**

Activa una variable del sistema.

**div::error(**string** $errmsg, **string** $level = 'WARNING')**

Emite un error y detiene la ejecución.

**div::fileExists(**string** $filename)**

Comprobación segura de la existencia de un archivo.

**div::getLastKeyOfArray(**array** $arr)**

Devuelve la última clave de un array.

**div::getCountOfParagraphs(**string** $text)**

Cuenta los párrafos de una cadena.

**div::getCountOfSentences(**string** $text)**

Cuenta las oraciones de una cadena.

**div::getCountOfWords(**string** $text)**

Cuenta las palabras de una cadena.

**div::getDefault(**mixed** $value)**

Devuelve el reemplazo por defecto de un valor.

**div::getDefaultByVar(**string** $var, **mixed** $value)**

Devuelve el reemplazo por defecto de un valor en el ámbito de una variable.

**div::getSystemData()**

Devuelve los datos del sistema cargados.

**div::getVersion()**

Devuelve la cadena de la versión actual del motor.

**div::getVarsFromCode(**string** $code)**

Devuelve la lista de variables referenciadas en un código PHP.

**div::haveVarsThisCode(**string** $code)**

Devuelve true si un código PHP referencia alguna variable.

**div::htmlToText(**string** $html, **integer** $width = 50)**

Convierte HTML en texto plano.

**div::isArrayOfArray(**array** $arr)**

Devuelve true si el array contiene arrays.

**div::isArrayOfObjects(**array** $arr)**

Devuelve true si el array contiene objetos.

**div::isCli()**

Devuelve true si el script se ejecuta en CLI.

**div::isNumericList(**array** $arr)**

Devuelve true si el array es numérico.

**div::isValidExpression(**string** $code)**

Valida una expresión PHP.

**div::isDir(**string** $dirname)**

`is_dir` seguro.

**div::isString(**mixed** $value)**

`is_string` seguro.

**div::jsonDecode(**string** $str)**

Decodifica JSON.

**div::jsonEncode(**mixed** $data)**

Codifica JSON.

**div::log(**string** $msg, **string** $level = ' ')**

Escribe un mensaje en el log.

**div::logOn(**string** $logfile)**

Activa el log de depuración en un archivo.

**div::mixedBool(**mixed** $value)**

Convierte un valor a booleano según las reglas de Div.

**div::setAllowedFunction(**string** $funcname)**

Permite una función PHP en fórmulas o macros.

**div::setDefault(**mixed** $search, **mixed** $replace)**

Añade o actualiza un reemplazo por defecto.

**div::setDefaultByVar(**string** $var, **mixed** $search, **mixed** $replace, **bool** $update = true)**

Añade o actualiza un reemplazo por defecto de una variable concreta.

**div::unsetAllowedFunction(**string** $funcname)**

Retira una función permitida anteriormente.

**div::utf162utf8(**string** $utf16)**

Convierte UTF-16 a UTF-8.

**div::varExists(**string** $var, **mixed** &$items = null)**

Devuelve true si una variable existe en los items (de forma recursiva).

## 3.2 Métodos de instancia

**div->addLiteral(**string** $var)**

Marca una o varias variables de la plantilla como literales (no se siguen analizando). Acepta una lista separada por espacios o comas.

**div->getLiterals()**

Devuelve el mapa actual de variables literales de esta instancia.
