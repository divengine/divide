<?php

/**
 * divide's Function test: one Runner Function called with a JSON context, in its own PHP process.
 *
 *   php functest.php REQUEST.json
 *
 * The request (written by divide, see divide/run/functest.py) names the Function (`name`, `module`),
 * the project's Composer autoload, Runner's source (when the autoload does not load it), the
 * function root and Module folders (`root`, `modules`), the context, and the file the result is
 * written to (`result`). Nothing else is read.
 *
 * - The Function is resolved by Runner's own importer, `runner::importer()`, with `_root_folder` and
 *   `_modules`: the same file a Flow's Step would load, nothing else is tried for a Module.
 * - It is called as Runner calls a condition or an activity: `$func($context)`, the context by
 *   reference, with `_importer` in it so it can import other Functions as in a Flow.
 * - The result goes to the result file, never to stdout or stderr: what the Function prints and
 *   PHP's own messages stay the user's. A fatal error or an exit() still writes a result (shutdown).
 *
 * This runs the real PHP code of the project: it is not a sandbox.
 */

declare(strict_types=1);

$requestFile = $argv[1] ?? '';
$request = is_file($requestFile) ? json_decode((string) file_get_contents($requestFile), true) : null;
if (!is_array($request) || !isset($request['result'], $request['name'])) {
    fwrite(STDERR, "divide functest: no request\n");
    exit(2);
}

$GLOBALS['__divide_functest'] = [
    'result' => (string) $request['result'],
    'written' => false,
    'phase' => 'bootstrap',
    'logs' => [],
    'before' => null,
    'context' => null,
    'resolved' => null,
    'started' => microtime(true),
];

/** A value as JSON can hold it: objects, closures and resources described, depth and size bounded. */
function __divide_functest_value(mixed $value, int $depth = 0): mixed
{
    if ($depth > 32) {
        return ['__divide' => 'depth', 'type' => get_debug_type($value)];
    }
    if (is_array($value)) {
        $out = [];
        $count = 0;
        foreach ($value as $key => $item) {
            if (++$count > 5000) {
                $out['__divide_truncated'] = count($value);
                break;
            }
            $out[$key] = __divide_functest_value($item, $depth + 1);
        }
        return $out;
    }
    if ($value instanceof Closure) {
        return ['__divide' => 'closure'];
    }
    if (is_object($value)) {
        $props = [];
        if ($value instanceof JsonSerializable) {
            try {
                return ['__divide' => 'object', 'class' => get_class($value),
                        'json' => __divide_functest_value($value->jsonSerialize(), $depth + 1)];
            } catch (Throwable) {
            }
        }
        foreach (get_object_vars($value) as $key => $item) {
            $props[$key] = __divide_functest_value($item, $depth + 1);
        }
        return ['__divide' => 'object', 'class' => get_class($value), 'properties' => $props];
    }
    if (is_resource($value)) {
        return ['__divide' => 'resource', 'type' => get_resource_type($value)];
    }
    if (is_float($value) && (is_nan($value) || is_infinite($value))) {
        return ['__divide' => 'float', 'value' => (string) $value];
    }
    if (is_string($value) && !mb_check_encoding($value, 'UTF-8')) {
        return ['__divide' => 'binary', 'base64' => base64_encode($value)];
    }
    return $value;
}

/** The context without what divide or Runner put in it for the call (helpers are not data). */
function __divide_functest_data(array $context): array
{
    unset($context['_importer'], $context['_logger']);
    return $context;
}

function __divide_functest_write(array $result): void
{
    $state = &$GLOBALS['__divide_functest'];
    if ($state['written']) {
        return;
    }
    $state['written'] = true;
    $result += [
        'phase' => $state['phase'],
        'resolved' => $state['resolved'],
        'logs' => $state['logs'],
        'before' => $state['before'],
        'seconds' => microtime(true) - $state['started'],
        'memory_peak' => memory_get_peak_usage(true),
    ];
    $json = json_encode($result, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PARTIAL_OUTPUT_ON_ERROR
        | JSON_PRESERVE_ZERO_FRACTION | JSON_INVALID_UTF8_SUBSTITUTE);
    if ($json === false) {
        $json = json_encode(['status' => 'protocol', 'message' => json_last_error_msg()]);
    }
    file_put_contents($state['result'] . '.tmp', $json);
    rename($state['result'] . '.tmp', $state['result']);
}

function __divide_functest_exception(Throwable $e): array
{
    $trace = [];
    foreach (array_slice($e->getTrace(), 0, 40) as $frame) {
        $trace[] = ['file' => $frame['file'] ?? null, 'line' => $frame['line'] ?? null,
                    'function' => ($frame['class'] ?? '') . ($frame['type'] ?? '') . ($frame['function'] ?? '')];
    }
    return ['class' => get_class($e), 'message' => $e->getMessage(), 'file' => $e->getFile(), 'line' => $e->getLine(),
            'trace' => $trace, 'previous' => $e->getPrevious() ? __divide_functest_exception($e->getPrevious()) : null];
}

register_shutdown_function(static function (): void {
    $state = $GLOBALS['__divide_functest'];
    if ($state['written']) {
        return;
    }
    $error = error_get_last();
    $fatal = $error !== null && in_array($error['type'], [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR, E_USER_ERROR], true);
    $context = $state['context'];
    __divide_functest_write([
        'status' => $fatal ? 'fatal' : 'exit',
        'error' => $fatal ? ['message' => $error['message'], 'file' => $error['file'], 'line' => $error['line']] : null,
        'after' => is_array($context) ? __divide_functest_value(__divide_functest_data($context)) : null,
    ]);
});

// ---------------------------------------------------------------- bootstrap
$autoload = (string) ($request['autoload'] ?? '');
if ($autoload !== '' && is_file($autoload)) {
    require_once $autoload;
}
if (!class_exists('divengine\\runner\\runner')) {
    $source = (string) ($request['runner'] ?? '');
    if ($source !== '' && is_file($source)) {
        require_once $source;
    }
}
if (!class_exists('divengine\\runner\\runner')) {
    __divide_functest_write(['status' => 'setup', 'message' => 'Runner is not installed: composer require divengine/runner']);
    exit(0);
}

// ---------------------------------------------------------------- resolve
$GLOBALS['__divide_functest']['phase'] = 'resolve';
$resolving = [];
if (isset($request['root']) && is_string($request['root']) && $request['root'] !== '') {
    $resolving['_root_folder'] = $request['root'];
}
if (isset($request['modules']) && is_array($request['modules']) && $request['modules'] !== []) {
    $resolving['_modules'] = $request['modules'];
}
$logger = static function (string $level, string $message, array $context = []): void {
    $GLOBALS['__divide_functest']['logs'][] = ['level' => $level, 'message' => $message];
};
$module = isset($request['module']) && is_string($request['module']) && $request['module'] !== '' ? $request['module'] : null;
$name = (string) $request['name'];
$func = \divengine\runner\runner::importer($name, $module, $resolving, $logger);
if ($func === null) {
    __divide_functest_write(['status' => 'missing', 'message' => "Runner's importer found no callable for "
        . ($module !== null ? "{$module}:{$name}" : $name)]);
    exit(0);
}
try {
    $reflection = is_array($func) ? new ReflectionMethod($func[0], $func[1])
        : (is_string($func) && str_contains($func, '::') ? new ReflectionMethod($func)
        : (is_object($func) && !($func instanceof Closure) ? new ReflectionMethod($func, '__invoke') : new ReflectionFunction($func)));
    $GLOBALS['__divide_functest']['resolved'] = [
        'file' => $reflection->getFileName() ?: null,
        'line' => $reflection->getStartLine() ?: null,
        'callable' => is_string($func) ? $func : (is_object($func) ? get_class($func) : 'callable'),
        'parameters' => $reflection->getNumberOfParameters(),
        'by_reference' => $reflection->getNumberOfParameters() > 0 && $reflection->getParameters()[0]->isPassedByReference(),
    ];
} catch (Throwable) {
}

// ---------------------------------------------------------------- call
$context = is_array($request['context'] ?? null) ? $request['context'] : [];
$GLOBALS['__divide_functest']['before'] = __divide_functest_value($context);
$context['_importer'] = static function (string $name, ?string $module = null) use ($resolving, $logger): ?callable {
    return \divengine\runner\runner::importer($name, $module, $resolving, $logger);
};
$GLOBALS['__divide_functest']['context'] = &$context;
$GLOBALS['__divide_functest']['phase'] = 'call';
try {
    $returned = $func($context);  // divide: the call (a debug session steps into it from here)
} catch (Throwable $e) {
    __divide_functest_write(['status' => 'exception', 'exception' => __divide_functest_exception($e),
                             'after' => __divide_functest_value(__divide_functest_data($context))]);
    exit(0);
}
$GLOBALS['__divide_functest']['phase'] = 'done';
__divide_functest_write([
    'status' => 'returned',
    'return' => __divide_functest_value($returned),
    'return_type' => get_debug_type($returned),
    'after' => __divide_functest_value(__divide_functest_data($context)),
]);
exit(0);
