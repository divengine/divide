<?php

declare(strict_types=1);

return function (array &$context): string {
    $context["trail"][] = "receipt";
    return sprintf("Total: %.2f%s", $context["total"], empty($context["approved"]) ? "" : " (approved)");
};
