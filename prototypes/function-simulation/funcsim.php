<?php

/**
 * Proof of concept for divide #15: one Runner Function called with a JSON context and
 * dependency doubles, in its own PHP process.
 *
 *   php funcsim.php REQUEST.json
 *
 * The request (written by funcsim.py) holds the scenario (docs/function-simulation.md), the Function's
 * resolved file and a nonce: the result is printed on stdout after it. Unlike divide's Test Function (src/divide/run/functest.php):
 *
 * - The project's Composer autoload is NOT loaded unless the scenario opts in (`"autoload": true`).
 *   An autoloader that fails loudly is registered instead: a class the Function needs and nobody
 *   doubled is an error, not a silent real dependency.
 * - Runner is not loaded at all. `$context['_importer']` is a double: every name it is asked for
 *   must be in `doubles.importer`, or the import throws. No other Function file is required.
 * - Context services named in `doubles.services` are strict objects: every method called must be
 *   doubled, or the call throws.
 * - The Function's file is required directly, after its sha256 is checked against the scenario.
 *
 * What this does NOT do: intercept PHP's own functions (file_put_contents, PDO, curl, ...). The
 * driver can add `disable_functions` / `open_basedir` as a tripwire, which is still not a sandbox.
 */

declare(strict_types=1);

final class DivideMissingDouble extends RuntimeException
{
}

$requestFile = $argv[1] ?? '';
$request = is_file($requestFile) ? json_decode((string) file_get_contents($requestFile), true) : null;
if (!is_array($request) || !isset($request['nonce'], $request['file'], $request['scenario'])) {
    fprintf(STDERR, "divide funcsim: no request\n");  // fprintf: the tripwire disables fwrite
    exit(2);
}

$GLOBALS['__divide_funcsim'] = [
    'nonce' => (string) $request['nonce'],
    'written' => false,
    'phase' => 'bootstrap',
    'calls' => [],      // doubles answered, in order
    'counts' => [],     // calls per double (sequences)
    'logs' => [],
    'context' => null,
    'stdout' => '',
    'stdout_limit' => (int) ($request['scenario']['limits']['stdout'] ?? 65536),
    'stdout_cut' => 0,
    'started' => microtime(true),
];

/** A value as JSON can hold it, bounded (the same rules as functest.php). */
function __divide_funcsim_value(mixed $value, int $depth = 0): mixed
{
    if ($depth > 16) {
        return ['$type' => 'depth', 'class' => get_debug_type($value)];
    }
    if (is_array($value)) {
        $out = [];
        $count = 0;
        foreach ($value as $key => $item) {
            if (++$count > 1000) {
                $out['$truncated'] = count($value);
                break;
            }
            $out[$key] = __divide_funcsim_value($item, $depth + 1);
        }
        return $out;
    }
    if ($value instanceof Closure) {
        return ['$type' => 'closure'];
    }
    if ($value instanceof DivideDouble) {
        return ['$type' => 'double', 'name' => $value->__divideName];
    }
    if (is_object($value)) {
        $props = [];
        foreach (get_object_vars($value) as $key => $item) {
            $props[$key] = __divide_funcsim_value($item, $depth + 1);
        }
        return ['$type' => 'object', 'class' => get_class($value), 'properties' => $props];
    }
    if (is_resource($value)) {
        return ['$type' => 'resource', 'resource' => get_resource_type($value)];
    }
    if (is_float($value) && (is_nan($value) || is_infinite($value))) {
        return ['$type' => 'float', 'value' => (string) $value];
    }
    if (is_string($value)) {
        if (!mb_check_encoding($value, 'UTF-8')) {
            return ['$type' => 'binary', 'bytes' => strlen($value)];
        }
        if (strlen($value) > 4096) {
            return ['$type' => 'string', 'head' => mb_strcut($value, 0, 4096), 'bytes' => strlen($value)];
        }
    }
    return $value;
}

/**
 * The locals of a frame as JSON, for the line tracer: `eval` of
 * `__divide_funcsim_locals(get_defined_vars())` in the Function's frame over DBGp.
 */
function __divide_funcsim_locals(array $vars): string
{
    // get_defined_vars() keeps references: a by-reference $context is the caller's own array.
    // Never assign into $vars, or observing the Function would change it. Build a new array.
    $out = [];
    foreach ($vars as $name => $value) {
        if ($name === 'GLOBALS') {
            continue;
        }
        $out[$name] = $name === 'context' && is_array($value) ? __divide_funcsim_data($value) : $value;
    }
    return (string) json_encode(__divide_funcsim_value($out), JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
        | JSON_PARTIAL_OUTPUT_ON_ERROR | JSON_PRESERVE_ZERO_FRACTION | JSON_INVALID_UTF8_SUBSTITUTE);
}

/** The context without what the harness put in it for the call: the helpers and the service doubles. */
function __divide_funcsim_data(array $context): array
{
    unset($context['_importer'], $context['_logger']);
    foreach ($context as $key => $value) {
        if ($value instanceof DivideDouble) {
            unset($context[$key]);
        }
    }
    return $context;
}

function __divide_funcsim_exception(Throwable $e): array
{
    return ['class' => get_class($e), 'message' => $e->getMessage(), 'file' => $e->getFile(), 'line' => $e->getLine(),
            'missing_double' => $e instanceof DivideMissingDouble];
}

function __divide_funcsim_write(array $result): void
{
    $state = &$GLOBALS['__divide_funcsim'];
    if ($state['written']) {
        return;
    }
    $state['written'] = true;
    while (ob_get_level() > 0) {
        ob_end_flush();
    }
    $result += [
        'phase' => $state['phase'],
        'calls' => $state['calls'],
        'logs' => $state['logs'],
        'stdout' => $state['stdout'],
        'stdout_cut' => $state['stdout_cut'],
        'seconds' => microtime(true) - $state['started'],
        'memory_peak' => memory_get_peak_usage(true),
    ];
    $json = json_encode($result, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PARTIAL_OUTPUT_ON_ERROR
        | JSON_PRESERVE_ZERO_FRACTION | JSON_INVALID_UTF8_SUBSTITUTE);
    // On the process's own stdout, after a marker only the driver knows: no file is written, so the
    // harness still works when --tripwire disables file_put_contents, fwrite and rename. What the
    // Function printed went to the output buffer above, never here.
    echo "\n", $state['nonce'], "\n", $json === false ? '{"status":"protocol"}' : $json, "\n";
}

/** One outcome of a double (Runner's --simulate grammar): returns, throws, or the next of a sequence. */
function __divide_funcsim_answer(string $key, array $double, array $args, ?array &$context): mixed
{
    $state = &$GLOBALS['__divide_funcsim'];
    $n = $state['counts'][$key] = ($state['counts'][$key] ?? 0) + 1;
    $outcome = $double;
    if (isset($double['sequence'])) {
        $outcome = $double['sequence'][$n - 1] ?? null;
        if ($outcome === null) {
            $state['calls'][] = ['double' => $key, 'call' => $n, 'outcome' => 'exhausted'];
            throw new DivideMissingDouble("double {$key}: its sequence has no outcome for call {$n}");
        }
    }
    if ($context !== null && isset($outcome['context']) && is_array($outcome['context'])) {
        foreach ($outcome['context'] as $k => $v) {
            $context[$k] = $v;
        }
    }
    $record = ['double' => $key, 'call' => $n, 'args' => __divide_funcsim_value($args)];
    if (array_key_exists('throws', $outcome)) {
        $state['calls'][] = $record + ['outcome' => 'throws'];
        throw new RuntimeException((string) $outcome['throws']);
    }
    $state['calls'][] = $record + ['outcome' => 'returns'];
    return $outcome['returns'] ?? null;
}

/** A context service whose every method must be doubled. */
final class DivideDouble
{
    /** @param array<string, array> $methods */
    public function __construct(public readonly string $__divideName, private readonly array $methods)
    {
    }

    public function __call(string $method, array $args): mixed
    {
        $key = "{$this->__divideName}->{$method}";
        if (!isset($this->methods[$method])) {
            $GLOBALS['__divide_funcsim']['calls'][] = ['double' => $key, 'outcome' => 'missing'];
            throw new DivideMissingDouble("no double for {$key}()");
        }
        $none = null;
        return __divide_funcsim_answer($key, $this->methods[$method], $args, $none);
    }

    public function __get(string $name): mixed
    {
        throw new DivideMissingDouble("no double for the property {$this->__divideName}->{$name}");
    }

    public function __set(string $name, mixed $value): void
    {
        throw new DivideMissingDouble("no double for the property {$this->__divideName}->{$name}");
    }
}

register_shutdown_function(static function (): void {
    $state = $GLOBALS['__divide_funcsim'];
    if ($state['written']) {
        return;
    }
    $error = error_get_last();
    $fatal = $error !== null && in_array($error['type'], [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR, E_USER_ERROR], true);
    $context = $state['context'];
    __divide_funcsim_write([
        'status' => $fatal ? 'fatal' : 'exit',
        'error' => $fatal ? ['message' => $error['message'], 'file' => $error['file'], 'line' => $error['line']] : null,
        'after' => is_array($context) ? __divide_funcsim_value(__divide_funcsim_data($context)) : null,
    ]);
});

// ---------------------------------------------------------------- bootstrap
$scenario = $request['scenario'];
$file = (string) $request['file'];
ob_start(static function (string $chunk): string {
    $state = &$GLOBALS['__divide_funcsim'];
    $room = $state['stdout_limit'] - strlen($state['stdout']);
    if ($room > 0) {
        $state['stdout'] .= substr($chunk, 0, $room);
    }
    $state['stdout_cut'] += max(0, strlen($chunk) - max(0, $room));
    return '';
}, 4096);

if (!empty($scenario['autoload']) && is_string($request['autoload'] ?? null) && is_file($request['autoload'])) {
    require_once $request['autoload'];  // opted in: the project's classes are real code
}
spl_autoload_register(static function (string $class): void {
    $GLOBALS['__divide_funcsim']['calls'][] = ['double' => "class {$class}", 'outcome' => 'missing'];
    throw new DivideMissingDouble("no double for the class {$class} (and the project's autoload is not loaded)");
});

$expected = $scenario['function']['sha256'] ?? null;
$actual = is_file($file) ? hash_file('sha256', $file) : null;
if ($actual === null) {
    __divide_funcsim_write(['status' => 'missing', 'message' => "no file {$file}"]);
    exit(0);
}
if (is_string($expected) && $expected !== '' && !hash_equals($expected, $actual)) {
    __divide_funcsim_write(['status' => 'stale', 'message' => 'The Function changed since the scenario was written',
                            'sha256' => $actual]);
    exit(0);
}

// ---------------------------------------------------------------- load
$GLOBALS['__divide_funcsim']['phase'] = 'load';
try {
    $func = require $file;
} catch (Throwable $e) {
    __divide_funcsim_write(['status' => 'exception', 'exception' => __divide_funcsim_exception($e), 'sha256' => $actual]);
    exit(0);
}
if (!is_callable($func)) {
    __divide_funcsim_write(['status' => 'missing', 'message' => "{$file} does not return a callable", 'sha256' => $actual]);
    exit(0);
}

// ---------------------------------------------------------------- context and doubles
$context = is_array($scenario['context'] ?? null) ? $scenario['context'] : [];
$before = __divide_funcsim_value($context);
$importerDoubles = is_array($scenario['doubles']['importer'] ?? null) ? $scenario['doubles']['importer'] : [];
$context['_importer'] = static function (string $name, ?string $module = null) use ($importerDoubles): callable {
    $key = $module !== null && $module !== '' ? "{$module}:{$name}" : $name;
    if (!isset($importerDoubles[$key])) {
        $GLOBALS['__divide_funcsim']['calls'][] = ['double' => "import {$key}", 'outcome' => 'missing'];
        throw new DivideMissingDouble("no double for the import of {$key}");
    }
    $double = $importerDoubles[$key];
    // Called as Runner calls a Function: the context by reference first (it gets the double's
    // `context`), then anything else, which is only recorded.
    return static function (?array &$context = null, mixed ...$rest) use ($key, $double): mixed {
        return __divide_funcsim_answer($key, $double, $rest, $context);
    };
};
$context['_logger'] = static function (string $level, string $message, array $data = []): void {
    $GLOBALS['__divide_funcsim']['logs'][] = ['level' => $level, 'message' => $message];
};
foreach ((is_array($scenario['doubles']['services'] ?? null) ? $scenario['doubles']['services'] : []) as $key => $methods) {
    $context[$key] = new DivideDouble((string) $key, is_array($methods) ? $methods : []);
}
$GLOBALS['__divide_funcsim']['context'] = &$context;

// ---------------------------------------------------------------- call
$GLOBALS['__divide_funcsim']['phase'] = 'call';
try {
    $returned = $func($context);  // divide: the call (the line tracer steps into it from here)
} catch (Throwable $e) {
    $GLOBALS['__divide_funcsim']['phase'] = 'done';
    __divide_funcsim_write(['status' => 'exception', 'exception' => __divide_funcsim_exception($e), 'sha256' => $actual,
                            'before' => $before, 'after' => __divide_funcsim_value(__divide_funcsim_data($context))]);
    exit(0);
}
$GLOBALS['__divide_funcsim']['phase'] = 'done';  // divide: returned
__divide_funcsim_write([
    'status' => 'returned', 'sha256' => $actual, 'before' => $before,
    'return' => __divide_funcsim_value($returned), 'return_type' => get_debug_type($returned),
    'after' => __divide_funcsim_value(__divide_funcsim_data($context)),
]);
exit(0);
