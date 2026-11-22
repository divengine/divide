<?php

// quality.verify: the outputs say what the model says. Both files are what the templates give today (nothing
// edited them by hand, and Div renders the same twice), and the class, loaded, has the model's namespace,
// class and fields with their types, and gives back what it is built from. Returns the number of checks.

declare(strict_types=1);

require_once dirname(__DIR__, 2) . '/lib/generator.php';

return function (array &$context): int {
    generator\stage($context, 'verify');
    $model = generator\template_data($context);
    $outputs = generator\outputs($model);
    $checks = 0;
    $fail = static function (string $what): never {
        throw new RuntimeException("Output check failed: $what");
    };
    foreach (['class' => 'dto.tpl', 'readme' => 'readme.tpl'] as $kind => $template) {
        $file = (string) file_get_contents(generator\output($context) . '/' . $outputs[$kind]);
        if ($file !== generator\render($template, $context)) {
            $fail("{$outputs[$kind]} is not what templates/$template renders from the model");
        }
        $checks++;
    }
    require_once generator\output($context) . '/' . $outputs['class'];
    $name = $model['namespace'] . '\\' . $model['class'];
    class_exists($name, false) || $fail("no class $name");
    $checks++;
    $parameters = (new ReflectionClass($name))->getConstructor()?->getParameters() ?? [];
    if (array_map(static fn ($p) => $p->getName(), $parameters) !== array_column($model['fields'], 'name')) {
        $fail('the constructor\'s parameters are not the model\'s fields, in order');
    }
    $checks++;
    $sample = [];
    foreach ($model['fields'] as $i => $field) {
        $type = $parameters[$i]->getType();
        if (!$type instanceof ReflectionNamedType || $type->getName() !== $field['type'] || $type->allowsNull() !== $field['nullable']) {
            $fail("{$field['name']} is not " . ($field['nullable'] ? '?' : '') . $field['type']);
        }
        $checks++;
        $sample[$field['name']] = $field['nullable'] ? null : ['string' => 'text', 'int' => 7, 'float' => 0.5, 'bool' => true][$field['type']];
    }
    $name::fromArray($sample)->toArray() === $sample || $fail("$name::fromArray()->toArray() does not give back its data");
    $checks++;
    foreach ($model['fields'] as $field) {
        str_contains((string) file_get_contents(generator\output($context) . '/' . $outputs['readme']), "| `{$field['name']}` |")
            || $fail("README.md does not list {$field['name']}");
    }
    $checks++;
    return $checks;
};
