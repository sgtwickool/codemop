// From gregkemp.dev (github.com/sgtwickool/kempgt.com, src/lib/art/style.ts), so CodeMop's
// site prints like the CodeMop card there. Change both together.
// Turns a print's layers and labels into inline CSS.
//
// Every motion is a function of two variables the scroll script sets on each
// print (see src/scripts/scroll-prints.ts): --p, its progress (0 as it enters
// at the bottom of the screen, 1 once it's just above the middle), and --t,
// how many screens it's travelled, which drives the loops. So scrolling back
// rewinds everything. Without the script, or with reduced motion, they fall
// back to 1 and 0: the finished, still print.
import type { Label, Layer, Motion, Print } from "./types";

const inks = {
  line: "var(--ink-line)",
  strong: "var(--ink-strong)",
  glow: "var(--ink-glow)",
  paper: "var(--print-bg)",
};

const tones = {
  ink: "var(--ink)",
  muted: "var(--muted)",
  strong: "var(--ink-strong)",
};

const oneOff = new Set<Motion["kind"]>(["draw", "fade", "slide", "stamp", "follow"]);

const css = (rules: (string | false | undefined)[]) => rules.filter(Boolean).join(";");

export function printStyles({ layers, labels = [] }: Print) {
  // One-off motions, and loops that wait for their moment, share the print's
  // timeline, which is scaled so the last of them finishes at --p = 1.
  const motions = [...layers, ...labels].flatMap((item) => (item.motion ? [item.motion] : []));
  const timed = (m: Motion) => oneOff.has(m.kind) || m.delay !== undefined;
  const timeline = Math.max(1, ...motions.filter(timed).map((m) => (m.delay ?? 0) + (m.duration ?? 1)));

  /** Sets --k: how far through its own slice of the timeline a motion is (0 to 1). */
  const progress = (m: Motion) => {
    const start = +((m.delay ?? 0) / timeline).toFixed(4);
    const span = +((m.duration ?? 1) / timeline).toFixed(4);
    return `--k:clamp(0, calc((var(--p, 1) - ${start}) / ${span}), 1)`;
  };

  function motion(m?: Motion): string[] {
    if (!m) return [];
    const phase = `calc(var(--t, 0) * ${m.cycles ?? 1} * 360deg)`;
    switch (m.kind) {
      case "draw":
        // Hidden until it starts, or a round line cap shows as a stray dot.
        return [
          progress(m),
          "stroke-dasharray:1",
          "stroke-dashoffset:calc(1 - var(--k))",
          "opacity:clamp(0, calc(var(--k) * 50), 1)",
        ];
      case "fade":
        return [progress(m), "opacity:var(--k)"];
      case "slide":
        return [progress(m), "opacity:var(--k)", "transform:translateX(calc((1 - var(--k)) * -12px))"];
      case "stamp":
        return [
          progress(m),
          "opacity:var(--k)",
          "transform-box:fill-box",
          "transform-origin:center",
          "transform:scale(calc(1 + (1 - var(--k)) * 0.7)) rotate(calc((1 - var(--k)) * -14deg))",
        ];
      case "follow":
        // The layer is drawn around 0,0 and carried along the path.
        return [
          progress(m),
          `offset-path:path('${m.along}')`,
          "offset-distance:calc(var(--k) * 100%)",
          `offset-rotate:${m.turn ? "auto" : "0deg"}`,
          "offset-anchor:0 0",
          "transform-box:view-box",
          "transform-origin:0 0",
          m.vanish
            ? "opacity:clamp(0, calc(min(var(--k), 1 - var(--k)) * 25), 1)"
            : "opacity:clamp(0, calc(var(--k) * 25), 1)",
        ];
      case "vibrate": {
        const origin = m.origin && `transform-origin:${m.origin[0]}px ${m.origin[1]}px`;
        return m.delay === undefined
          ? [origin || "", `transform:scaleY(cos(${phase}))`]
          : [progress(m), origin || "", `transform:scaleY(calc(cos(${phase}) * var(--k)))`];
      }
      case "blink":
        return m.delay === undefined
          ? [`opacity:calc(0.62 + 0.38 * cos(${phase}))`]
          : [progress(m), `opacity:calc((0.62 + 0.38 * cos(${phase})) * var(--k))`];
    }
  }

  return {
    animated: motions.length > 0 || layers.some((layer) => layer.spin),

    layer: (layer: Layer) =>
      css([
        ...(layer.width
          ? [
              `fill:${layer.knockout ? "var(--print-bg)" : "none"}`,
              `stroke:${inks[layer.ink]}`,
              `stroke-width:${layer.width}`,
              "stroke-linejoin:round",
              layer.round && "stroke-linecap:round",
            ]
          : [`fill:${inks[layer.ink]}`]),
        ...motion(layer.motion),
      ]),

    spin: ({ origin, cycles, reverse }: NonNullable<Layer["spin"]>) =>
      css([
        `transform-origin:${origin[0]}px ${origin[1]}px`,
        `transform:rotate(calc(var(--t, 0) * ${reverse ? -cycles : cycles} * 360deg))`,
      ]),

    label: (label: Label) =>
      css([
        `fill:${tones[label.tone ?? "ink"]}`,
        `font-size:${label.size}px`,
        `font-weight:${label.weight ?? 500}`,
        label.symbol && "font-family:var(--font-serif);font-style:italic",
        ...motion(label.motion),
      ]),
  };
}
