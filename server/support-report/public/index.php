<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/src/bootstrap.php';

use SupportReport\RateLimiter;
use SupportReport\SupportReportHandler;

header('Content-Type: application/json; charset=utf-8');

$handler = new SupportReportHandler(
    new RateLimiter(dirname(__DIR__) . '/storage/ratelimit')
);

[$statusCode, $payload] = $handler->handle(
    $_SERVER['REQUEST_METHOD'] ?? 'GET',
    file_get_contents('php://input') ?: '',
    $_SERVER
);

http_response_code($statusCode);
echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
