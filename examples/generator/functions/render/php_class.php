<?php

// generate.php: templates/dto.tpl rendered by Div with the model, as build/src/<Class>.php.

declare(strict_types=1);

require_once dirname(__DIR__, 2) . '/lib/generator.php';

return function (array &$context): string {
    generator\stage($context, 'php');
    $relative = generator\outputs($context['dto'])['class'];
    generator\write($context, $relative, generator\render('dto.tpl', $context));
    return $relative;
};
