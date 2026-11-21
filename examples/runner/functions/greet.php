<?php

declare(strict_types=1);

// The returned value is stored in $context["greet"] (the Step id).
return fn (array &$context): string => "Hello " . ($context["name"] ?? "World");
