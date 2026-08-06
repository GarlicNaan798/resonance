/**
 * Data-protection configuration: encryption, residency, retention.
 *
 * The point of putting these in one typed, validated place is that they are the
 * settings a customer's security review will ask about, and the ones most
 * likely to drift silently between environments. `loadSafetyConfig()` fails
 * fast at startup rather than letting a production instance boot with
 * encryption off because an env var was misspelled.
 *
 * Encryption at rest is delegated to the storage layer (managed database
 * encryption, or an encrypted volume) rather than reimplemented here. Rolling
 * our own record encryption would mean owning key rotation, envelope
 * encryption and backup key escrow — all of which the platform already does
 * better. What this module owns is *asserting* that it is switched on, and
 * refusing to run if it is not.
 */

export type Region = "eu-west-1" | "eu-central-1" | "us-east-1" | "us-west-2"
  | "ap-southeast-2" | "self-hosted";

export type DeploymentMode = "cloud" | "self-hosted";

export interface SafetyConfig {
  readonly mode: DeploymentMode;
  /** Where this tenant's data physically resides. */
  readonly region: Region;
  /** Must be true in cloud mode; asserted at startup. */
  readonly encryptionAtRest: boolean;
  /** TLS enforced for all transport. */
  readonly encryptionInTransit: boolean;
  /** Days before uploaded campaign data is purged. */
  readonly retentionDays: number;
  /** If false, no data leaves the deployment region for any reason. */
  readonly allowCrossRegionReplication: boolean;
  /** Verify the audit hash chain on this cadence, in hours. */
  readonly auditVerifyIntervalHours: number;
}

export class SafetyConfigError extends Error {
  constructor(message: string) {
    super(`Unsafe configuration: ${message}`);
    this.name = "SafetyConfigError";
  }
}

const REGIONS: readonly Region[] = [
  "eu-west-1", "eu-central-1", "us-east-1", "us-west-2",
  "ap-southeast-2", "self-hosted",
];

/** GDPR default: 24 months. Shorter is fine; unlimited is not. */
const MAX_RETENTION_DAYS = 730;

function bool(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined || value === "") return fallback;
  return /^(1|true|yes|on)$/i.test(value);
}

export function loadSafetyConfig(
  env: Record<string, string | undefined> = process.env,
): SafetyConfig {
  const mode = (env.RESONANCE_MODE ?? "cloud") as DeploymentMode;
  if (mode !== "cloud" && mode !== "self-hosted") {
    throw new SafetyConfigError(`unknown RESONANCE_MODE: ${mode}`);
  }

  const region = (env.RESONANCE_REGION
    ?? (mode === "self-hosted" ? "self-hosted" : "eu-west-1")) as Region;
  if (!REGIONS.includes(region)) {
    throw new SafetyConfigError(`unknown RESONANCE_REGION: ${region}`);
  }

  const cfg: SafetyConfig = {
    mode,
    region,
    encryptionAtRest: bool(env.RESONANCE_ENCRYPTION_AT_REST, true),
    encryptionInTransit: bool(env.RESONANCE_ENCRYPTION_IN_TRANSIT, true),
    retentionDays: Number(env.RESONANCE_RETENTION_DAYS ?? 365),
    allowCrossRegionReplication:
      bool(env.RESONANCE_ALLOW_CROSS_REGION, false),
    auditVerifyIntervalHours:
      Number(env.RESONANCE_AUDIT_VERIFY_HOURS ?? 24),
  };

  assertSafe(cfg);
  return cfg;
}

/**
 * Fail fast on a configuration that would be indefensible in a security
 * review. These are refusals, not warnings — a warning in a startup log is a
 * warning nobody reads.
 */
export function assertSafe(cfg: SafetyConfig): void {
  if (!cfg.encryptionInTransit) {
    throw new SafetyConfigError("encryption in transit cannot be disabled");
  }
  if (cfg.mode === "cloud" && !cfg.encryptionAtRest) {
    throw new SafetyConfigError(
      "encryption at rest is required in cloud mode",
    );
  }
  if (!Number.isFinite(cfg.retentionDays) || cfg.retentionDays <= 0) {
    throw new SafetyConfigError("retentionDays must be a positive number");
  }
  if (cfg.retentionDays > MAX_RETENTION_DAYS) {
    throw new SafetyConfigError(
      `retentionDays ${cfg.retentionDays} exceeds the ${MAX_RETENTION_DAYS}-day ` +
        "maximum; indefinite retention of client data is not offered",
    );
  }
  if (cfg.region === "self-hosted" && cfg.mode !== "self-hosted") {
    throw new SafetyConfigError(
      "region 'self-hosted' requires RESONANCE_MODE=self-hosted",
    );
  }
  if (cfg.allowCrossRegionReplication && cfg.region.startsWith("eu-")) {
    throw new SafetyConfigError(
      "cross-region replication is not permitted for EU-resident data",
    );
  }
}

/** True when a record is past its retention window and must be purged. */
export function isExpired(
  createdAtIso: string,
  cfg: SafetyConfig,
  now: Date = new Date(),
): boolean {
  const created = new Date(createdAtIso).getTime();
  if (Number.isNaN(created)) {
    // An unparseable timestamp must not read as "keep forever".
    throw new SafetyConfigError(`invalid createdAt: ${createdAtIso}`);
  }
  const ageDays = (now.getTime() - created) / 86_400_000;
  return ageDays > cfg.retentionDays;
}

/** Summary for the UI's data-protection panel. Safe to show a customer. */
export function describeSafety(cfg: SafetyConfig): string[] {
  return [
    `Deployment: ${cfg.mode}`,
    `Data residency: ${cfg.region}`,
    `Encryption at rest: ${cfg.encryptionAtRest ? "enabled" : "n/a (self-hosted)"}`,
    "Encryption in transit: enforced",
    `Retention: ${cfg.retentionDays} days, then purged`,
    `Cross-region replication: ${cfg.allowCrossRegionReplication ? "enabled" : "disabled"}`,
    "Personal data: rejected at ingest, never stored",
    "Model isolation: per-tenant; your data never trains another tenant's model",
  ];
}
