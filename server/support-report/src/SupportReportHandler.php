<?php
declare(strict_types=1);

namespace SupportReport;

use PHPMailer\PHPMailer\Exception as PHPMailerException;
use PHPMailer\PHPMailer\PHPMailer;
use Throwable;

final class SupportReportHandler
{
    private const SMTP_HOST = 'smtp.mail.ovh.net';
    private const SMTP_PORT = 465;
    private const SMTP_USERNAME = 'app-notification@mathieumartin.ovh';
    private const SMTP_FROM = 'app-notification@mathieumartin.ovh';
    private const REPORT_TO = 'contact@mathieumartin.ovh';
    private const SMTP_PASSWORD_ENV = 'APPCLAVIER_SMTP_PASS';
    private const APP_NAME = 'Accessible Media Converter';

    private const ISSUE_LABELS = [
        'conversion_problem' => 'Problème de conversion',
        'application_crash' => "Crash de l'application",
        'update_problem' => 'Problème de mise à jour',
        'accessibility_issue' => "Problème d'accessibilité",
        'installation_problem' => "Problème d'installation",
        'feature_request' => 'Demande de fonctionnalité',
        'other' => 'Autre',
    ];

    public function __construct(
        private readonly RateLimiter $rateLimiter,
    ) {
    }

    public function handle(string $requestMethod, string $rawBody, array $server): array
    {
        if (strtoupper($requestMethod) !== 'POST') {
            return [405, $this->errorResponse('validation_error', 'Méthode non autorisée.')];
        }

        $payload = json_decode($rawBody, true);
        if (!is_array($payload)) {
            return [400, $this->errorResponse('validation_error', 'Le JSON envoyé est invalide.')];
        }

        $validationError = $this->validatePayload($payload);
        if ($validationError !== null) {
            return [422, $this->errorResponse('validation_error', $validationError)];
        }

        $clientIp = $this->resolveClientIp($server);
        try {
            if (!$this->rateLimiter->allow($clientIp)) {
                return [429, $this->errorResponse('rate_limited', 'Trop de rapports ont été envoyés récemment. Veuillez réessayer plus tard.')];
            }
        } catch (Throwable) {
            return [500, $this->errorResponse('server_error', 'Le rapport n’a pas pu être envoyé pour le moment.')];
        }

        try {
            $this->sendMail($payload);
        } catch (Throwable) {
            return [500, $this->errorResponse('server_error', 'Le rapport n’a pas pu être envoyé pour le moment.')];
        }

        return [200, [
            'ok' => true,
            'message' => 'Votre rapport a été envoyé avec succès.',
        ]];
    }

    private function validatePayload(array $payload): ?string
    {
        $email = trim((string) ($payload['email'] ?? ''));
        $issueType = trim((string) ($payload['issue_type'] ?? ''));
        $message = trim((string) ($payload['message'] ?? ''));
        $honeypot = trim((string) ($payload['honeypot'] ?? ''));
        $technicalContext = $payload['technical_context'] ?? null;

        if ($honeypot !== '') {
            return 'Le formulaire de support est invalide.';
        }
        if ($email === '' || filter_var($email, FILTER_VALIDATE_EMAIL) === false) {
            return 'L’adresse email est invalide.';
        }
        if (!array_key_exists($issueType, self::ISSUE_LABELS)) {
            return 'Le type de problème est invalide.';
        }
        if ($message === '') {
            return 'Le message est obligatoire.';
        }
        if (!is_array($technicalContext)) {
            return 'Les informations techniques sont invalides.';
        }

        return null;
    }

    private function sendMail(array $payload): void
    {
        $password = getenv(self::SMTP_PASSWORD_ENV) ?: '';
        if ($password === '') {
            throw new PHPMailerException('Missing SMTP password.');
        }

        $email = trim((string) $payload['email']);
        $issueType = trim((string) $payload['issue_type']);
        $message = trim((string) $payload['message']);
        $technicalContext = is_array($payload['technical_context']) ? $payload['technical_context'] : [];

        $mailer = new PHPMailer(true);
        $mailer->isSMTP();
        $mailer->Host = self::SMTP_HOST;
        $mailer->Port = self::SMTP_PORT;
        $mailer->SMTPAuth = true;
        $mailer->SMTPSecure = PHPMailer::ENCRYPTION_SMTPS;
        $mailer->Username = self::SMTP_USERNAME;
        $mailer->Password = $password;
        $mailer->CharSet = 'UTF-8';
        $mailer->Encoding = 'base64';

        $mailer->setFrom(self::SMTP_FROM, self::APP_NAME);
        $mailer->addAddress(self::REPORT_TO);
        $mailer->addReplyTo($email);

        $mailer->Subject = $this->buildSubject($issueType, $technicalContext);
        $mailer->Body = $this->buildBody($email, $issueType, $message, $technicalContext);

        $mailer->send();
    }

    private function buildSubject(string $issueType, array $technicalContext): string
    {
        $version = trim((string) ($technicalContext['app_version'] ?? 'inconnue'));
        $issueLabel = self::ISSUE_LABELS[$issueType] ?? self::ISSUE_LABELS['other'];

        return sprintf('%s - %s - v%s', self::APP_NAME, $issueLabel, $version);
    }

    private function buildBody(string $email, string $issueType, string $message, array $technicalContext): string
    {
        $lines = [
            'Type de demande : ' . (self::ISSUE_LABELS[$issueType] ?? self::ISSUE_LABELS['other']),
            'Email utilisateur : ' . $email,
            'Date de réception : ' . gmdate('Y-m-d H:i:s') . ' UTC',
            '',
            'Message utilisateur :',
            $message,
            '',
            'Informations techniques :',
            'Version de l’application : ' . $this->stringValue($technicalContext, 'app_version', 'inconnue'),
            'Mode d’exécution : ' . $this->formatExecutionMode($technicalContext['execution_mode'] ?? 'source'),
            'Système d’exploitation : ' . $this->stringValue($technicalContext, 'operating_system', 'inconnu'),
            'Langue : ' . $this->stringValue($technicalContext, 'language', 'inconnue'),
            'Onglet courant : ' . $this->formatTab($technicalContext['current_tab'] ?? 'audio'),
            'Format de sortie sélectionné : ' . $this->stringValue($technicalContext, 'selected_output_format', 'non sélectionné'),
            'Mode debug : ' . $this->formatBoolean($technicalContext['debug_mode_enabled'] ?? false),
            'Données debug présentes : ' . $this->formatBoolean($technicalContext['debug_data_present'] ?? false),
            'Fichiers audio chargés : ' . $this->stringValue($technicalContext, 'loaded_audio_files_count', '0'),
            'Fichiers vidéo chargés : ' . $this->stringValue($technicalContext, 'loaded_video_files_count', '0'),
            'Vérification auto des mises à jour : ' . $this->formatBoolean($technicalContext['auto_update_check_enabled'] ?? false),
            'Politique de sortie existante : ' . $this->formatExistingOutputPolicy($technicalContext['existing_output_policy'] ?? 'rename'),
            'Conversions simultanées max : ' . $this->stringValue($technicalContext, 'max_concurrent_jobs', '0'),
            'Threads FFmpeg : ' . $this->formatFfmpegThreads($technicalContext['ffmpeg_threads'] ?? 'auto'),
        ];

        return implode(PHP_EOL, $lines);
    }

    private function stringValue(array $context, string $key, string $fallback): string
    {
        $value = $context[$key] ?? null;
        if ($value === null || $value === '') {
            return $fallback;
        }
        return trim((string) $value);
    }

    private function formatExecutionMode(mixed $value): string
    {
        return $value === 'packaged' ? 'packagé' : 'source';
    }

    private function formatTab(mixed $value): string
    {
        return $value === 'video' ? 'vidéo' : 'audio';
    }

    private function formatBoolean(mixed $value): string
    {
        return filter_var($value, FILTER_VALIDATE_BOOL) ? 'oui' : 'non';
    }

    private function formatExistingOutputPolicy(mixed $value): string
    {
        return match ((string) $value) {
            'overwrite' => 'écraser le fichier existant',
            'skip' => 'ignorer le fichier existant',
            default => 'renommer automatiquement',
        };
    }

    private function formatFfmpegThreads(mixed $value): string
    {
        return is_string($value) && strtolower($value) === 'auto'
            ? 'automatique'
            : trim((string) $value);
    }

    private function resolveClientIp(array $server): string
    {
        $forwarded = trim((string) ($server['HTTP_X_FORWARDED_FOR'] ?? ''));
        if ($forwarded !== '') {
            $parts = explode(',', $forwarded);
            return trim((string) ($parts[0] ?? 'unknown'));
        }

        return trim((string) ($server['REMOTE_ADDR'] ?? 'unknown'));
    }

    private function errorResponse(string $errorCode, string $message): array
    {
        return [
            'ok' => false,
            'error_code' => $errorCode,
            'message' => $message,
        ];
    }
}
