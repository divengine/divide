<?php

// generate.readme: templates/readme.tpl rendered by Div with the same model, as build/README.md.

declare(strict_types=1);

require_once dirname(__DIR__, 2) . '/lib/generator.php';

return function (array &$context): string {
    generator\stage($context, 'readme');
    $relative = generator\outputs($context['dto'])['readme'];
    generator\write($context, $relative, generator\render('readme.tpl', $context));
    return $relative;
};
