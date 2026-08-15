"use client";

import { useEffect } from "react";

/**
 * Scroll-entry animation for every `[data-reveal]` element on the page.
 *
 * One IntersectionObserver for the document rather than a component per
 * element, and never a scroll listener. A scroll handler fires hundreds of
 * times a second and forces layout on each one.
 *
 * TWO FAILSAFES, because the hidden state is the default and a decoration that
 * fails must never take the content with it:
 *
 *   1. The hidden styles are scoped to `html[data-reveal-ready]`, set here on
 *      mount. Without JavaScript the attribute is absent and everything renders
 *      visible, as it should.
 *   2. A hard deadline. Everything still hidden after DEADLINE_MS is revealed,
 *      whatever the observer is doing.
 *
 * The deadline used to be cancelled as soon as the observer reported its first
 * intersection, on the theory that a working observer needs no backstop. That
 * was wrong, and a full-page screenshot showed why: the hero intersected, the
 * backstop was cancelled as "not needed", and the other twelve blocks sat at
 * opacity 0 waiting for a scroll that never came. The real failure mode is not
 * a broken observer. It is a working observer on content nobody scrolls to.
 * Print, PDF export, reader modes and screenshots all hit it.
 *
 * So the deadline is unconditional. Anyone scrolling in the first few seconds
 * gets the animation; everyone else gets the content, which matters more.
 */
/** Long enough for the animation to feel intentional, short enough that a
 *  reader who never scrolls is not staring at blank space. */
const DEADLINE_MS = 2500;

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

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.05 },
    );

    nodes().forEach((n) => observer.observe(n));

    // Unconditional. Not "if the observer looks broken". See the note above.
    const deadline = window.setTimeout(() => {
      observer.disconnect();
      revealAll();
    }, DEADLINE_MS);

    return () => {
      window.clearTimeout(deadline);
      observer.disconnect();
    };
  }, []);

  return null;
}
