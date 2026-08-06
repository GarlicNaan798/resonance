/**
 * Tenant isolation tests.
 *
 * The central assertion the plan calls for: tenant A cannot read or train on
 * tenant B's data. Everything else here supports that claim.
 */

import { beforeEach, describe, expect, it } from "vitest";
import {
  InMemoryAuditSink,
  auditTrail,
  setAuditSink,
  verifyChain,
} from "./audit";
import {
  CampaignRecord,
  InMemoryStore,
  TenantIsolationError,
  TenantRepository,
  modelKey,
  tenantContext,
} from "./tenant";

const ALICE = tenantContext("agency-alice", "user-1", "eu-west-1");
const BOB = tenantContext("agency-bob", "user-2", "us-east-1");

function repo(store: InMemoryStore<CampaignRecord>, ctx = ALICE) {
  return new TenantRepository<CampaignRecord>(store, ctx, "campaign");
}

const row = (id: string): Omit<CampaignRecord, "tenantId"> => ({
  id,
  copy: "Save big today",
  impressions: 1000,
  clicks: 12,
  createdAt: "2026-08-05T00:00:00Z",
});

describe("tenant scoping", () => {
  beforeEach(() => setAuditSink(new InMemoryAuditSink()));

  it("stamps the tenant on insert rather than trusting the caller", async () => {
    const store = new InMemoryStore<CampaignRecord>();
    await repo(store).insert(row("c1"));
    const all = await store.all();
    expect(all[0].tenantId).toBe("agency-alice");
  });

  it("A cannot list B's records", async () => {
    const store = new InMemoryStore<CampaignRecord>();
    await repo(store, ALICE).insert(row("c1"));
    await repo(store, BOB).insert(row("c2"));

    const alice = await repo(store, ALICE).list();
    expect(alice.map((r) => r.id)).toEqual(["c1"]);

    const bob = await repo(store, BOB).list();
    expect(bob.map((r) => r.id)).toEqual(["c2"]);
  });

  it("A cannot fetch B's record even knowing its id", async () => {
    const store = new InMemoryStore<CampaignRecord>();
    await repo(store, BOB).insert(row("secret-id"));
    expect(await repo(store, ALICE).get("secret-id")).toBeUndefined();
  });

  it("A cannot delete B's record", async () => {
    const store = new InMemoryStore<CampaignRecord>();
    await repo(store, BOB).insert(row("secret-id"));
    expect(await repo(store, ALICE).remove("secret-id")).toBe(false);
    expect((await store.all()).length).toBe(1);
  });

  it("records a cross-tenant attempt in the audit log", async () => {
    const store = new InMemoryStore<CampaignRecord>();
    await repo(store, BOB).insert(row("secret-id"));
    await repo(store, ALICE).get("secret-id");
    const trail = await auditTrail("agency-alice");
    expect(trail.some((e) => e.action === "cross_tenant_denied")).toBe(true);
  });
});

describe("context validation", () => {
  it("rejects ids that could subvert scoping", () => {
    for (const bad of ["", "*", "../other", "a", "x".repeat(70), "has space"]) {
      expect(() => tenantContext(bad, "user-1", "eu-west-1")).toThrow(
        TenantIsolationError,
      );
    }
  });
});

describe("model artefact isolation", () => {
  it("namespaces per tenant and region", () => {
    expect(modelKey(ALICE, "ranker.json")).toBe(
      "eu-west-1/agency-alice/ranker.json",
    );
    expect(modelKey(BOB, "ranker.json")).not.toBe(modelKey(ALICE, "ranker.json"));
  });

  it("rejects traversal in the artefact name", () => {
    expect(() => modelKey(ALICE, "../bob/ranker.json")).toThrow(
      TenantIsolationError,
    );
  });
});

describe("audit chain", () => {
  beforeEach(() => setAuditSink(new InMemoryAuditSink()));

  it("verifies a well-formed chain", async () => {
    const store = new InMemoryStore<CampaignRecord>();
    await repo(store).insert(row("c1"));
    await repo(store).insert(row("c2"));
    await repo(store).list();
    expect((await verifyChain()).valid).toBe(true);
  });

  it("detects an altered entry", async () => {
    const sink = new InMemoryAuditSink();
    setAuditSink(sink);
    const store = new InMemoryStore<CampaignRecord>();
    await repo(store).insert(row("c1"));
    await repo(store).insert(row("c2"));

    // Tamper: rewrite a field without recomputing the hash.
    const entries = await sink.all();
    (entries[0] as { actorId: string }).actorId = "someone-else";

    const v = await verifyChain();
    expect(v.valid).toBe(false);
    expect(v.brokenAt).toBe(1);
  });

  it("never stores record content", async () => {
    const store = new InMemoryStore<CampaignRecord>();
    await repo(store).insert({ ...row("c1"), copy: "TOP SECRET COPY" });
    const serialised = JSON.stringify(await auditTrail("agency-alice"));
    expect(serialised).not.toContain("TOP SECRET COPY");
  });
});
