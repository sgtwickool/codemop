// Risograph prints, computed at build time, as on gregkemp.dev (src/lib/art there).
//
// Each print is a few layers of SVG path data, each in one of three inks: "line" (fluorescent
// pink), "strong" (blue) or "glow" (yellow). Inks overprint each other (see .ink in
// src/styles/theme.css). Layers can carry a motion, driven by scrolling (see Print.astro), so
// each print tells a small story as it scrolls up the screen and rewinds as it scrolls back.
import { gate, mop, respond } from "./prints/review-loop";
import type { Print } from "./types";

export type * from "./types";

/** Every print, in the order they appear on the home page. */
export const prints = {
  mop: mop(),
  respond: respond(),
  gate: gate(),
} satisfies Record<string, Print>;

export type PrintName = keyof typeof prints;
