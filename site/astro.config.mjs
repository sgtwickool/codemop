// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// The docs pages come from the repository's markdown (scripts/sync-docs.mjs); the home page
// is src/pages/index.astro.
export default defineConfig({
  site: "https://codemop.com",
  integrations: [
    starlight({
      title: "CodeMop",
      description: "AI code review for pull requests, with the model of your choice. Tick the fixes you want and it commits them.",
      favicon: "/favicon.svg",
      social: [{ icon: "github", label: "GitHub", href: "https://github.com/sgtwickool/codemop" }],
      customCss: [
        "@fontsource-variable/archivo/wdth.css",
        "@fontsource-variable/source-serif-4/opsz.css",
        "@fontsource-variable/source-serif-4/opsz-italic.css",
        "./src/styles/theme.css",
      ],
      head: [
        {
          // The prints move as they're scrolled past, unless the visitor prefers reduced motion
          tag: "script",
          content:
            "document.documentElement.classList.toggle('motion', !matchMedia('(prefers-reduced-motion: reduce)').matches)",
        },
      ],
      sidebar: [
        { label: "Start", items: ["quickstart", "responding", "merge-check"] },
        { label: "Reference", items: ["configuration", "models", "cli"] },
        { label: "About", items: ["privacy", "security", "self-hosting", "changelog", "contributing"] },
      ],
      pagination: true,
    }),
  ],
});
