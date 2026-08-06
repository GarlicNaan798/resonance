import { describe, expect, it } from "vitest";
import { checkSurface, guardRanking } from "./guardrails";

describe("shouting detection", () => {
  it("flags all-caps copy", () => {
    const r = checkSurface("URGENT SLASH YOUR BILLS TODAY");
    expect(r.risks.some((x) => x.kind === "shouting")).toBe(true);
    expect(r.rankerBlind).toBe(true);
  });

  it("does not flag ordinary sentence case", () => {
    const r = checkSurface("Cut your heating bill with one simple change");
    expect(r.risks.some((x) => x.kind === "shouting")).toBe(false);
  });

  it("does not flag Title Case, which is normal in headlines", () => {
    const r = checkSurface("Cut Your Heating Bill With One Simple Change");
    expect(r.risks.some((x) => x.kind === "shouting")).toBe(false);
  });

  it("ignores short copy where caps ratio is unstable", () => {
    // "OK" is 100% capitals but says nothing about tone.
    expect(checkSurface("OK").risks).toHaveLength(0);
  });

  it("explains that the ranker cannot see capitals", () => {
    const r = checkSurface("BUY NOW BEFORE IT IS TOO LATE");
    const shouting = r.risks.find((x) => x.kind === "shouting");
    expect(shouting?.message).toMatch(/cannot see capitalisation/);
    expect(shouting?.evidence).toMatch(/cosine 1\.000000/);
  });
});

describe("exclamation detection", () => {
  it("flags dense exclamation marks", () => {
    const r = checkSurface("Act now!!! Save big!!! Do not miss out!!!");
    expect(r.risks.some((x) => x.kind === "exclamation")).toBe(true);
  });

  it("allows a single exclamation mark", () => {
    const r = checkSurface(
      "Save on your energy bill this winter with our simple guide!",
    );
    expect(r.risks.some((x) => x.kind === "exclamation")).toBe(false);
  });

  it("cites the measured evidence rather than asserting a rule", () => {
    const r = checkSurface("Buy!!! Now!!! Today!!!");
    const ex = r.risks.find((x) => x.kind === "exclamation");
    expect(ex?.evidence).toMatch(/0\.5698/);
  });
});

describe("severity", () => {
  it("scales with how extreme the copy is", () => {
    const mild = checkSurface("Save Money On Your BILLS Today Right Now");
    const extreme = checkSurface("SAVE MONEY ON YOUR BILLS TODAY RIGHT NOW");
    expect(extreme.maxSeverity).toBeGreaterThan(mild.maxSeverity);
  });

  it("is zero for clean copy", () => {
    expect(checkSurface("A clear and simple offer for your home").maxSeverity)
      .toBe(0);
  });

  it("stays within 0-1", () => {
    for (const t of ["!!!!!!!!!!", "AAAAAAAAAA BBBBBBB CCCCCCC", "normal copy here"]) {
      const r = checkSurface(t);
      expect(r.maxSeverity).toBeGreaterThanOrEqual(0);
      expect(r.maxSeverity).toBeLessThanOrEqual(1);
    }
  });
});

describe("guardRanking", () => {
  const calm = { text: "Cut your heating bill with one simple change" };
  const shouty = { text: "URGENT!!! SLASH YOUR BILLS TODAY!!! DON'T MISS OUT!!!" };

  it("cautions when the top-ranked variant is the riskiest", () => {
    const { caution } = guardRanking([shouty, calm]);
    expect(caution).toMatch(/top-ranked variant carries the most surface risk/);
  });

  it("stays silent when the top-ranked variant is clean", () => {
    const { caution } = guardRanking([calm, shouty]);
    expect(caution).toBeNull();
  });

  it("never reorders the ranking", () => {
    // Overriding a model invisibly is worse than surfacing the disagreement.
    const { guarded } = guardRanking([shouty, calm]);
    expect(guarded[0].item).toBe(shouty);
    expect(guarded[1].item).toBe(calm);
  });

  it("attaches a report to every variant", () => {
    const { guarded } = guardRanking([calm, shouty]);
    expect(guarded).toHaveLength(2);
    for (const g of guarded) expect(g.guardrail).toBeDefined();
  });

  it("handles an empty ranking", () => {
    const { guarded, caution } = guardRanking([]);
    expect(guarded).toHaveLength(0);
    expect(caution).toBeNull();
  });

  it("reproduces the real failure this was built for", () => {
    // The exact case that exposed the problem: the ranker put the shouty
    // variant first, and nothing in the product said why that might be wrong.
    const { caution } = guardRanking([shouty, calm]);
    expect(caution).toContain("cannot");
    expect(caution).toContain("caution");
  });
});
