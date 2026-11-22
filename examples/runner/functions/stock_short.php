<?php

declare(strict_types=1);

return fn (array &$context): bool => empty($context["retried"]);
