"use client";

import { useEffect } from "react";

/**
 * Scroll-entry animation for every `[data-reveal]` element on the page.
 *
 * One IntersectionObserver for the document rather than a component per
 * element, and never a scroll listener — a scroll handler fires hundreds of
 * times a second and forces layout on each one.
 *
 * TWO FAILSAFES, because the hidden state is the default and a decoration that
 * fails must never take the content with it:
 *
 *   1. The hidden styles are scoped to `html[data-reveal-ready]`, set here on
 *      mount. Without JavaScript the attribute is absent and everything renders
 *      visible, as it should.
 *   2. If the observer has not reported a single intersection shortly after
 *      mount, everything is revealed unconditionally. Observed in practice: in
 *      a tab that is not compositing frames, IntersectionObserver never fires
 *      and the entire page stayed at opacity 0. Throttled background tabs and
 *      occluded windows can do the same. A blank page is a far worse outcome
 *      than an animation that does not play.
 */
export function Reveal() {
  useEffect(() => {
    const root = document.documentElement;
    const nodes = () =>
      Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));

    const revealAll = () => nodes().forEach((n) => n.classList.add("is-visible"));

    if (typeof IntersectionObserver === "undefined") {
      revealAll();
      return;
    }

    root.setAttribute("data-reveal-ready", "");

    let observerWorks = false;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            observerWorks = true;
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.05 },
    );

    nodes().forEach((n) => observer.observe(n));

    // Cancelled implicitly by `observerWorks` once a real intersection lands.
    const rescue = window.setTimeout(() => {
      if (!observerWorks) {
        observer.disconnect();
        revealAll();
      }
    }, 1500);

    return () => {
      window.clearTimeout(rescue);
      observer.disconnect();
    };
  }, []);

  return null;
}
