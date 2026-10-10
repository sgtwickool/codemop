// From gregkemp.dev (github.com/sgtwickool/kempgt.com, src/lib/art/build.ts), so CodeMop's
// site prints like the CodeMop card there. Change both together.
// Shorthands for putting a print together.
import type { Label, Layer, Motion, Print } from "./types";

export const small = (layers: Layer[], labels?: Label[]): Print => ({ width: 200, height: 140, layers, labels });
export const large = (layers: Layer[], labels?: Label[]): Print => ({ width: 520, height: 340, layers, labels });

export const draw = (delay: number, duration: number): Motion => ({ kind: "draw", delay, duration });
export const fade = (delay: number, duration = 0.4): Motion => ({ kind: "fade", delay, duration });
export const stamp = (delay: number, duration = 0.3): Motion => ({ kind: "stamp", delay, duration });
export const slide = (delay: number, duration = 0.4): Motion => ({ kind: "slide", delay, duration });

export const follow = (along: string, delay: number, duration: number, opts: Partial<Motion> = {}): Motion => ({
  kind: "follow",
  along,
  delay,
  duration,
  ...opts,
});
