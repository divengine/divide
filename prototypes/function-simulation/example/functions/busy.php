<?php

declare(strict_types=1);

// A loop, to measure how fast the line trace is.
return function (array &$context): int {
    $sum = 0;
    for ($i = 0; $i < $context["n"]; $i++) {
        $sum += $i;
    }
    return $sum;
};
