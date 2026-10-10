// CodeMop's mascot: a fretful mop who can't leave a mess alone. The home page's hero, as SVG
// markup (Starlight's hero takes its image as HTML). How he moves is in
// src/styles/mascot.css, and when, in src/scripts/mascot.ts: the class on the <svg> is his state.
//
// He's drawn in the prints' inks and with their rough edge and grain (PrintFilters.astro),
// standing on the floor at (0, 0) of his own coordinates. Each string has a --lag, so the
// outer ones trail the inner ones when he moves.

const strands = [
  { d: "M-18 -42 C-26 -34 -20 -26 -27 -18 C-33 -11 -30 -3 -36 -1", lag: 90 },
  { d: "M-11 -44 C-16 -35 -10 -27 -15 -18 C-19 -11 -15 -4 -20 0", lag: 55 },
  { d: "M-4 -45 C-7 -36 -1 -28 -5 -19 C-8 -11 -3 -5 -6 1", lag: 20 },
  { d: "M4 -45 C7 -36 1 -28 5 -19 C8 -11 3 -5 6 1", lag: 20 },
  { d: "M11 -44 C16 -35 10 -27 15 -18 C19 -11 15 -4 20 0", lag: 55 },
  { d: "M18 -42 C26 -34 20 -26 27 -18 C33 -11 30 -3 36 -1", lag: 90 },
];

const spark = "M224 30 L226.5 37.5 L234 40 L226.5 42.5 L224 50 L221.5 42.5 L214 40 L221.5 37.5 Z";

export const mascotSvg = `
<svg class="mascot m-intro" viewBox="0 0 240 210" role="img"
  aria-label="CodeMop's mascot, a worried little mop, rushes in, mops up the dirt on the floor, taps a crooked picture straight with its handle, and hurries off to look for more mess">
  <rect class="m-plate" width="240" height="210" rx="3"/>
  <g filter="url(#rough)">
    <path class="m-floor" d="M18 181 H222"/>
    <path class="m-line m-thin" d="M196 46 L182 58 M196 46 L210 58"/>
    <g class="m-frame">
      <rect class="m-frame-box" x="180" y="58" width="32" height="32" rx="2"/>
      <circle class="m-pink m-ink" cx="204" cy="67" r="4.5"/>
      <path class="m-yellow m-ink" d="M183 87 L192 74 L199 82 L204 77 L209 87 Z"/>
    </g>
    <circle class="m-blue" cx="196" cy="46" r="2.2"/>
    <g class="m-dirt1">
      <circle class="m-pink m-ink" cx="64" cy="177" r="4"/>
      <circle class="m-pink m-ink" cx="71" cy="179" r="2"/>
      <circle class="m-pink m-ink" cx="58" cy="179" r="1.6"/>
    </g>
    <g class="m-dirt2">
      <circle class="m-pink m-ink" cx="100" cy="174" r="6"/>
      <path class="m-fuzz" d="M92 170 l-3 -2 M95 166 l-1 -3 M101 165 l0 -3 M106 167 l2 -2 M108 172 l3 0 M107 178 l3 1 M93 178 l-3 1"/>
    </g>
    <g class="m-dirt3"><ellipse class="m-pink m-ink" cx="130" cy="179" rx="9" ry="2.6"/></g>
    <g class="m-dirt4">
      <circle class="m-pink m-ink" cx="92" cy="178" r="3"/>
      <circle class="m-pink m-ink" cx="98" cy="179" r="1.6"/>
    </g>
    <g class="m-spark"><path class="m-yellow m-ink" d="${spark}"/><path class="m-line m-thin" d="${spark}"/></g>
    <g class="m-move">
      <path class="m-speed-r m-line m-thin" d="M-52 -60 H-74 M-60 -36 H-86 M-58 -14 H-76 M-6 -130 H-26"/>
      <path class="m-speed-l m-line m-thin" d="M52 -60 H74 M60 -36 H86 M58 -14 H76 M18 -130 H38"/>
      <g class="m-puff-r">
        <circle class="m-yellow m-ink" cx="38" cy="-4" r="5"/>
        <circle class="m-yellow m-ink" cx="47" cy="-10" r="3.5"/>
        <circle class="m-yellow m-ink" cx="32" cy="-11" r="3"/>
      </g>
      <g class="m-puff-l">
        <circle class="m-yellow m-ink" cx="-38" cy="-4" r="5"/>
        <circle class="m-yellow m-ink" cx="-47" cy="-10" r="3.5"/>
        <circle class="m-yellow m-ink" cx="-32" cy="-11" r="3"/>
      </g>
      <g class="m-hop">
        <g class="m-squash">
          <path class="m-handle" d="M0 -80 L6 -160"/>
          <circle class="m-line m-thin" cx="6.3" cy="-164" r="3.5"/>
          ${strands.map((s) => `<path class="m-strand" style="--lag:${s.lag}ms" d="${s.d}"/>`).join("")}
          <path class="m-strand m-edge" style="--lag:55ms" d="M-9 -43 C-14 -34 -8 -26 -13 -17 M6 -44 C9 -35 3 -27 7 -18 M20 -41 C28 -33 22 -25 29 -17"/>
          <rect class="m-blue m-ink" x="-15" y="-82" width="30" height="8" rx="3"/>
          <g class="m-head">
            <rect class="m-yellow m-ink" x="-23" y="-76" width="46" height="34" rx="15"/>
            <ellipse class="m-pink m-ink" cx="-15" cy="-54" rx="4" ry="2.4"/>
            <ellipse class="m-pink m-ink" cx="15" cy="-54" rx="4" ry="2.4"/>
            <g class="m-eyes">
              <ellipse class="m-eye" cx="-8" cy="-63" rx="5" ry="6"/>
              <ellipse class="m-eye" cx="8" cy="-63" rx="5" ry="6"/>
              <g class="m-pupils">
                <circle class="m-blue" cx="-8" cy="-63" r="2.4"/>
                <circle class="m-blue" cx="8" cy="-63" r="2.4"/>
                <circle class="m-glint" cx="-7" cy="-64" r=".8"/>
                <circle class="m-glint" cx="9" cy="-64" r=".8"/>
              </g>
            </g>
            <g class="m-worried">
              <path class="m-line" d="M-15 -72 L-5 -75.5 M5 -75.5 L15 -72"/>
              <path class="m-line m-thin" d="M-5 -52 q2.5 -2.5 5 0 q2.5 2.5 5 0"/>
            </g>
            <g class="m-shocked">
              <path class="m-line" d="M-16 -75 q5 -5 10 -2.5 M6 -77.5 q5 -2.5 10 2.5"/>
              <ellipse class="m-eye" cx="0" cy="-51" rx="3" ry="3.8"/>
            </g>
            <g class="m-smile">
              <path class="m-line" d="M-14 -73 q4.5 -3 9 0 M5 -73 q4.5 -3 9 0"/>
              <path class="m-line m-thin" d="M-5 -54 q5 4 10 0"/>
            </g>
            <path class="m-sweat m-blue m-ink" d="M-28 -76 C-25 -70 -23 -67 -26 -64 C-29 -61 -33 -65 -31 -69 Z"/>
          </g>
        </g>
      </g>
    </g>
  </g>
  <rect class="grain" width="240" height="210"/>
</svg>`;
