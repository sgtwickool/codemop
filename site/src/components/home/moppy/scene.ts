// Moppy, CodeMop's mascot, in the home page's hero: a fretful mop who can't leave a mess alone,
// beside a wet-floor sign and its puddle. As HTML, because that's how Starlight's hero takes its
// image (`hero.image.html`), and so his styles and script load on the home page only: a button
// around the SVG, which plays his routine again.
//
// The scene is drawn as it is once he's tidied up, which is all that reduced motion shows. How
// he moves is in moppy.css, and when, in play.ts: the class on the <svg> is the routine playing
// (m-intro as the page loads, m-tidy when a drip lands later). His colours are the theme's that
// stay the same in both themes (--night, --yellow and --water in theme.css); the handle, floor
// and speed lines follow the theme, so they show on a dark page.

const INK = "#16181D";
const YELLOW = "#FFC800";
const WATER = "#BFE9F4";

// Moppy's strands, in two sets so the outer ones trail the inner ones
const OUTER = "M-18 -42 C-27 -30 -21 -18 -36 0 M19 -42 C29 -30 25 -18 38 -2";
const INNER = "M-8 -44 C-13 -30 -7 -16 -15 2 M2 -44 C4 -30 -1 -16 4 3 M11 -44 C16 -30 12 -16 22 2";
const strands = (d: string, outer = false) => `
  <g class="m-strands${outer ? " m-strands-outer" : ""}">
    <path d="${d}" stroke="${INK}" stroke-width="8" stroke-linecap="round" fill="none"/>
    <path d="${d}" stroke="#ffffff" stroke-width="5" stroke-linecap="round" fill="none"/>
  </g>`;

const sparkle = (x: number, y: number, r: number, fill: string, cls = "m-spark") => {
  const a = r / 10;
  const d = `M0 ${-r} C${a} ${-4 * a} ${4 * a} ${-a} ${r} 0 C${4 * a} ${a} ${a} ${4 * a} 0 ${r} ` +
    `C${-a} ${4 * a} ${-4 * a} ${a} ${-r} 0 C${-4 * a} ${-a} ${-a} ${-4 * a} 0 ${-r} Z`;
  return `<g transform="translate(${x} ${y})"><g class="${cls}"><path d="${d}" fill="${fill}" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/></g></g>`;
};

const drop = (x: number, y: number, size: number, cls: string) => {
  const s = size / 4.5;
  const d = `M0 ${-7 * s} C${2.5 * s} ${-3 * s} ${4.5 * s} ${-0.5 * s} ${4.5 * s} ${2 * s} ` +
    `A${4.5 * s} ${4.5 * s} 0 0 1 ${-4.5 * s} ${2 * s} C${-4.5 * s} ${-0.5 * s} ${-2.5 * s} ${-3 * s} 0 ${-7 * s} Z`;
  return `<g transform="translate(${x} ${y})"><path class="${cls}" d="${d}" fill="${WATER}" stroke="${INK}" stroke-width="1.6"/></g>`;
};

// The wet-floor sign: an A-frame, its back panel hinged at the same top edge with its foot
// further back, standing on (0, 0)
const SIGN_FRONT = "M-26 -250 H26 Q38 -250 40 -238 L95 -8 Q97 0 88 0 H-88 Q-97 0 -95 -8 L-40 -238 Q-38 -250 -26 -250 Z";
const SIGN_BACK = "M-26 -250 H26 Q38 -250 40 -238 L117 -18 Q119 -10 110 -10 H-66 Q-75 -10 -73 -18 L-40 -238 Q-38 -250 -26 -250 Z";
const sign = `
  <g transform="translate(200 422)">
    <ellipse cx="8" cy="2" rx="112" ry="6" fill="${INK}" opacity=".1"/>
    <g class="m-sign">
      <path d="${SIGN_BACK}" fill="#E0A400" stroke="${INK}" stroke-width="2.5" stroke-linejoin="round"/>
      <rect x="96" y="-13" width="22" height="6" rx="3" fill="${INK}"/>
      <path d="${SIGN_FRONT}" fill="${YELLOW}" stroke="${INK}" stroke-width="2.5" stroke-linejoin="round"/>
      <rect x="-98" y="-4" width="24" height="6" rx="3" fill="${INK}"/>
      <rect x="72" y="-4" width="24" height="6" rx="3" fill="${INK}"/>
      <rect x="-17" y="-240" width="34" height="11" rx="5.5" fill="#ffffff" stroke="${INK}" stroke-width="2.5"/>
      <path d="M0 -205 L54 -112 H-54 Z" fill="#ffffff" stroke="${INK}" stroke-width="6" stroke-linejoin="round"/>
      <g transform="translate(0 -121) scale(0.42)" fill="${INK}">
        <path d="M0 -80 L6 -146" stroke="${INK}" stroke-width="8" stroke-linecap="round"/>
        <rect x="-15" y="-84" width="30" height="9" rx="3"/>
        <rect x="-24" y="-77" width="48" height="35" rx="15"/>
        <ellipse cx="-8" cy="-61" rx="6" ry="7" fill="#ffffff"/>
        <ellipse cx="8" cy="-61" rx="6" ry="7" fill="#ffffff"/>
        <circle cx="-6" cy="-59" r="3"/>
        <circle cx="10" cy="-59" r="3"/>
        <path d="M-16 -42 C-22 -30 -18 -20 -28 -6 M-6 -42 C-9 -30 -4 -18 -9 -4 M6 -42 C9 -30 4 -18 9 -4 M16 -42 C22 -30 18 -20 28 -6" stroke="${INK}" stroke-width="8" stroke-linecap="round" fill="none"/>
      </g>
      <text x="0" y="-68" text-anchor="middle" class="m-sign-text" font-weight="800" font-size="32" letter-spacing="1.5">CAUTION</text>
      <text x="0" y="-44" text-anchor="middle" class="m-sign-text" font-weight="700" font-size="14.5" letter-spacing="0.6">FIXES BEING COMMITTED</text>
    </g>
  </g>`;

// Moppy himself, standing on (0, 0), each nested group one part of how he moves
const moppy = `
  <g transform="translate(404 428) scale(1.9)">
    <g class="m-move">
      <ellipse cx="0" cy="1" rx="36" ry="3.4" fill="${INK}" opacity=".12"/>
      <g class="m-hop"><g class="m-scrub"><g class="m-squash"><g class="m-breathe">
        <g transform="rotate(-8)">
          <path class="m-handle" d="M0 -80 L8 -160" stroke-width="4" stroke-linecap="round"/>
          <circle cx="8.4" cy="-163" r="3.6" fill="${YELLOW}" stroke="${INK}" stroke-width="1.4"/>
          ${strands(OUTER, true)}
          ${strands(INNER)}
          <rect x="-16" y="-85" width="32" height="9" rx="3" fill="#1592B0" stroke="${INK}" stroke-width="1.4"/>
          <rect x="-24" y="-78" width="48" height="36" rx="16" fill="${YELLOW}" stroke="${INK}" stroke-width="1.4"/>
          <ellipse cx="-15" cy="-54" rx="4" ry="2.4" fill="#FF9AAE"/>
          <ellipse cx="15" cy="-54" rx="4" ry="2.4" fill="#FF9AAE"/>
          <g class="m-eyes">
            <ellipse cx="-8" cy="-63" rx="5" ry="6" fill="#ffffff" stroke="${INK}" stroke-width="1.3"/>
            <ellipse cx="8" cy="-63" rx="5" ry="6" fill="#ffffff" stroke="${INK}" stroke-width="1.3"/>
            <g class="m-pupils">
              <circle cx="-9" cy="-61.6" r="2.5" fill="${INK}"/>
              <circle cx="7" cy="-61.6" r="2.5" fill="${INK}"/>
            </g>
          </g>
          <g class="m-worried">
            <path d="M-15 -72 L-5 -75.5 M5 -75.5 L15 -72" stroke="${INK}" stroke-width="1.6" stroke-linecap="round"/>
            <path d="M-5 -51 q2.5 -2.5 5 0 q2.5 2.5 5 0" stroke="${INK}" stroke-width="1.4" fill="none" stroke-linecap="round"/>
            <path d="M-28 -76 C-25 -70 -23 -67 -26 -64 C-29 -61 -33 -65 -31 -69 Z" fill="${WATER}" stroke="${INK}" stroke-width="1.3"/>
          </g>
          <g class="m-smile">
            <path d="M-14 -73 q4.5 -3 9 0 M5 -73 q4.5 -3 9 0" stroke="${INK}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
            <path d="M-5 -53 q5 4 10 0" stroke="${INK}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
          </g>
        </g>
      </g></g></g></g>
    </g>
  </g>`;

const svg = `
<svg class="mascot m-intro m-hold" viewBox="0 76 560 404" role="img"
  aria-label="Moppy, CodeMop's mascot, a worried little mop, hops in, mops up a puddle beside a wet-floor sign that reads Caution: fixes being committed, knocks the tipping sign straight with his handle and hops for joy">
  <path class="m-floor" d="M40 430 H540" stroke-width="3" stroke-linecap="round"/>
  <g class="m-puddle">
    <path d="M132 428 C120 408 190 402 240 405 C300 398 380 400 440 406 C500 406 516 424 494 436 C468 450 390 446 330 449 C250 454 150 452 132 428 Z" fill="${WATER}" stroke="${INK}" stroke-width="2.5"/>
    <path d="M164 438 q30 6 70 4 M384 418 q28 -3 48 2" stroke="#ffffff" stroke-width="3.5" stroke-linecap="round" fill="none"/>
  </g>
  <ellipse class="m-mini" cx="334" cy="434" rx="26" ry="6" fill="${WATER}" stroke="${INK}" stroke-width="2"/>
  ${sign}
  <g class="m-bubbles" fill="#ffffff" stroke="${INK}" stroke-width="2">
    <circle cx="508" cy="262" r="14"/><circle cx="530" cy="222" r="7"/><circle cx="72" cy="318" r="10"/><circle cx="96" cy="282" r="5"/>
    <path d="M500 257 q3 -5 8 -6 M66 313 q2 -4 6 -4.5" fill="none" stroke-linecap="round"/>
  </g>
  <path class="m-speed" d="M500 300 h34 M490 336 h50 M504 372 h30" stroke-width="2.5" stroke-linecap="round"/>
  <g class="m-puff" fill="#ffffff" stroke="${INK}" stroke-width="2"><circle cx="330" cy="422" r="7"/><circle cx="318" cy="412" r="4"/></g>
  <g class="m-puff" fill="#ffffff" stroke="${INK}" stroke-width="2"><circle cx="480" cy="422" r="7"/><circle cx="492" cy="412" r="4"/></g>
  ${drop(356, 420, 4.5, "m-drop m-drop-a")}
  ${drop(456, 420, 4.5, "m-drop m-drop-b")}
  ${drop(372, 424, 3.2, "m-drop m-drop-c")}
  ${drop(334, 430, 5, "m-drip")}
  ${moppy}
  ${sparkle(302, 458, 16, YELLOW)}
  ${sparkle(498, 450, 10, "#ffffff", "m-spark m-spark-late")}
  ${sparkle(150, 446, 7, WATER, "m-spark m-spark-late")}
  ${sparkle(334, 432, 9, YELLOW, "m-mini-spark")}
</svg>`;

export const moppyHtml = `
<button type="button" class="mascot-replay" aria-label="Watch Moppy tidy up again">${svg}</button>`;
