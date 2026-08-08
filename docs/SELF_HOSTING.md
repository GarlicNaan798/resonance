# Self-hosting Resonance

For agencies and in-house teams whose campaign data cannot leave their own
infrastructure. In self-hosted mode Resonance makes **no outbound network calls
at all** — models run locally, and there is no telemetry.

This is the deployment most enterprise security reviews will require, so it is
supported as a first-class mode rather than an afterthought.

## What runs where

| Component | Self-hosted | Notes |
|---|---|---|
| Next.js app | your infrastructure | UI + API routes |
| Module model (diagnostic) | in-process | 60 KB of JSON weights, pure TypeScript |
| Embedding encoder | in-process | ONNX, ~90 MB, bundled — never downloaded at runtime |
| Postgres | your infrastructure | campaign uploads, audit log |
| Outbound calls | **none** | verify with the egress test below |

## Requirements

- Docker and Docker Compose, or Node 20+ and Postgres 15+
- 2 vCPU / 4 GB RAM minimum. The encoder is the memory driver; 8 GB is
  comfortable for concurrent use.
- No GPU. Inference is CPU-only by design.

## Quick start

```bash
cp .env.example .env
docker compose up -d
```

The app is then on `http://localhost:3000`.

## Configuration

Set these in `.env`. `loadSafetyConfig()` validates them at startup and the app
**refuses to boot** on an unsafe combination rather than logging a warning
nobody reads.

| Variable | Default | Notes |
|---|---|---|
| `RESONANCE_MODE` | `cloud` | set to `self-hosted` |
| `RESONANCE_REGION` | `eu-west-1` | use `self-hosted` |
| `RESONANCE_ENCRYPTION_AT_REST` | `true` | may be `false` self-hosted if your volume is already encrypted |
| `RESONANCE_ENCRYPTION_IN_TRANSIT` | `true` | **cannot be disabled** |
| `RESONANCE_RETENTION_DAYS` | `365` | max 730; indefinite retention is not offered |
| `RESONANCE_ALLOW_CROSS_REGION` | `false` | rejected outright for EU regions |
| `RESONANCE_AUDIT_VERIFY_HOURS` | `24` | audit hash-chain verification cadence |

`DATABASE_URL` is the only other required variable.

## Data protection in this mode

- **Personal data is rejected at ingest.** Uploads containing emails, phone
  numbers, card numbers, IPs or addresses are refused; nothing is stored and
  redacted. See `resonance/lib/safety/pii.ts`.
- **Tenant isolation is structural.** Queries cannot be constructed without a
  tenant context. Relevant even single-tenant, because it keeps client
  workspaces separate within one agency.
- **The audit log is append-only and hash-chained.** Run
  `verifyChain()` on a schedule; a broken chain means the log was altered.
- **Model isolation.** Recalibrated weights are namespaced per tenant. One
  client's uploads never influence another's model.

## Verifying there is no egress

Do not take the claim on trust — the point of self-hosting is that you can check
it. Run the container with networking disabled and confirm the app still works:

```bash
docker compose run --rm --network none app npm run selftest
```

Or watch for outbound connections under normal use:

```bash
docker compose exec app sh -c "netstat -tunp | grep -v 127.0.0.1"
```

The encoder weights are baked into the image at build time precisely so nothing
is fetched at runtime.

## Backups

Back up Postgres normally. Two cautions:

- **The audit log must be backed up append-only.** Restoring an older snapshot
  over a newer log destroys the chain and the accountability record with it.
- **Backups inherit retention obligations.** A deletion request is not satisfied
  while the data survives in a backup past its retention window.

## Upgrades

Model weights are versioned in `resonance/lib/inference/`. Upgrading may change
scores, so any historical comparison should record the model version alongside
the result. `module_model.json` carries `format_version` for exactly this.

## What you are not getting

Stated plainly, because a security review will ask:

- **No outcome prediction.** The tool ranks variants and profiles copy. It does
  not forecast conversions or revenue — see `data/processed/model_card.md`.
- **Global model accuracy is 61.8%** on held-out randomised experiments
  (chance 50%, measured ceiling 66.2%). Recalibrating on your own campaigns is
  expected to beat that, and is the intended path.
- **No neural or biochemical measurement.** Module names refer to functional
  systems from the literature; the scores are psychometric, computed from
  published human word ratings.
