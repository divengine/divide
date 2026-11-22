<?php

/**
 * What the generator's functions share: where things are, the model as the
 * templates see it, rendering with Div, hashing and writing inside the output
 * folder only.
 *
 * Every path is relative to this project (the folder above lib/), whatever the
 * working directory, and the output folder must be build/ or a folder in it.
 */

declare(strict_types=1);

namespace generator;

require_once dirname(__DIR__) . '/vendor/autoload.php';

use divengine\div;
use RuntimeException;

const TYPES = ['string', 'int', 'float', 'bool'];

/** Words PHP keeps for itself (lowercase). */
const RESERVED = ['abstract', 'and', 'array', 'as', 'bool', 'break', 'callable', 'case', 'catch', 'class', 'clone',
    'const', 'continue', 'declare', 'default', 'do', 'echo', 'else', 'elseif', 'empty', 'enum', 'eval', 'exit',
    'extends', 'false', 'final', 'float', 'fn', 'for', 'foreach', 'function', 'global', 'goto', 'if', 'implements',
    'include', 'instanceof', 'insteadof', 'int', 'interface', 'isset', 'iterable', 'list', 'match', 'mixed',
    'namespace', 'never', 'new', 'null', 'object', 'or', 'parent', 'print', 'private', 'protected', 'public',
    'readonly', 'require', 'return', 'self', 'static', 'string', 'switch', 'throw', 'trait', 'true', 'try', 'unset',
    'use', 'var', 'void', 'while', 'xor', 'yield'];

/** The generator's own inputs besides the model: a change in any of them regenerates. */
const RULES = [
    'templates/dto.tpl',
    'templates/readme.tpl',
    'lib/generator.php',
    'functions/render/php_class.php',
    'functions/render/readme.php',
];

function root(): string
{
    return dirname(__DIR__);
}

/** A path of this project, from one relative to it, never outside it. */
function inside(string $relative): string
{
    $relative = str_replace('\\', '/', $relative);
    if ($relative === '' || $relative[0] === '/' || preg_match('~^[A-Za-z]:~', $relative)) {
        throw new RuntimeException("Not a path relative to the generator: $relative");
    }
    foreach (explode('/', $relative) as $part) {
        if ($part === '..') {
            throw new RuntimeException("A path may not leave the generator: $relative");
        }
    }
    return root() . '/' . trim($relative, '/');
}

/** The output folder: build/ or a folder inside it. */
function output(array $context): string
{
    $relative = trim(str_replace('\\', '/', (string) ($context['output'] ?? 'build')), '/');
    if ($relative !== 'build' && !str_starts_with($relative, 'build/')) {
        throw new RuntimeException("The output must be build/ or a folder in it: $relative");
    }
    return inside($relative);
}

/** The files generated from a model, relative to the output folder. */
function outputs(array $model): array
{
    return ['class' => 'src/' . $model['class'] . '.php', 'readme' => 'README.md'];
}

/** The model as the templates read it: every field with all its keys. */
function template_data(array $context): array
{
    $model = $context['dto'];
    $model['description'] = $model['description'] ?? '';
    $model['model_file'] = $context['model'];
    $model['fields'] = array_map(static fn (array $field): array => [
        'name' => $field['name'],
        'type' => $field['type'],
        'nullable' => (bool) ($field['nullable'] ?? false),
        'description' => $field['description'] ?? '',
    ], $model['fields']);
    return $model;
}

/** A template of templates/ rendered by Div with the model. */
function render(string $template, array $context): string
{
    return (string) new div(inside("templates/$template"), template_data($context));
}

/** One hash of the model and of the rules that turn it into code. */
function inputs_hash(array $context): string
{
    $hash = hash_init('sha256');
    foreach (array_merge([$context['model']], RULES) as $file) {
        hash_update($hash, $file . "\0" . read($file) . "\0");
    }
    return hash_final($hash);
}

function read(string $relative): string
{
    $text = @file_get_contents(inside($relative));
    if ($text === false) {
        throw new RuntimeException("Cannot read $relative");
    }
    return $text;
}

/** Writes a file of the output folder (through a temporary file, then a rename). */
function write(array $context, string $relative, string $text): string
{
    $path = output($context) . '/' . $relative;
    if (str_contains($relative, '..')) {
        throw new RuntimeException("A path may not leave the output: $relative");
    }
    if (!is_dir(dirname($path)) && !mkdir(dirname($path), 0777, true) && !is_dir(dirname($path))) {
        throw new RuntimeException('Cannot create ' . dirname($path));
    }
    $temporary = $path . '.tmp';
    if (file_put_contents($temporary, $text) === false || !rename($temporary, $path)) {
        throw new RuntimeException("Cannot write $relative");
    }
    return $path;
}

function stage(array &$context, string $name): void
{
    $context['trail'][] = $name;
}

function json(array $value): string
{
    return json_encode($value, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR) . "\n";
}
