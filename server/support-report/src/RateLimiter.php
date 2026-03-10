<?php
declare(strict_types=1);

namespace SupportReport;

use RuntimeException;

final class RateLimiter
{
    public function __construct(
        private readonly string $storageDir,
        private readonly int $maxAttempts = 5,
        private readonly int $windowSeconds = 3600,
    ) {
    }

    public function allow(string $ipAddress): bool
    {
        $normalizedIp = trim($ipAddress) !== '' ? trim($ipAddress) : 'unknown';
        $this->ensureStorageDir();

        $filePath = $this->storageDir . '/' . hash('sha256', $normalizedIp) . '.json';
        $handle = fopen($filePath, 'c+');
        if ($handle === false) {
            throw new RuntimeException('Unable to open rate limit storage file.');
        }

        try {
            if (!flock($handle, LOCK_EX)) {
                throw new RuntimeException('Unable to lock rate limit storage file.');
            }

            $content = stream_get_contents($handle);
            $payload = json_decode($content ?: '{}', true);
            if (!is_array($payload)) {
                $payload = [];
            }
            $timestamps = is_array($payload['timestamps'] ?? null) ? $payload['timestamps'] : [];

            $now = time();
            $cutoff = $now - $this->windowSeconds;
            $timestamps = array_values(array_filter(
                $timestamps,
                static fn ($value): bool => is_int($value) && $value >= $cutoff
            ));

            if (count($timestamps) >= $this->maxAttempts) {
                $this->writePayload($handle, $timestamps);
                return false;
            }

            $timestamps[] = $now;
            $this->writePayload($handle, $timestamps);
            return true;
        } finally {
            flock($handle, LOCK_UN);
            fclose($handle);
        }
    }

    private function ensureStorageDir(): void
    {
        if (is_dir($this->storageDir)) {
            return;
        }

        if (!mkdir($this->storageDir, 0775, true) && !is_dir($this->storageDir)) {
            throw new RuntimeException('Unable to create rate limit storage directory.');
        }
    }

    private function writePayload($handle, array $timestamps): void
    {
        $payload = json_encode(['timestamps' => $timestamps], JSON_UNESCAPED_SLASHES);
        if ($payload === false) {
            throw new RuntimeException('Unable to encode rate limit payload.');
        }

        rewind($handle);
        ftruncate($handle, 0);
        fwrite($handle, $payload);
        fflush($handle);
    }
}
