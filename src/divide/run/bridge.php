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
 * With "op": "resolve" it renders nothing: it asks Div where the includes of
 * the template lead, the way Div itself resolves them when it includes:
 *   {"engine": ..., "op": "resolve", "path": "/abs/page.tpl",
 *    "includes": ["parts/menu", "box:data"], "history": ["/abs/parent.tpl"]}
 *   -> {"resolved": {"parts/menu": {"path": "parts/menu", "file": "/abs/parts/menu.tpl" | null}}, ...}
 * "history" seeds Div's include history (the templates that include this one),
 * which Div uses as a fallback for relative paths.
 *
 * Dialects (for the dialector), answered by Div itself:
 *   {"op": "dialect_validate", "tags": {"DIV_TAG_...": "..."}}
 *     -> {"valid": true | "<Div's reason>"}: the tags are defined before Div
 *        loads, then div::isValidCurrentDialect() judges them;
 *   {"op": "dialect_load", "path": "/abs/page.tpl", "ref": "<@_DIALECT value>", "history": [...]}
 *   {"op": "dialect_load", "file": "/abs/x.dialect"}
 *     -> {"file": "/abs/x.dialect" | null, "tags": {"DIV_TAG_...": "..."} | null, "problem": "..." | null}:
 *        as prepareDialect() does: getTplPath() finds the file, getFileContents()
 *        reads it and jsonDecode() decodes it;
 *   {"op": "translate", "from": {...} | "<dialect JSON>", "to": {...} | "<dialect JSON>", "code": "..."}
 *     -> {"translated": "..."}: div::translate(); an empty "from" / "to" is Div's
 *        default dialect, and dialect files are given as text for Div to decode.
 *
 * With "op": "trace" it renders as above and also records how Div got there:
 * the reply gains "trace": {"events": [...], "truncated": bool}. Div is not
 * changed: the template is a subclass of Div whose logger() (called by Div's
 * log mode, div::logOn(), at every step of its parser) notes the step, the
 * engine and its parse level, and the template's whole source when it changed
 * since that engine's last note:
 *   {"engine": 1, "level": 1, "message": "Parsing conditions...", "src": "..." | null}
 *
 * Div prints its errors into the output ("[[]]LEVEL: message" in CLI) and
 * dies on fatal ones, so everything is buffered and the reply is written
 * from a shutdown function.
 */

$messages = [];
$version = null;
$replied = false;  // the resolve operation answers by itself

set_error_handler(static function ($no, $str, $file, $line) use (&$messages) {
    $level = in_array($no, [E_DEPRECATED, E_USER_DEPRECATED], true) ? 'DEPRECATED' : 'PHP';
    $messages[] = ['level' => $level, 'text' => $str . ' (' . basename($file) . ':' . $line . ')'];
    return true;
});

register_shutdown_function(static function () use (&$messages, &$version, &$replied) {
    if ($replied) {
        return;
    }
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
    $reply = ['output' => $output, 'messages' => $messages, 'fatal' => $fatal, 'version' => $version];
    if (isset($GLOBALS['divide_trace'])) {
        $reply['trace'] = $GLOBALS['divide_trace'];
    }
    fwrite(STDOUT, json_encode(
        $reply,
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
$op = $request['op'] ?? 'render';
if ($op === 'dialect_validate') {
    // Div defines its tags with "defined(...) or define(...)": ours must come first.
    foreach ((array) ($request['tags'] ?? []) as $name => $value) {
        if (is_string($name) && strpos($name, 'DIV_TAG_') === 0 && !defined($name)) {
            define($name, (string) $value);
        }
    }
}

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

function reply_now(array $reply)
{
    global $replied;
    while (ob_get_level() > 0) {
        ob_end_clean();
    }
    $replied = true;
    fwrite(STDOUT, json_encode($reply, JSON_INVALID_UTF8_SUBSTITUTE | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
    exit(0);
}

if ($op === 'dialect_validate') {
    try {
        class_exists($divClass);  // loads div.php, which defines the tags we did not
        $valid = $divClass::isValidCurrentDialect();
    } catch (Throwable $e) {
        $valid = get_class($e) . ': ' . $e->getMessage();
    }
    reply_now(['valid' => $valid, 'messages' => $messages, 'version' => $version]);
}

if ($op === 'dialect_load') {
    $file = null;
    $tags = null;
    $problem = null;
    try {
        if (isset($request['ref'])) {
            $tpl = new $divClass('', []);
            $tpl->__path = $request['path'] ?? '';
            $history = array_values(array_filter((array) ($request['history'] ?? []), 'is_string'));
            if ($history) {
                $prop = new ReflectionProperty($divClass, '__includes_history');
                $prop->setAccessible(true);
                $prop->setValue(null, $history);
            }
            $ref = trim((string) $request['ref']);
            $file = $ref === '' ? null : $tpl->getTplPath($ref);
        } elseif (!isset($request['code'])) {
            $file = (string) ($request['file'] ?? '');
        }
        if (isset($request['code'])) {
            $json = (string) $request['code'];  // an unsaved buffer: only jsonDecode()
        } elseif ($file === null || $file === '' || !$divClass::fileExists($file)) {
            $problem = 'not found';
            $file = null;
        } else {
            $json = $divClass::getFileContents($file);
        }
        if ($problem === null) {
            $decoded = $json === null ? null : $divClass::jsonDecode($json);
            if (is_object($decoded)) {
                $decoded = get_object_vars($decoded);
            }
            if (!is_array($decoded) || ($decoded !== [] && array_keys($decoded) === range(0, count($decoded) - 1))) {
                $problem = 'Div cannot decode it as a JSON object';
            } else {
                $tags = [];
                foreach ($decoded as $name => $value) {
                    if (is_string($name) && strpos($name, 'DIV_TAG_') === 0 && is_scalar($value)) {
                        $tags[$name] = (string) $value;
                    }
                }
            }
            if ($file !== null) {
                $file = realpath($file) ?: $file;
            }
        }
    } catch (Throwable $e) {
        $problem = get_class($e) . ': ' . $e->getMessage();
    }
    reply_now(['file' => $file, 'tags' => $tags === null ? null : (object) $tags, 'problem' => $problem, 'messages' => $messages, 'version' => $version]);
}

if ($op === 'translate') {
    $translated = null;
    $dialect = static function ($d) use ($divClass) {
        if (is_string($d)) {
            $d = trim($d) === '' ? [] : $divClass::jsonDecode($d);
        }
        if (is_object($d)) {
            $d = get_object_vars($d);
        }
        return is_array($d) ? $d : null;
    };
    try {
        $from = $dialect($request['from'] ?? []);
        $to = $dialect($request['to'] ?? []);
        if ($from === null || $to === null) {
            throw new RuntimeException('Div could not decode the ' . ($from === null ? 'source' : 'target') . ' dialect');
        }
        $tpl = new $divClass('', []);
        $translated = $tpl->translate($from, $to, (string) ($request['code'] ?? ''));
    } catch (Throwable $e) {
        $messages[] = ['level' => 'FATAL', 'text' => get_class($e) . ': ' . $e->getMessage()];
    }
    reply_now(['translated' => $translated, 'messages' => $messages, 'version' => $version]);
}

if ($op === 'resolve') {
    $resolved = [];
    try {
        $tpl = new $divClass('', []);
        $tpl->__path = $request['path'];
        $history = array_values(array_filter((array) ($request['history'] ?? []), 'is_string'));
        if ($history) {
            $prop = new ReflectionProperty($divClass, '__includes_history');
            $prop->setAccessible(true);
            $prop->setValue(null, $history);
        }
        $separator = $request['separator'] ?? DIV_TAG_PREPROCESSED_SEPARATOR;
        foreach ((array) ($request['includes'] ?? []) as $raw) {
            // As Div's include parsers do: "path:data" when "path:data" itself is not a file.
            $path = trim((string) $raw);
            if ($separator !== '' && !$divClass::fileExists($path) && ($sep = strpos($path, $separator)) !== false) {
                $path = substr($path, 0, $sep);
            }
            $file = $tpl->getTplPath($path);
            $resolved[(string) $raw] = ['path' => $path, 'file' => $file === null ? null : (realpath($file) ?: $file)];
        }
    } catch (Throwable $e) {
        $messages[] = ['level' => 'FATAL', 'text' => get_class($e) . ': ' . $e->getMessage()];
    }
    while (ob_get_level() > 0) {
        ob_end_clean();
    }
    $replied = true;
    fwrite(STDOUT, json_encode(['resolved' => (object) $resolved, 'messages' => $messages, 'version' => $version], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
    exit(0);
}

if ($op === 'trace') {
    // What Div does, step by step: its own log messages, seen from a subclass.
    $GLOBALS['divide_trace'] = ['events' => [], 'truncated' => false];
    $GLOBALS['divide_trace_state'] = ['last' => [], 'bytes' => 0, 'level' => new ReflectionProperty($divClass, '__parse_level')];

    function divide_trace_note($engine, $message)
    {
        static $noise = ['Building instance', 'Destroying the instance', 'Template [checksum=', 'Loading the template'];
        foreach ($noise as $prefix) {
            if (strpos($message, $prefix) === 0) {
                return;
            }
        }
        $trace = &$GLOBALS['divide_trace'];
        $state = &$GLOBALS['divide_trace_state'];
        if (count($trace['events']) >= 50000) {
            $trace['truncated'] = true;
            return;
        }
        $id = spl_object_id($engine);  // Div's clones of its auxiliary engine share getId()
        $src = (string) $engine->__src;
        $crc = crc32($src);
        $changed = !isset($state['last'][$id]) || $state['last'][$id] !== $crc;
        if ($changed && $state['bytes'] + strlen($src) > 64 * 1024 * 1024) {
            $trace['truncated'] = true;
            $changed = false;
        }
        if ($changed) {
            $state['last'][$id] = $crc;
            $state['bytes'] += strlen($src);
        }
        $trace['events'][] = [
            'engine' => $id,
            'level' => $state['level']->getValue(),
            'message' => $message,
            'src' => $changed ? $src : null,
        ];
    }

    trait divide_tracing
    {
        public function logger($msg, $level = 'INFO')
        {
            divide_trace_note($this, (string) $msg);
        }
    }

    if ($divClass === 'divengine\\div') {
        class divide_traced extends \divengine\div
        {
            use divide_tracing;
        }
    } else {
        class divide_traced extends \div
        {
            use divide_tracing;
        }
    }
    $null = stripos(PHP_OS_FAMILY, 'win') === 0 ? 'NUL' : '/dev/null';
    $divClass::logOn($null);  // the log file gets only Div's static notes; ours go to the trace
    $divClass = 'divide_traced';
}

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
