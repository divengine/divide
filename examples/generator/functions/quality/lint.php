<?php

// quality.lint: php -l on the generated class, with the PHP that runs the Flow. A syntax error ends the run.

declare(strict_types=1);

require_once dirname(__DIR__, 2) . '/lib/generator.php';

return function (array &$context): string {
    generator\stage($context, 'lint');
    $path = generator\output($context) . '/' . generator\outputs($context['dto'])['class'];
    $process = proc_open([PHP_BINARY, '-n', '-l', $path], [1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
    if (!is_resource($process)) {
        throw new RuntimeException('Cannot run php -l');
    }
    $said = trim(stream_get_contents($pipes[1]) . stream_get_contents($pipes[2]));
    fclose($pipes[1]);
    fclose($pipes[2]);
    if (proc_close($process) !== 0) {
        throw new RuntimeException("The generated class does not parse: $said");
    }
    return 'ok';
};
