<?php

declare(strict_types=1);

return function (array &$context): bool {
    $context["trail"][] = "check";
    return true;
};
