<?php

declare(strict_types=1);

// Not written for injection: a direct side effect no double can intercept.
return function (array &$context): bool {
    $context["step"] = "writing";
    return file_put_contents($context["path"], "real write") !== false;
};
