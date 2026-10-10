// The review loop, a print for each step. mop() is the CodeMop card's print on gregkemp.dev
// (src/lib/art/prints/side-projects.ts there); respond() and gate() are drawn for this site in
// the same style.
import { draw, fade, follow, small, stamp } from "../build";
import { arcFractions, circle, path, rect } from "../geometry";
import type { Layer, Print, Pt } from "../types";

export function mop(): Print {
  // CodeMop. A pull request diff appears, the mop sweeps back and forth down
  // it and wipes out the removed lines, and the review is approved.
  const diff = [
    { len: 74, added: false },
    { len: 96, added: true },
    { len: 58, added: false },
    { len: 110, added: true },
    { len: 84, added: true },
    { len: 46, added: false },
  ];
  const y = (i: number) => 24 + i * 18;
  const sweep = diff.flatMap((_, i): Pt[] => [
    [36, y(i) - 4],
    [160, y(i) + 4],
  ]);
  const at = arcFractions(sweep);
  const [from, span] = [1.0, 1.7];
  return small([
    ...diff.map((line, i): Layer => ({
      d: `M44 ${y(i)}h${line.len}M18 ${y(i)}h12` + (line.added ? `M24 ${y(i) - 6}v12` : ""),
      ink: line.added ? "strong" : "line",
      width: 6,
      round: true,
      motion: draw(i * 0.12, 0.3),
    })),
    // Removed lines are wiped out by paper-coloured strokes as the mop passes.
    ...diff.flatMap((line, i): Layer[] =>
      line.added
        ? []
        : [
            {
              d: `M12 ${y(i)}H${48 + line.len}`,
              ink: "paper",
              width: 11,
              round: true,
              motion: draw(from + span * at[2 * i], span * (at[2 * i + 1] - at[2 * i])),
            },
          ],
    ),
    {
      d: "M-14 -2Q0 -10 14 -2L12 8Q0 3 -12 8Z",
      ink: "glow",
      motion: follow(path(sweep), from, span, { vanish: true }),
    },
    { d: circle(176, 118, 12), ink: "glow", motion: stamp(from + span + 0.05) },
    { d: "M170 118l4.5 4.5l8.5 -10", ink: "strong", width: 2.6, round: true, motion: draw(from + span + 0.2, 0.25) },
  ]);
}

export function respond(): Print {
  // Responding. Fixes in the summary are ticked one at a time, then "Commit
  // the ticked fixes", and they land on the branch together, as one commit.
  const rows = [
    { y: 26, len: 70, ticked: true },
    { y: 52, len: 52, ticked: false },
    { y: 78, len: 84, ticked: true },
  ];
  const commit = 112;
  const box = (y: number) => rect(16, y - 7, 14, 14);
  const tick = (y: number) => `M19 ${y}l3.5 3.5l6.5 -7.5`;
  const ticks = rows.filter((row) => row.ticked);
  return small([
    // The PR's branch, with the commits already on it.
    { d: "M170 130V12", ink: "line", width: 2, motion: draw(0, 0.4) },
    { d: circle(170, 108, 5) + circle(170, 80, 5), ink: "line", width: 2, knockout: true, motion: stamp(0.3, 0.2) },
    ...rows.map((row, i): Layer => ({ d: box(row.y), ink: "line", width: 1.8, motion: draw(0.1 + i * 0.08, 0.3) })),
    ...rows.map((row, i): Layer => ({
      d: `M42 ${row.y}h${row.len}`,
      ink: "strong",
      width: 5,
      round: true,
      motion: draw(0.15 + i * 0.08, 0.3),
    })),
    ...ticks.map((row, i): Layer => ({
      d: tick(row.y),
      ink: "strong",
      width: 2.4,
      round: true,
      motion: draw(0.7 + i * 0.3, 0.2),
    })),
    // "Commit the ticked fixes"
    { d: box(commit), ink: "glow", motion: stamp(1.3) },
    { d: `M42 ${commit}h62`, ink: "strong", width: 7, round: true, motion: draw(1.2, 0.3) },
    { d: tick(commit), ink: "strong", width: 2.4, round: true, motion: draw(1.45, 0.2) },
    {
      d: circle(0, 0, 4),
      ink: "glow",
      motion: follow(`M112 ${commit}C142 ${commit} 146 44 170 44`, 1.6, 0.5, { vanish: true }),
    },
    { d: circle(170, 44, 10), ink: "glow", motion: stamp(2.1) },
    { d: circle(170, 44, 5), ink: "strong", width: 2.4, knockout: true, motion: stamp(2.15, 0.2) },
  ]);
}

export function gate(): Print {
  // The merge check. It fails while a bug is open, passes once it's fixed,
  // and the branch merges.
  const branch = "M30 112C50 112 50 64 80 64H124";
  const merge = "M124 64C150 64 150 112 172 112";
  return small([
    { d: "M12 112H188", ink: "strong", width: 2.4, round: true, motion: draw(0, 0.5) },
    { d: branch, ink: "line", width: 2.4, round: true, motion: draw(0.2, 0.5) },
    { d: circle(86, 64, 5) + circle(114, 64, 5), ink: "line", width: 2, knockout: true, motion: stamp(0.6, 0.2) },
    // A cross while the bug is open...
    { d: circle(100, 28, 13), ink: "line", width: 2, motion: draw(0.7, 0.3) },
    { d: "M94 22l12 12M106 22l-12 12", ink: "line", width: 2.6, round: true, motion: draw(0.9, 0.25) },
    // ...covered over once it's fixed, by a tick.
    { d: circle(100, 28, 17), ink: "paper", motion: fade(1.4, 0.2) },
    { d: circle(100, 28, 13), ink: "glow", motion: stamp(1.6) },
    { d: "M94 28l4.5 4.5l8.5 -10", ink: "strong", width: 2.6, round: true, motion: draw(1.75, 0.25) },
    // Then the branch merges.
    { d: merge, ink: "line", width: 2.4, round: true, motion: draw(2.0, 0.4) },
    { d: circle(172, 112, 9), ink: "glow", motion: stamp(2.4) },
    { d: circle(172, 112, 5), ink: "strong", width: 2.4, knockout: true, motion: stamp(2.45, 0.2) },
  ]);
}
