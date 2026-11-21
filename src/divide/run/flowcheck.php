<?php
/**
 * divide's check of a Runner Flow: Runner's own compiler, without running anything.
 *
 *     php flowcheck.php RUNNER_SRC FLOW_YAML < names.json
 *
 * RUNNER_SRC is Runner's single source file (vendor/divengine/runner/src/runner.php):
 * nothing else is loaded, not the project's autoloader, so no code of the project
 * runs. runner::generateFlowCodeFromYaml() parses the YAML, validates its schema and
 * resolves call and jump targets; the code it returns is not evaluated, so no
 * condition or activity runs.
 *
 * stdin: a JSON list of function names; the answer says which are PHP functions
 * (function_exists, built-in or of an extension: nothing of the project is loaded).
 *
 * stdout: {"ok": true} or {"ok": false, "error": "..."}, with "functions": [names
 * that are PHP functions].
 */

declare(strict_types=1);

$runner = $argv[1] ?? "";
$flow = $argv[2] ?? "";
$answer = ["ok" => false, "error" => null, "functions" => []];

$names = json_decode((string) stream_get_contents(STDIN), true);
if (is_array($names)) {
    foreach ($names as $name) {
        if (is_string($name) && $name !== "" && function_exists(ltrim($name, "\\"))) {
            $answer["functions"][] = $name;
        }
    }
}

try {
    if (!is_file($runner)) {
        throw new RuntimeException("Runner's source was not found: {$runner}");
    }
    require_once $runner;
    \divengine\runner\runner::generateFlowCodeFromYaml($flow);
    $answer["ok"] = true;
} catch (Throwable $e) {
    $answer["error"] = str_replace("[divengine.runner] ", "", $e->getMessage());
}

echo json_encode($answer, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE), "\n";
