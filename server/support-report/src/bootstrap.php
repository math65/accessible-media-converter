<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/vendor/phpmailer/src/Exception.php';
require_once dirname(__DIR__) . '/vendor/phpmailer/src/PHPMailer.php';
require_once dirname(__DIR__) . '/vendor/phpmailer/src/SMTP.php';

require_once __DIR__ . '/RateLimiter.php';
require_once __DIR__ . '/SupportReportHandler.php';
