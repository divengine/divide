<?php
/**
 * The shop's home page, rendered by Div from PHP.
 *
 *     composer require divengine/div
 *     php -S localhost:8000
 */

require __DIR__ . '/vendor/autoload.php';

use divengine\div;

$data = json_decode(file_get_contents(__DIR__ . '/index.json'), true);
$data['today'] = date('Y-m-d');

echo new div('index.tpl', $data);
