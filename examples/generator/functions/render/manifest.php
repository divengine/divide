<?php

// generate.manifest: the inputs' hash and each output's, which main.current compares on the next run.

declare(strict_types=1);

require_once dirname(__DIR__, 2) . '/lib/generator.php';

return function (array &$context): string {
    generator\stage($context, 'manifest');
    $outputs = [];
    foreach (generator\outputs($context['dto']) as $relative) {
        $outputs[$relative] = hash_file('sha256', generator\output($context) . '/' . $relative);
    }
    generator\write($context, 'manifest.json', generator\json(['inputs' => $context['inputs'], 'outputs' => $outputs]));
    return 'manifest.json';
};
