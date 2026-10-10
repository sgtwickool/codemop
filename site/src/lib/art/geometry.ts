// From gregkemp.dev (github.com/sgtwickool/kempgt.com, src/lib/art/geometry.ts), so CodeMop's
// site prints like the CodeMop card there. Change both together.
// Small helpers for writing SVG path data.
import type { Pt } from "./types";

export const TAU = 2 * Math.PI;

/** Round to one decimal place, which keeps the path data small. */
export const num = (v: number) => (Math.round(v * 10) / 10).toString();

export const path = (pts: Pt[], close = false) =>
  `M${pts.map(([x, y]) => `${num(x)} ${num(y)}`).join("L")}${close ? "Z" : ""}`;

export const circle = (cx: number, cy: number, r: number) =>
  `M${num(cx - r)} ${num(cy)}a${num(r)} ${num(r)} 0 1 0 ${num(2 * r)} 0` +
  `a${num(r)} ${num(r)} 0 1 0 ${num(-2 * r)} 0Z`;

export const rect = (x: number, y: number, w: number, h: number) =>
  `M${num(x)} ${num(y)}h${num(w)}v${num(h)}h${num(-w)}Z`;

/** n + 1 points from fn(0) to fn(1). */
export const sample = (n: number, fn: (u: number) => Pt) => Array.from({ length: n + 1 }, (_, i) => fn(i / n));

/** How far along a polyline (0 to 1) each of its points is reached. */
export function arcFractions(pts: Pt[]) {
  const cum = [0];
  for (let i = 1; i < pts.length; i++) {
    cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  }
  const total = cum[cum.length - 1] || 1;
  return cum.map((c) => c / total);
}

/** An arrowhead at `tip`, pointing along the unit vector (ux, uy). */
export function arrowhead([x, y]: Pt, ux: number, uy: number, length = 4, spread = 3) {
  const [hx, hy] = [-uy, ux];
  return path([
    [x - length * ux + spread * hx, y - length * uy + spread * hy],
    [x, y],
    [x - length * ux - spread * hx, y - length * uy - spread * hy],
  ]);
}
