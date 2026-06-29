# 13 — Sandbox Domain

Isolamento de execução do **Replay** e de qualquer código de agente que rodamos por nossa conta.

> Replay executa código de agente do usuário. Tool maliciosa pode tentar `rm -rf`, exfiltrar chaves, ou minerar crypto. Sandbox é fronteira de segurança.

## Stack

| Camada | Ferramenta v1 | v2 (se crescer) |
|---|---|---|
| Execução | **Firecracker microVM** (Fly Machines) | gVisor |
| Orquestração | Fly Machines API | Kubernetes + Kata |
| FS | overlayfs ephemeral | mesmo |
| Network | eBPF allowlist | Cilium |
| Secrets | mounted volume, TTL 5 min | Vault |

## Modelo de threat

| Atacante | Objetivo | Mitigação |
|---|---|---|
| Tool maliciosa do usuário | ler FS do host | overlayfs read-only + ephemeral |
| Tool maliciosa do usuário | exfiltrar dados via HTTP | network egress allowlist por tool |
| Tool maliciosa do usuário | minerar crypto | CPU/mem cap + timeout duro |
| Tool maliciosa do usuário | escapar sandbox | seccomp + Landlock + no `CAP_*` |
| User malicioso | DoS via replay pesado | rate limit + queue + budget |
| Tool bem escrita com bug | corromper state | checkpoint versionado, restore |

## Garantias

1. **Não persiste nada no host** — overlayfs ephemeral, descartado no fim.
2. **Network egress por allowlist** — tool só fala com domínios que registrou.
3. **Sem capabilities privilegiadas** — roda como `nobody`, sem `CAP_*`.
4. **CPU/mem cap hard** — `4 vCPU`, `8 GB RAM`, swap=0.
5. **Timeout duro** — `replay_timeout_seconds = 30` (default), max `300`.
6. **Filesystem read-only exceto `/tmp`** — `/tmp` tmpfs 256 MB cap.
7. **Sem `ptrace`, sem `/proc` writable** — seccomp profile bloqueia.
8. **Kill switch** — admin pode `kill` sandbox ativo via API.

## Arquitetura

```
┌─────────────────────────────────────────┐
│ Fly Machine (microVM)                   │
│                                         │
│  ┌──────────────────────────────────┐   │
│  │ Sandbox Runtime                  │   │
│  │  - python:3.12-slim              │   │
│  │  - ai_obs SDK (read-only)        │   │
│  │  - user's agent code (read-only) │   │
│  │  - tools (sandboxed)             │   │
│  │  - /tmp (256MB tmpfs)            │   │
│  └──────────────────────────────────┘   │
│                                         │
│  Network:                              │
│    - ingress: from fly proxy only      │
│    - egress: allowlist (config)        │
│                                         │
│  Limits:                               │
│    - cpu: 4 vCPU                       │
│    - mem: 8 GB                         │
│    - timeout: 30s (default)            │
└─────────────────────────────────────────┘
         ▲                       │
         │ stdin/stdout          │ HTTP egress (allowlist)
         │                       ▼
   ┌─────┴──────┐         ┌──────────────┐
   │ Replay     │         │ Allowlist    │
   │ Engine     │         │ (per tool)   │
   └────────────┘         └──────────────┘
```

## Per-tool network allowlist

```yaml
# config/network-allowlist.yaml
tools:
  browser.fetch:
    allowed_domains: ["*"]               # genérico
    blocked_domains: ["169.254.0.0/16"]  # link-local
  github.read:
    allowed_domains: ["api.github.com"]
  internal.cache:
    allowed_domains: ["cache.internal:6379"]
    protocol: "redis"
  default:
    allowed_domains: []
    blocked: true
```

- Allowlist **vazia = ferramenta não pode fazer rede**. Default deny.
- Mudança requer deploy de config (auditado).
- DNS resolvido dentro do sandbox, NXDOMAIN = blocked.

## Seccomp profile (resumo)

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64"],
  "syscalls": [
    { "names": ["read", "write", "open", "close", "stat", "fstat", "mmap", "brk", "exit_group"], "action": "SCMP_ACT_ALLOW" },
    { "names": ["clone", "fork", "vfork"], "action": "SCMP_ACT_ALLOW", "args": [{ "index": 0, "mask": "SCMP_CMASK", "value": 0x100 }] },
    { "names": ["ptrace", "mount", "umount2", "kexec_load", "reboot"], "action": "SCMP_ACT_KILL" }
  ]
}
```

## API de controle

```
POST /v1/sandbox/start
  body: { run_id, step, tools[], timeout_s }
  → { sandbox_id, machine_id, ssh_endpoint (internal only) }

POST /v1/sandbox/{id}/kill
  auth: admin
  → 204

GET  /v1/sandbox/{id}/status
  → { state, cpu_pct, mem_mb, network_bytes, elapsed_s }
```

## Replay dentro do sandbox

1. `ReplayEngine` chama `POST /v1/sandbox/start` com `tools[]` do run.
2. Sandbox monta `/state` com checkpoints + `/artifacts` com S3 via FUSE.
3. Sandbox executa `python -m ai_obs.replay --config /state/config.yaml`.
4. Output é `ReplayResult` streamado via stdout JSON Lines.
5. Engine recolhe, atualiza `ReplaySession`, mata sandbox.
6. Sandbox efêmero é destruído — nada persiste.

## Limits & quotas

| Recurso | Por replay | Por org/dia |
|---|---|---|
| Wall time | 30s (default), 300s (max) | 100h |
| CPU | 4 vCPU | 400 vCPU·h |
| Memory | 8 GB | — |
| Network egress | 1 GB | 50 GB |
| Disk write | 256 MB | 10 GB |
| Sandboxes simultâneos | 1/run | 10/org |

## Erros

| Cenário | `error.code` | Recovery |
|---|---|---|
| Sandbox start failed | `SANDBOX_BOOT_FAILED` | retry 1x, depois `REPLAY_DIVERGED` |
| Tool tried blocked syscall | `SANDBOX_SECCOMP_VIOLATION` | kill sandbox, alerta de segurança |
| Tool tried blocked domain | `SANDBOX_NETWORK_VIOLATION` | kill sandbox, alerta |
| Timeout exceeded | `SANDBOX_TIMEOUT` | matar, retornar step parcial |
| OOM | `SANDBOX_OOM` | matar, retornar `CHECKPOINT_MISSING` |

## Telemetria do sandbox

| Métrica | Tipo |
|---|---|
| `sandbox_active` | gauge |
| `sandbox_boot_seconds` | histogram |
| `sandbox_violations_total` | counter `{kind: seccomp\|network\|fs}` |
| `sandbox_cpu_seconds_total` | counter |
| `sandbox_egress_bytes` | counter |
| `sandbox_kills_total` | counter `{reason}` |

## O que este domínio **NÃO** decide

- Como Replay consome o sandbox → `05-replay.md` (chama API daqui)
- Quem pode iniciar replay → `11-auth.md` (scope `runs.replay`)
- Como custo do sandbox é debitado → `06-cost.md` (não debita; sandbox é free p/ user, custo interno)
