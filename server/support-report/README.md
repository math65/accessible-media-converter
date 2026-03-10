# Support Report Backend

This directory contains the PHP backend used by the desktop app to send support reports directly to `contact@mathieumartin.ovh`.

## Requirements

- PHP 8.2
- `PHPMailer` vendored in `vendor/phpmailer/`
- PHP-FPM environment variable:
  - `APPCLAVIER_SMTP_PASS`

## SMTP settings

The backend is configured for OVH MX Plan:

- host: `smtp.mail.ovh.net`
- port: `465`
- security: `SSL/TLS`
- username: `app-notification@mathieumartin.ovh`

## Public endpoint

Expected public URL:

- `https://mathieumartin.ovh/api/support-report`

The web server should route this URL to:

- `server/support-report/public/index.php`

## Writable directory

The following directory must be writable by PHP-FPM:

- `server/support-report/storage/ratelimit/`
