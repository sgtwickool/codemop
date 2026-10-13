// When Moppy moves (moppy.css says how): his routine once the page has settled (loaded, its
// fonts ready, and a beat for the eye to land on the headline), then now and then a drip lands
// and he mops it up; each only while he's on screen and the tab is visible. Off screen, his
// blinking and breathing pause too. Clicking him plays the routine again. With reduced motion
// he stays still, and this does nothing.

const ROUTINES = ["m-intro", "m-tidy"];
const QUIET = [12_000, 28_000]; // between drips, at random within this, in ms
const BEAT = 300; // after the page settles, before he starts (the routine waits 0.4s more itself)

const loaded = () =>
  document.readyState === "complete"
    ? Promise.resolve()
    : new Promise((done) => addEventListener("load", done, { once: true }));

export function playMoppy() {
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

  const play = (routine: string) => {
    svg.classList.remove("m-hold", ...ROUTINES);
    svg.getBoundingClientRect(); // so its animations start over
    svg.classList.add(routine);
  };
  const later = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(drip, QUIET[0] + Math.random() * (QUIET[1] - QUIET[0]));
  };
  const drip = () => {
    if (!onScreen || document.hidden) return later();
    play("m-tidy");
  };
  // The intro, held on its first frame until the page has settled and he can be seen
  const start = () => {
    if (!svg.classList.contains("m-hold")) return;
    if (!onScreen || document.hidden) return window.setTimeout(start, 250);
    svg.classList.remove("m-hold");
  };

  // Each routine ends with the floor clean, which is how the scene rests
  move.addEventListener("animationend", (event) => {
    if (event.target !== move) return;
    svg.classList.remove(...ROUTINES);
    later();
  });
  new IntersectionObserver(([entry]) => {
    onScreen = entry.isIntersecting;
    svg.classList.toggle("m-paused", !onScreen);
  }).observe(svg);
  button?.addEventListener("click", () => {
    window.clearTimeout(timer);
    play("m-intro");
  });
  Promise.all([loaded(), document.fonts.ready]).then(() => window.setTimeout(start, BEAT));
}
