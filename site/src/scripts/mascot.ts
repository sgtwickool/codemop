// When CodeMop's mascot moves (src/styles/mascot.css says how): his routine once as the page
// loads, then away, peeking back in now and then to look for dirt, only while he's on screen
// and the tab is visible. Clicking him plays the routine again. With reduced motion he stays
// still, and this does nothing.

const PEEKS = ["m-peek-left", "m-peek-right", "m-peek-bottom"];
const STATES = ["m-intro", "m-away", ...PEEKS];
const QUIET = [12_000, 28_000]; // between peeks, at random within this, in ms

export function bindMascot() {
  const svg = document.querySelector<SVGSVGElement>(".mascot");
  const move = svg?.querySelector(".m-move");
  const button = svg?.closest("button");
  if (!svg || !move) return;
  if (!document.documentElement.classList.contains("motion")) {
    if (button) button.disabled = true;
    return;
  }

  let timer = 0;
  let onScreen = true;

  const show = (state: string) => {
    const again = svg.classList.contains(state);
    svg.classList.remove(...STATES);
    if (again) svg.getBoundingClientRect(); // so its animation starts over
    svg.classList.add(state);
  };
  const later = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(peek, QUIET[0] + Math.random() * (QUIET[1] - QUIET[0]));
  };
  const peek = () => {
    if (!onScreen || document.hidden || !svg.classList.contains("m-away")) return later();
    show(PEEKS[Math.floor(Math.random() * PEEKS.length)]);
  };

  // The routine and each peek end with him away
  move.addEventListener("animationend", (event) => {
    if (event.target !== move) return;
    show("m-away");
    later();
  });
  new IntersectionObserver(([entry]) => (onScreen = entry.isIntersecting)).observe(svg);
  button?.addEventListener("click", () => {
    window.clearTimeout(timer);
    show("m-intro");
  });
}
