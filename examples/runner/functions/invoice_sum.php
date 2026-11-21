<?php

declare(strict_types=1);

return fn (array &$context): float => $context["lines"] + $context["shipping"];
