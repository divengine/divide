<?php

declare(strict_types=1);

return function (array &$context): string {
    $context["trail"][] = "record";
    return ($context["approver"] ?? "someone") . " approved " . number_format($context["total"], 2);
};
