<?php

// validate.identifiers: names PHP accepts where the templates put them, and no field twice.

declare(strict_types=1);

require_once dirname(__DIR__, 2) . '/lib/generator.php';

return function (array &$context): int {
    generator\stage($context, 'identifiers');
    $model = $context['dto'];
    $identifier = '/^[A-Za-z_][A-Za-z0-9_]*$/';
    $problems = [];
    foreach (explode('\\', is_string($model['namespace'] ?? null) ? $model['namespace'] : '') as $part) {
        if ($part !== '' && (!preg_match($identifier, $part) || in_array(strtolower($part), generator\RESERVED, true))) {
            $problems[] = "namespace: \"$part\" is not a PHP name";
        }
    }
    $class = is_string($model['class'] ?? null) ? $model['class'] : '';
    if ($class !== '' && (!preg_match('/^[A-Z][A-Za-z0-9]*$/', $class) || in_array(strtolower($class), generator\RESERVED, true))) {
        $problems[] = "class: \"$class\" must be a PHP class name in PascalCase";
    }
    $seen = [];
    foreach (is_array($model['fields'] ?? null) ? $model['fields'] : [] as $field) {
        $name = is_array($field) && is_string($field['name'] ?? null) ? $field['name'] : null;
        if ($name === null) {
            continue;
        }
        if (!preg_match('/^[a-z][A-Za-z0-9_]*$/', $name) || $name === 'this') {
            $problems[] = "field \"$name\": a property name starts with a lowercase letter";
        }
        if (isset($seen[$name])) {
            $problems[] = "field \"$name\" twice";
        }
        $seen[$name] = true;
    }
    array_push($context['problems'], ...$problems);
    return count($problems);
};
