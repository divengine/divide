<?php

declare(strict_types=1);

return fn (array &$context): bool => ($context["total"] ?? 0) >= 20 && empty($context["approved"]);
