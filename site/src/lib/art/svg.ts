// A print as inline SVG markup: for Print.astro, and for Starlight's hero, which takes an
// image as HTML. The markup is gregkemp.dev's Print.astro; its classes are styled in
// src/styles/theme.css, and src/scripts/scroll-prints.ts moves it.
import { prints, type PrintName } from "./prints";
import { printStyles } from "./style";

const escape = (text: string) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");

export function printSvg(name: PrintName, { plate = true, className = "" } = {}): string {
  const print = prints[name];
  const { width, height, layers, labels = [] } = print;
  const styles = printStyles(print);
  const classes = ["print", plate && "plate", className].filter(Boolean).join(" ");

  const shapes = layers.map((layer) => {
    // Paper ink covers what's beneath it, so it doesn't blend like the inks.
    const blend = layer.ink !== "paper";
    const length = layer.motion?.kind === "draw" ? ' pathLength="1"' : "";
    const path = (cls: string) =>
      `<path${cls ? ` class="${cls}"` : ""} d="${layer.d}"${length} style="${escape(styles.layer(layer))}"/>`;
    return layer.spin
      ? `<g${blend ? ' class="ink"' : ""} style="${escape(styles.spin(layer.spin))}">${path("")}</g>`
      : path(blend ? "ink" : "");
  });
  const texts = labels.map(
    (label) =>
      `<text class="print-label" x="${label.x}" y="${label.y}" text-anchor="${label.anchor ?? "start"}" ` +
      `style="${escape(styles.label(label))}">${escape(label.text)}</text>`,
  );

  return (
    `<svg viewBox="0 0 ${width} ${height}" class="${classes}"${styles.animated ? " data-animate" : ""} ` +
    `style="--print-bg:var(${plate ? "--plate" : "--paper"})" aria-hidden="true" focusable="false">` +
    `<g filter="url(#rough)">${shapes.join("")}</g>${texts.join("")}` +
    (plate ? `<rect class="grain" width="${width}" height="${height}"/>` : "") +
    `</svg>`
  );
}
