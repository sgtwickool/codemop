// When Moppy moves (moppy.css says how): his routine once as the page loads, then now and then
// a drip lands and he mops it up, only while he's on screen and the tab is visible. Off screen,
// his blinking and breathing pause too. Clicking him plays the routine again. With reduced
// motion he stays still, and this does nothing.

const ROUTINES = ["m-intro", "m-tidy"];
const QUIET = [12_000, 28_000]; // between drips, at random within this, in ms

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
    svg.classList.remove(...ROUTINES);
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
}
