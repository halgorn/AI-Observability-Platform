<?php

declare(strict_types=1);

/**
 * AI Observability Platform — PHP client
 * Requires PHP >= 8.1, ext-curl, ext-json (both enabled by default)
 */
final class AiObs
{
    private static string  $ingestUrl    = '';
    private static string  $token        = '';
    private static ?string $currentRunId = null;
    private static ?string $currentAgent = null;
    private static array   $spanStack    = [];

    public static function configure(string $ingestUrl, string $token): void
    {
        self::$ingestUrl = rtrim($ingestUrl, '/');
        self::$token     = $token;
    }

    public static function run(string $agent, array $input, callable $fn): mixed
    {
        $runId   = self::uuid4();
        $spanId  = self::randSpan();
        $started = self::now();

        self::$currentRunId = $runId;
        self::$currentAgent = $agent;
        self::$spanStack    = [$spanId];

        self::emit([
            'run_id'     => $runId,
            'span_id'    => $spanId,
            'type'       => 'run.start',
            'agent'      => $agent,
            'started_at' => $started,
            'payload'    => ['agent' => $agent, 'input_hash' => self::hashOf($input)],
        ]);

        $ctx    = new RunContext($runId, $agent, $spanId);
        $status = 'succeeded';
        try {
            return $fn($ctx);
        } catch (\Throwable $e) {
            $status = 'failed';
            throw $e;
        } finally {
            self::emit([
                'run_id'     => $runId,
                'span_id'    => self::randSpan(),
                'type'       => 'run.end',
                'agent'      => $agent,
                'started_at' => $started,
                'ended_at'   => self::now(),
                'payload'    => [
                    'status'         => $status,
                    'total_steps'    => $ctx->steps,
                    'total_tokens'   => $ctx->totalTokens,
                    'total_cost_usd' => $ctx->totalCost,
                ],
            ]);
            self::$currentRunId = null;
            self::$currentAgent = null;
            self::$spanStack    = [];
        }
    }

    public static function observe(
        ?string $llm   = null,
        ?string $tool  = null,
        ?string $agent = null,
        callable $fn   = null
    ): mixed {
        $kind   = $llm ? 'llm' : ($tool ? 'tool' : ($agent ? 'agent' : null));
        $target = $llm ?? $tool ?? $agent;
        if (!$kind || !$fn) {
            throw new \InvalidArgumentException('observe requires exactly one of llm, tool, agent AND a callable');
        }
        if (!self::$currentRunId) {
            throw new \RuntimeException('observe must be called inside run()');
        }

        $parent   = end(self::$spanStack) ?: null;
        $spanId   = self::randSpan();
        $started  = self::now();
        $typeMap  = ['llm' => 'llm.call', 'tool' => 'tool.invoke', 'agent' => 'step.start'];
        $type     = $typeMap[$kind];
        $curAgent = self::$currentAgent;
        $runId    = self::$currentRunId;

        $error = null;
        try {
            return $fn();
        } catch (\Throwable $e) {
            $error = $e;
            throw $e;
        } finally {
            $payload = match ($kind) {
                'llm'   => ['model' => $target, 'finish_reason' => $error ? 'error' : 'stop'],
                'tool'  => ['tool' => $target, 'args_hash' => 'sha256:' . str_repeat('0', 64), 'status' => $error ? 'error' : 'ok'],
                'agent' => ['step' => 0, 'status' => $error ? 'error' : 'ok'],
            };
            self::emit(array_filter([
                'run_id'         => $runId,
                'span_id'        => $spanId,
                'parent_span_id' => $parent,
                'type'           => $type,
                'agent'          => $curAgent,
                'llm_model'      => $kind === 'llm' ? $target : null,
                'started_at'     => $started,
                'ended_at'       => self::now(),
                'payload'        => $payload,
            ], static fn($v) => $v !== null));
        }
    }

    /** Generates a signed token. Normally done server-side — for reference/testing only. */
    public static function issueToken(
        string $secret,
        string $orgId,
        string $name    = 'default',
        array  $scopes  = ['ingest.write'],
        int    $ttl     = 31_536_000
    ): string {
        $raw = json_encode(['org_id' => $orgId, 'scopes' => $scopes, 'exp' => time() + $ttl, 'name' => $name]);
        $b64 = rtrim(strtr(base64_encode($raw), '+/', '-_'), '=');
        $sig = substr(hash_hmac('sha256', $b64, $secret), 0, 32);
        return "ai_obs_v1.{$b64}.{$sig}";
    }

    public static function emit(array $event): void
    {
        $url  = self::$ingestUrl . '/v1/events';
        $body = json_encode([$event]);
        $ch   = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_POST           => true,
            CURLOPT_POSTFIELDS     => $body,
            CURLOPT_HTTPHEADER     => [
                'Content-Type: application/json',
                'Authorization: Bearer ' . self::$token,
            ],
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 5,
        ]);
        curl_exec($ch);
        curl_close($ch);
    }

    private static function uuid4(): string
    {
        $b     = random_bytes(16);
        $b[6]  = chr(ord($b[6]) & 0x0f | 0x40);
        $b[8]  = chr(ord($b[8]) & 0x3f | 0x80);
        return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($b), 4));
    }

    private static function randSpan(): string { return bin2hex(random_bytes(8)); }

    private static function now(): string
    {
        return (new \DateTime('now', new \DateTimeZone('UTC')))->format(\DateTime::ATOM);
    }

    private static function hashOf(mixed $v): string
    {
        return 'sha256:' . hash('sha256', json_encode($v));
    }
}

final class RunContext
{
    public int   $steps       = 0;
    public int   $totalTokens = 0;
    public float $totalCost   = 0.0;

    public function __construct(
        public readonly string $runId,
        public readonly string $agent,
        public readonly string $spanId,
    ) {}

    public function checkpoint(int $step, array $state): void
    {
        $this->steps++;
        AiObs::emit([
            'run_id'     => $this->runId,
            'span_id'    => bin2hex(random_bytes(8)),
            'type'       => 'checkpoint',
            'agent'      => $this->agent,
            'started_at' => (new \DateTime('now', new \DateTimeZone('UTC')))->format(\DateTime::ATOM),
            'payload'    => ['step' => $step, 'state_hash' => 'sha256:' . hash('sha256', json_encode($state))],
        ]);
    }

    public function handoff(string $to, string $reason = 'delegation', array $payload = []): void
    {
        AiObs::emit([
            'run_id'     => $this->runId,
            'span_id'    => bin2hex(random_bytes(8)),
            'type'       => 'handoff',
            'agent'      => $this->agent,
            'started_at' => (new \DateTime('now', new \DateTimeZone('UTC')))->format(\DateTime::ATOM),
            'payload'    => [
                'from'         => $this->agent,
                'to'           => $to,
                'reason'       => $reason,
                'payload_hash' => 'sha256:' . hash('sha256', json_encode($payload)),
            ],
        ]);
    }
}
