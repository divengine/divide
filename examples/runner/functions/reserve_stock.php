<?php

declare(strict_types=1);

return function (array &$context): int {
    $context["trail"][] = "reserve";
    return ($context["reserve"] ?? 0) + 1;
};
