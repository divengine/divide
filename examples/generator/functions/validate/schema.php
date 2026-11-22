<?php

// validate.schema: the model's shape (namespace, class, fields with a name and a type). Each problem is
// added to $context['problems']; validate.reject stops the run when there is any.

declare(strict_types=1);

require_once dirname(__DIR__, 2) . '/lib/generator.php';

return function (array &$context): int {
    generator\stage($context, 'schema');
    $model = $context['dto'];
    $problems = [];
    foreach (['namespace', 'class'] as $key) {
        if (!is_string($model[$key] ?? null) || $model[$key] === '') {
            $problems[] = "\"$key\" must be a non-empty string";
        }
    }
    if (isset($model['description']) && !is_string($model['description'])) {
        $problems[] = '"description" must be a string';
    }
    if (!is_array($model['fields'] ?? null) || !array_is_list($model['fields']) || $model['fields'] === []) {
        $problems[] = '"fields" must be a list with at least one field';
    } else {
        foreach ($model['fields'] as $i => $field) {
            if (!is_array($field) || !is_string($field['name'] ?? null)) {
                $problems[] = "fields[$i] needs a \"name\"";
                continue;
            }
            if (!in_array($field['type'] ?? null, generator\TYPES, true)) {
                $problems[] = "fields[$i] ({$field['name']}): \"type\" must be one of " . implode(', ', generator\TYPES);
            }
            if (isset($field['nullable']) && !is_bool($field['nullable'])) {
                $problems[] = "fields[$i] ({$field['name']}): \"nullable\" must be true or false";
            }
            if (isset($field['description']) && !is_string($field['description'])) {
                $problems[] = "fields[$i] ({$field['name']}): \"description\" must be a string";
            }
            foreach (array_diff(array_keys($field), ['name', 'type', 'nullable', 'description']) as $key) {
                $problems[] = "fields[$i] ({$field['name']}): unknown key \"$key\"";
            }
        }
    }
    array_push($context['problems'], ...$problems);
    return count($problems);
};
