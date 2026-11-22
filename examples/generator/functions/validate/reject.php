<?php

// validate.reject: the run ends in error with the problems, before anything is written.

declare(strict_types=1);

return function (array &$context): never {
    throw new RuntimeException("The model is not valid:\n- " . implode("\n- ", $context['problems']));
};
