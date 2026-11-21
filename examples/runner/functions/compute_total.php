<?php

declare(strict_types=1);

return function (array &$context): float {
    $context["trail"][] = "total";
    $total = 0.0;
    foreach ($context["items"] ?? [] as $item) {
        $total += $item["price"] * $item["qty"];
    }
    return $total;
};
