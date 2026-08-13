import { describe, expect, it } from "vitest";
import {
  SafetyConfig,
  SafetyConfigError,
  assertSafe,

  isExpired,
  loadSafetyConfig,
} from "./config";

const base: SafetyConfig = {
  mode: "cloud",
  region: "eu-west-1",
  encryptionAtRest: true,
  encryptionInTransit: true,
  retentionDays: 365,
  allowCrossRegionReplication: false,
  auditVerifyIntervalHours: 24,
};

describe("refuses indefensible configurations", () => {
  it("will not run without encryption in transit", () => {
    expect(() => assertSafe({ ...base, encryptionInTransit: false }))
      .toThrow(SafetyConfigError);
  });

  it("requires encryption at rest in cloud mode", () => {
    expect(() => assertSafe({ ...base, encryptionAtRest: false }))
      .toThrow(SafetyConfigError);
  });

  it("allows self-hosted without managed at-rest encryption", () => {
    expect(() => assertSafe({
      ...base, mode: "self-hosted", region: "self-hosted",
      encryptionAtRest: false,
    })).not.toThrow();
  });

  it("rejects indefinite retention", () => {
    expect(() => assertSafe({ ...base, retentionDays: 5000 }))
      .toThrow(SafetyConfigError);
    expect(() => assertSafe({ ...base, retentionDays: 0 }))
      .toThrow(SafetyConfigError);
  });

  it("blocks cross-region replication of EU data", () => {
    expect(() => assertSafe({ ...base, allowCrossRegionReplication: true }))
      .toThrow(SafetyConfigError);
  });

  it("permits cross-region replication outside the EU", () => {
    expect(() => assertSafe({
      ...base, region: "us-east-1", allowCrossRegionReplication: true,
    })).not.toThrow();
  });
});

describe("loading from env", () => {
  it("defaults to safe values", () => {
    const cfg = loadSafetyConfig({});
    expect(cfg.encryptionAtRest).toBe(true);
    expect(cfg.encryptionInTransit).toBe(true);
    expect(cfg.allowCrossRegionReplication).toBe(false);
    expect(cfg.region).toBe("eu-west-1");
  });

  it("fails fast on an unknown region rather than guessing", () => {
    expect(() => loadSafetyConfig({ RESONANCE_REGION: "mars-1" }))
      .toThrow(SafetyConfigError);
  });

  it("cannot be talked out of transit encryption by env", () => {
    expect(() => loadSafetyConfig({
      RESONANCE_ENCRYPTION_IN_TRANSIT: "false",
    })).toThrow(SafetyConfigError);
  });
});

describe("retention", () => {
  it("expires records past the window", () => {
    const now = new Date("2026-08-05T00:00:00Z");
    expect(isExpired("2025-01-01T00:00:00Z", base, now)).toBe(true);
    expect(isExpired("2026-07-01T00:00:00Z", base, now)).toBe(false);
  });

  it("treats an unparseable timestamp as an error, not as 'keep forever'", () => {
    expect(() => isExpired("not-a-date", base)).toThrow(SafetyConfigError);
  });
});

// The "customer-facing summary" suite is gone with describeSafety(). It
// asserted that the output contained "never trains another tenant" — a
// guarantee about a per-tenant model that was never built. The test passed and
// the claim was false, which is the failure mode where a test certifies
// wording rather than behaviour.
