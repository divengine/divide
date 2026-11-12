<?php
/**
 * divide render bridge.
 *
 * Reads one JSON request on stdin:
 *   {"engine": "/path/vendor/autoload.php | /path/div.php", "path": "/abs/page.tpl",
 *    "code": "<template source>", "data": "<json text>|null"}
 * Prints one JSON reply on stdout:
 *   {"output": "...", "messages": [{"level": "WARNING|FATAL|PHP", "text": "..."}], "fatal": bool, "version": "..."}
 *
 * Div prints its errors into the output ("[[]]LEVEL: message" in CLI) and
 * dies on fatal ones, so everything is buffered and the reply is written
 * from a shutdown function.
 */

$messages = [];
$version = null;

set_error_handler(static function ($no, $str, $file, $line) use (&$messages) {
    $level = in_array($no, [E_DEPRECATED, E_USER_DEPRECATED], true) ? 'DEPRECATED' : 'PHP';
    $messages[] = ['level' => $level, 'text' => $str . ' (' . basename($file) . ':' . $line . ')'];
    return true;
});

register_shutdown_function(static function () use (&$messages, &$version) {
    $buffer = '';
    while (ob_get_level() > 0) {
        $buffer = ob_get_clean() . $buffer;
    }
    $fatal = false;
    $output = preg_replace_callback('/^\[\[\]\](\w+): (.*)\R?/m', static function ($m) use (&$messages, &$fatal) {
        $messages[] = ['level' => $m[1], 'text' => trim($m[2])];
        $fatal = $fatal || $m[1] === 'FATAL';
        return '';
    }, $buffer);
    $last = error_get_last();
    if ($last !== null && in_array($last['type'], [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR], true)) {
        $messages[] = ['level' => 'FATAL', 'text' => $last['message'] . ' (' . basename($last['file']) . ':' . $last['line'] . ')'];
        $fatal = true;
    }
    fwrite(STDOUT, json_encode(
        ['output' => $output, 'messages' => $messages, 'fatal' => $fatal, 'version' => $version],
        JSON_INVALID_UTF8_SUBSTITUTE | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES
    ));
});

ob_start();

$request = json_decode(stream_get_contents(STDIN), true);
if (!is_array($request)) {
    $messages[] = ['level' => 'FATAL', 'text' => 'divide bridge: bad request'];
    exit(0);
}

// Composer's autoload.php (the usual install) or a bare div.php; Div needs the
// divengine/functions helpers, found next to a checkout's own vendor/ if any.
$engine = $request['engine'];
require_once $engine;
if (basename($engine) === 'div.php' && !function_exists('divengine\\string')) {
    $autoload = dirname($engine, 2) . '/vendor/autoload.php';
    if (is_file($autoload)) {
        require_once $autoload;
    }
}
$divClass = class_exists('divengine\\div') ? 'divengine\\div' : 'div';
if (!class_exists($divClass)) {
    $messages[] = ['level' => 'FATAL', 'text' => "Div not found in $engine"];
    exit(0);
}
$version = $divClass::getVersion();

try {
    // Decode with Div's own (lenient) JSON parser, so the check matches what the template sees.
    $data = $request['data'] ?? null;
    $items = [];
    if ($data !== null && trim($data) !== '') {
        $decoded = $divClass::jsonDecode($data);
        if (is_object($decoded)) {
            $decoded = get_object_vars($decoded);
        }
        if (is_array($decoded)) {
            $items = $decoded;
        } else {
            $messages[] = ['level' => 'DATA', 'text' => 'Div could not decode the data as an object; rendering without data'];
        }
    }
    $tpl = new $divClass($request['code'], $items);
    // Includes relative to the template need its real path (the code came from the editor).
    $tpl->__path = $request['path'];
    echo (string) $tpl;
} catch (Throwable $e) {
    $messages[] = ['level' => 'FATAL', 'text' => get_class($e) . ': ' . $e->getMessage() . ' (' . basename($e->getFile()) . ':' . $e->getLine() . ')'];
}
