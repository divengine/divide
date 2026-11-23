<?php

declare(strict_types=1);

// A Function written for injection: its dependencies come from the context.
return function (array &$context): string {
    $total = 0.0;
    foreach ($context["items"] ?? [] as $item) {
        $line = $item["price"] * $item["qty"];
        $total += $line;
    }
    $tax = $context["_importer"]("tax", "billing");
    $total += $tax($context);
    if ($total > 100) {
        $context["_logger"]("INFO", "large order");
        $context["review"] = true;
    }
    $sent = $context["mailer"]->send($context["email"], "Total: " . $total);
    $context["total"] = $total;
    echo "sent: ", $sent ? "yes" : "no", "\n";
    return $sent ? "notified" : "pending";
};
