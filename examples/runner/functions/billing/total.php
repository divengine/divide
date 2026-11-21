<?php

declare(strict_types=1);

return function (array &$context): float {
    $sum = 0.0;
    foreach ($context["items"] ?? [] as $item) {
        $sum += $item["price"] * $item["qty"];
    }
    return $sum;
};
