<?php

// main.current: true when the manifest of the last generation has the same inputs and
// every output it lists is still there, unchanged. Then main jumps over generation.

declare(strict_types=1);

require_once dirname(__DIR__) . '/lib/generator.php';

return function (array &$context): bool {
    $manifest = generator\output($context) . '/manifest.json';
    if (!is_file($manifest)) {
        return false;
    }
    $last = json_decode((string) file_get_contents($manifest), true);
    if (!is_array($last) || ($last['inputs'] ?? null) !== $context['inputs']) {
        return false;
    }
    foreach (generator\outputs($context['dto']) as $relative) {
        $path = generator\output($context) . '/' . $relative;
        if (!is_file($path) || hash_file('sha256', $path) !== ($last['outputs'][$relative] ?? null)) {
            return false;
        }
    }
    return true;
};
