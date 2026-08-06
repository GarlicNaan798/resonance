/**
 * Tenant isolation, enforced at the data-access layer.
 *
 * The common way this goes wrong is putting the tenant check in route handlers:
 * every handler must remember to filter by tenant, and the one that forgets
 * leaks one agency's campaign data to another. That failure is invisible in
 * testing because the happy path looks identical.
 *
 * Here the tenant is structural instead. A query cannot be constructed without
 * a TenantContext, scoping is applied inside the repository, and the raw store
 * is not exported. Forgetting to scope is not something a caller can express.
 *
 * Every stored record carries `tenantId`, and reads, writes and deletes are all
 * filtered. Model artefacts are namespaced by tenant too, so one client's
 * uploads can never influence another's recalibrated model — the requirement
 * that made per-tenant isolation necessary in the first place.
 */

import { appendAudit } from "./audit";

/** Opaque tenant handle. Constructed only via `tenantContext()`. */
export interface TenantContext {
  readonly tenantId: string;
  readonly actorId: string;
  /** Data residency for this tenant, e.g. "eu-west-1". */
  readonly region: string;
  readonly __brand: "TenantContext";
}

export class TenantIsolationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TenantIsolationError";
  }
}

const ID_RE = /^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$/;

export function tenantContext(
  tenantId: string,
  actorId: string,
  region: string,
): TenantContext {
  // Reject anything that could be used to escape scoping via wildcards, path
  // traversal, or an empty id that a naive filter would treat as "match all".
  if (!ID_RE.test(tenantId)) {
    throw new TenantIsolationError(`Invalid tenantId: ${JSON.stringify(tenantId)}`);
  }
  if (!ID_RE.test(actorId)) {
    throw new TenantIsolationError(`Invalid actorId: ${JSON.stringify(actorId)}`);
  }
  return { tenantId, actorId, region, __brand: "TenantContext" };
}

/** Anything persisted carries its owner. */
export interface TenantOwned {
  readonly tenantId: string;
  readonly id: string;
}

export interface CampaignRecord extends TenantOwned {
  copy: string;
  impressions: number;
  clicks: number;
  segment?: string;
  createdAt: string;
}

/**
 * Storage port. A real deployment binds this to Postgres with row-level
 * security; the in-memory implementation below is for tests and self-host
 * evaluation. RLS is defence in depth, not a replacement for this layer.
 */
export interface Store<T extends TenantOwned> {
  insert(record: T): Promise<void>;
  all(): Promise<T[]>;
  remove(id: string): Promise<boolean>;
}

export class InMemoryStore<T extends TenantOwned> implements Store<T> {
  private rows: T[] = [];

  async insert(record: T): Promise<void> {
    this.rows.push(record);
  }

  async all(): Promise<T[]> {
    return this.rows.slice();
  }

  async remove(id: string): Promise<boolean> {
    const before = this.rows.length;
    this.rows = this.rows.filter((r) => r.id !== id);
    return this.rows.length < before;
  }
}

/**
 * Tenant-scoped repository. Every method filters by the context's tenantId;
 * there is no unscoped read path on this class.
 */
export class TenantRepository<T extends TenantOwned> {
  constructor(
    private readonly store: Store<T>,
    private readonly ctx: TenantContext,
    private readonly resource: string,
  ) {}

  async insert(record: Omit<T, "tenantId">): Promise<void> {
    // The caller does not supply tenantId — it is stamped here, so a client
    // cannot write into another tenant by forging a field.
    const owned = { ...record, tenantId: this.ctx.tenantId } as T;
    await this.store.insert(owned);
    await appendAudit({
      action: "insert",
      resource: this.resource,
      tenantId: this.ctx.tenantId,
      actorId: this.ctx.actorId,
      recordId: record.id,
    });
  }

  async list(): Promise<T[]> {
    const rows = (await this.store.all()).filter(
      (r) => r.tenantId === this.ctx.tenantId,
    );
    await appendAudit({
      action: "read",
      resource: this.resource,
      tenantId: this.ctx.tenantId,
      actorId: this.ctx.actorId,
      count: rows.length,
    });
    return rows;
  }

  async get(id: string): Promise<T | undefined> {
    const rows = await this.store.all();
    const row = rows.find((r) => r.id === id);
    if (!row) return undefined;
    if (row.tenantId !== this.ctx.tenantId) {
      // Deliberately indistinguishable from "not found" to the caller, but
      // recorded loudly: a cross-tenant id guess is a security signal.
      await appendAudit({
        action: "cross_tenant_denied",
        resource: this.resource,
        tenantId: this.ctx.tenantId,
        actorId: this.ctx.actorId,
        recordId: id,
      });
      return undefined;
    }
    return row;
  }

  async remove(id: string): Promise<boolean> {
    const existing = await this.get(id);
    if (!existing) return false;
    const ok = await this.store.remove(id);
    await appendAudit({
      action: "delete",
      resource: this.resource,
      tenantId: this.ctx.tenantId,
      actorId: this.ctx.actorId,
      recordId: id,
    });
    return ok;
  }
}

/**
 * Namespaced key for per-tenant model artefacts. Recalibrated weights must
 * never be shared, and a shared cache key is the easy way to leak them.
 */
export function modelKey(ctx: TenantContext, name: string): string {
  if (!/^[a-zA-Z0-9._-]{1,64}$/.test(name)) {
    throw new TenantIsolationError(`Invalid model name: ${JSON.stringify(name)}`);
  }
  return `${ctx.region}/${ctx.tenantId}/${name}`;
}
