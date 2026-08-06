import { describe, expect, it } from "vitest";
import { PiiRejectedError } from "./safety/pii";
import {
  MIN_CAMPAIGNS_FOR_RECALIBRATION,
  assessReadiness,
  parseCampaignCsv,
  previewUpload,
  validateUpload,
} from "./upload";

const header = "copy,impressions,clicks\n";
const row = (copy: string, impr = 5000, clicks = 60) =>
  `"${copy}",${impr},${clicks}\n`;

describe("parsing", () => {
  it("reads a well-formed file", () => {
    const csv = header + row("Save on heating") + row("Cut your bill");
    const r = parseCampaignCsv(csv);
    expect(r.rows).toHaveLength(2);
    expect(r.issues).toHaveLength(0);
    expect(r.rows[0].impressions).toBe(5000);
  });

  it("accepts common column aliases from real exports", () => {
    const csv = "Headline,Impr,Link Clicks\nSave big,5000,60\n";
    expect(parseCampaignCsv(csv).rows).toHaveLength(1);
  });

  it("names the missing columns rather than failing vaguely", () => {
    const r = parseCampaignCsv("copy,impressions\nhello,5000\n");
    expect(r.issues[0].problem).toMatch(/Missing required column\(s\): clicks/);
  });

  it("handles quoted copy containing commas", () => {
    const csv = header + '"Save now, before winter",5000,60\n';
    expect(parseCampaignCsv(csv).rows[0].copy).toBe("Save now, before winter");
  });

  it("handles escaped quotes", () => {
    const csv = header + '"He said ""yes"" today",5000,60\n';
    expect(parseCampaignCsv(csv).rows[0].copy).toBe('He said "yes" today');
  });

  it("strips thousands separators and currency symbols", () => {
    const csv = header + '"Save now","12,500",150\n';
    expect(parseCampaignCsv(csv).rows[0].impressions).toBe(12500);
  });
});

describe("row-level validation", () => {
  it("rejects low-impression rows as too noisy", () => {
    const r = parseCampaignCsv(header + row("Save now", 100, 3));
    expect(r.rows).toHaveLength(0);
    expect(r.issues[0].problem).toMatch(/sampling noise/);
  });

  it("rejects clicks exceeding impressions", () => {
    const r = parseCampaignCsv(header + row("Save now", 5000, 6000));
    expect(r.issues[0].problem).toMatch(/must be between 0 and impressions/);
  });

  it("rejects non-numeric metrics", () => {
    const r = parseCampaignCsv(header + '"Save now",lots,many\n');
    expect(r.issues[0].problem).toMatch(/not numeric/);
  });

  it("keeps good rows alongside bad ones", () => {
    const csv = header + row("Good row") + row("Too small", 50, 1) + row("Also good");
    const r = parseCampaignCsv(csv);
    expect(r.rows).toHaveLength(2);
    expect(r.issues).toHaveLength(1);
  });

  it("reports an empty file clearly", () => {
    expect(parseCampaignCsv("").issues[0].problem).toMatch(/no data rows/);
  });
});

describe("recalibration readiness", () => {
  it("is eligible at the floor", () => {
    const r = assessReadiness(MIN_CAMPAIGNS_FOR_RECALIBRATION);
    expect(r.eligible).toBe(true);
    expect(r.shrinkage).toBe(0);
  });

  it("shrinks toward the global model below the floor", () => {
    const r = assessReadiness(50);
    expect(r.eligible).toBe(false);
    expect(r.shrinkage).toBeCloseTo(0.75, 6);
    expect(r.message).toMatch(/blended 75% toward the global model/);
  });

  it("warns that the global model may not resemble the client's audience", () => {
    expect(assessReadiness(10).message).toMatch(/2013-15 viral media/);
  });

  it("does not refuse small uploads outright", () => {
    // Refusing a client with 50 campaigns helps nobody; blending and saying so
    // is the honest middle.
    expect(assessReadiness(50).shrinkage).toBeLessThan(1);
    expect(assessReadiness(0).shrinkage).toBe(1);
  });

  it("never reports shrinkage outside 0-1", () => {
    for (const n of [0, 1, 199, 200, 5000]) {
      const s = assessReadiness(n).shrinkage;
      expect(s).toBeGreaterThanOrEqual(0);
      expect(s).toBeLessThanOrEqual(1);
    }
  });
});

describe("PII gate", () => {
  it("rejects an upload containing an email before anything is stored", () => {
    const csv = header + row("Contact us at sales@brand.com");
    expect(() => validateUpload(csv)).toThrow(PiiRejectedError);
  });

  it("rejects a card number in the copy column", () => {
    const csv = header + row("Pay with 4111 1111 1111 1111");
    expect(() => validateUpload(csv)).toThrow(PiiRejectedError);
  });

  it("passes clean marketing copy through", () => {
    const csv = header + row("Save 20% on your energy bill this winter");
    expect(() => validateUpload(csv)).not.toThrow();
  });

  it("preview reports PII without throwing, so users can fix it", () => {
    const csv = header + row("Email hello@brand.com for details");
    const r = previewUpload(csv);
    expect(r.piiProblems.length).toBeGreaterThan(0);
    expect(r.rows).toHaveLength(1);
  });

  it("never echoes the detected value back", () => {
    const secret = "private.person@example.com";
    try {
      validateUpload(header + row(`Reach ${secret}`));
      throw new Error("should have thrown");
    } catch (e) {
      expect((e as Error).message).not.toContain(secret);
    }
  });
});
