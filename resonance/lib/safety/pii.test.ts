/**
 * PII detector tests.
 *
 * Two failure modes matter equally here, and the second is the one that usually
 * ships broken:
 *
 *   1. FALSE NEGATIVES leak personal data into storage.
 *   2. FALSE POSITIVES block legitimate marketing copy. A tool that rejects
 *      "Save 50% on orders over $100" or "Call to action" is unusable, and the
 *      user's only recourse is to disable the check entirely, which is worse
 *      than not having it.
 *
 * So the negative cases below are as load-bearing as the positive ones.
 */

import { describe, expect, it } from "vitest";
import { assertNoPii, PiiRejectedError, scanRows, scanText } from "./pii";

describe("detects real PII", () => {
  it("finds email addresses", () => {
    const r = scanText("Contact sarah.chen@example.co.uk for details");
    expect(r.clean).toBe(false);
    expect(r.findings[0].kind).toBe("email");
  });

  it("finds Luhn-valid card numbers", () => {
    // Standard Visa test number, valid checksum, not a real card.
    const r = scanText("card 4111 1111 1111 1111 on file");
    expect(r.findings.some((f) => f.kind === "credit_card")).toBe(true);
  });

  it("finds SSN-formatted values", () => {
    const r = scanText("SSN 123-45-6789");
    expect(r.findings.some((f) => f.kind === "ssn")).toBe(true);
  });

  it("finds IBANs", () => {
    const r = scanText("pay to GB82WEST12345698765432");
    expect(r.findings.some((f) => f.kind === "iban")).toBe(true);
  });

  it("finds IP addresses (personal data under GDPR)", () => {
    const r = scanText("user seen at 192.168.14.201 yesterday");
    expect(r.findings.some((f) => f.kind === "ip_address")).toBe(true);
  });

  it("finds phone numbers", () => {
    const r = scanText("ring +44 20 7946 0958 to book");
    expect(r.findings.some((f) => f.kind === "phone")).toBe(true);
  });

  it("finds street addresses", () => {
    const r = scanText("ship to 221 Baker Street");
    expect(r.findings.some((f) => f.kind === "postal_address")).toBe(true);
  });

  it("finds dates of birth", () => {
    const r = scanText("DOB: 12/03/1988");
    expect(r.findings.some((f) => f.kind === "date_of_birth")).toBe(true);
  });
});

describe("does not block legitimate marketing copy", () => {
  const copy = [
    "Save 50% on orders over $100",
    "Join 1,000,000 happy customers",
    "Our 2024 report is out now",
    "Rated 4.9/5 by 12,483 reviewers",
    "Limited time: 25% off everything",
    "The #1 tool for growth teams in 2025",
    "Free shipping on orders above 75 EUR",
    "We grew revenue 300% in 18 months",
    "Sale ends 31/12/2025",
    "Version 2.10.4 is now available",
  ];

  for (const text of copy) {
    it(`allows: ${text}`, () => {
      expect(scanText(text).clean).toBe(true);
    });
  }

  it("does not treat a 16-digit non-card number as a card", () => {
    // Fails Luhn. An impression count, not a payment instrument.
    expect(scanText("1234567812345678 impressions").clean).toBe(true);
  });
});

describe("row scanning", () => {
  it("reports row and column of each problem", () => {
    const rows = [
      { copy: "Buy now", impressions: "1000" },
      { copy: "Email us at hi@brand.com", impressions: "2000" },
    ];
    const r = scanRows(rows);
    expect(r.clean).toBe(false);
    expect(r.problems[0].row).toBe(2);
    expect(r.problems[0].column).toBe("copy");
  });

  it("ignores non-string cells", () => {
    const rows = [{ copy: "Buy now", impressions: 1000, ctr: 0.012 }];
    expect(scanRows(rows).clean).toBe(true);
  });

  it("finds every occurrence, not just the first", () => {
    const r = scanText("a@b.com and c@d.com");
    expect(r.findings.filter((f) => f.kind === "email")).toHaveLength(2);
  });
});

describe("rejection at the ingest boundary", () => {
  it("throws PiiRejectedError", () => {
    const rows = [{ copy: "reach me at x@y.com" }];
    expect(() => assertNoPii(rows)).toThrow(PiiRejectedError);
  });

  it("passes clean data through", () => {
    expect(() => assertNoPii([{ copy: "Save big today" }])).not.toThrow();
  });

  it("never puts the detected value in the error message", () => {
    const secret = "leaked.person@example.com";
    try {
      assertNoPii([{ copy: `contact ${secret}` }]);
      throw new Error("should have thrown");
    } catch (e) {
      // The whole point of the module: the error is safe to log.
      expect((e as Error).message).not.toContain(secret);
      expect((e as Error).message).toContain("email");
    }
  });
});
