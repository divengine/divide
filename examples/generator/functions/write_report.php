<?php

// main.report: what this run did, in build/report.json (no dates or times: the same run, the same report).

declare(strict_types=1);

require_once dirname(__DIR__) . '/lib/generator.php';

return function (array &$context): string {
    generator\stage($context, 'report');
    $outputs = [];
    foreach (generator\outputs($context['dto']) as $relative) {
        $outputs[$relative] = hash_file('sha256', generator\output($context) . '/' . $relative);
    }
    $regenerated = (bool) ($context['regenerated'] ?? false);
    generator\write($context, 'report.json', generator\json([
        'model' => $context['model'],
        'class' => $context['dto']['namespace'] . '\\' . $context['dto']['class'],
        'regenerated' => $regenerated,
        'stages' => $context['trail'],
        'lint' => $context['lint'],
        'checks' => $context['verify'],
        'outputs' => $outputs,
    ]));
    return sprintf('%s: %s, %d files, %d checks passed', $context['dto']['class'],
        $regenerated ? 'generated' : 'up to date, generation skipped', count($outputs), $context['verify']);
};
