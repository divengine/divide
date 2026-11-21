<?php

declare(strict_types=1);

return fn (array &$context): float => count($context["items"] ?? []) * 2.5;
