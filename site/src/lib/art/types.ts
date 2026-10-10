// From gregkemp.dev (github.com/sgtwickool/kempgt.com, src/lib/art/types.ts), so CodeMop's
// site prints like the CodeMop card there. Change both together.
export type Pt = [number, number];

/**
 * The three risograph inks, plus "paper", which paints in the background
 * colour to wipe out whatever is beneath it.
 */
export type Ink = "line" | "strong" | "glow" | "paper";

export interface Motion {
  /**
   * One-off motions play out as the print scrolls from the bottom of the
   * screen to just above the middle, timed by delay and duration (relative
   * units; each print's timeline is scaled to fit):
   *   draw    the stroke draws itself in
   *   fade    the layer fades in
   *   slide   the layer slides in from the left
   *   stamp   the layer lands like a rubber stamp
   *   follow  the layer (drawn around 0,0) travels along `along`
   *
   * Loops repeat as the print is scrolled past, `cycles` times per screen of
   * scroll: vibrate, blink. Give one a delay and it waits until then and
   * builds up over its duration (a plucked string, a cursor once typing stops).
   */
  kind: "draw" | "fade" | "slide" | "stamp" | "follow" | "vibrate" | "blink";
  delay?: number;
  duration?: number;
  /** Loops: repeats per screen of scroll. */
  cycles?: number;
  /** vibrate: the line to vibrate about, in viewBox units. */
  origin?: Pt;
  /** follow: the path to travel along. */
  along?: string;
  /** follow: face the direction of travel. */
  turn?: boolean;
  /** follow: disappear on arrival (absorbed into whatever it reached). */
  vanish?: boolean;
}

export interface Layer {
  d: string;
  ink: Ink;
  /** Stroke width in viewBox units. Omit for a filled shape. */
  width?: number;
  round?: boolean;
  /** Fill the shape with the background colour as well as stroking it. */
  knockout?: boolean;
  motion?: Motion;
  /** Turn with the scroll as well, so a layer can draw in and spin. */
  spin?: { origin: Pt; cycles: number; reverse?: boolean };
}

export interface Label {
  x: number;
  y: number;
  text: string;
  size: number;
  weight?: number;
  anchor?: "start" | "middle" | "end";
  tone?: "ink" | "muted" | "strong";
  /** Set in the serif italic, for maths and physics symbols. */
  symbol?: boolean;
  motion?: Motion;
}

export interface Print {
  width: number;
  height: number;
  layers: Layer[];
  labels?: Label[];
}
