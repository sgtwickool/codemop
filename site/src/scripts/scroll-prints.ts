// From gregkemp.dev (src/scripts/scroll-prints.ts). Change both together.
// Drives the prints' motion from the scroll position (see src/lib/art/style.ts).
// For each print it sets --p, its progress (0 as it enters at the bottom of
// the screen, 1 once its middle is 45% of the way down), and --t, screens
// travelled since it entered, frozen once it's left the top so the loops
// stop off screen.

let unbind: AbortController | undefined;

export function bindScrollPrints() {
  unbind?.abort();
  // "motion" is set in BaseLayout unless the visitor prefers reduced motion.
  if (!document.documentElement.classList.contains("motion")) return;
  const prints = Array.from(document.querySelectorAll<SVGSVGElement>(".print[data-animate]"));
  if (!prints.length) return;
  unbind = new AbortController();

  const last = new WeakMap<Element, string>();
  let frame = 0;

  const update = () => {
    frame = 0;
    const vh = window.innerHeight;
    for (const print of prints) {
      const { top, height } = print.getBoundingClientRect();
      const p = Math.min(1, Math.max(0, (vh - top) / (0.55 * vh + height / 2)));
      const t = Math.min(Math.max((vh - top) / vh, 0), (vh + height) / vh);
      const value = `${p.toFixed(4)} ${t.toFixed(4)}`;
      if (last.get(print) === value) continue;
      last.set(print, value);
      print.style.setProperty("--p", p.toFixed(4));
      print.style.setProperty("--t", t.toFixed(4));
    }
  };
  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(update);
  };

  window.addEventListener("scroll", schedule, { passive: true, signal: unbind.signal });
  window.addEventListener("resize", schedule, { signal: unbind.signal });
  update();
}
