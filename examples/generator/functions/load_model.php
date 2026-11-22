<?php

// main.load: the model named by the context, and the hash of everything generation depends on.

declare(strict_types=1);

require_once dirname(__DIR__) . '/lib/generator.php';

return function (array &$context): string {
    $context['trail'] = [];
    $context['problems'] = [];
    generator\stage($context, 'load');
    $file = (string) ($context['model'] ?? '');
    $model = json_decode(generator\read($file), true, 64, JSON_THROW_ON_ERROR);
    $context['dto'] = is_array($model) ? $model : [];
    $context['inputs'] = generator\inputs_hash($context);
    return $file;
};
