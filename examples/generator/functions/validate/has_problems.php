<?php

// validate.reject's condition: validation found something.

declare(strict_types=1);

return fn (array &$context): bool => !empty($context['problems']);
