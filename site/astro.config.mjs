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
      logo: { src: "./src/assets/logo.svg" },
      // The home page's hero (its headline and Moppy's scene), and the header's links
      components: {
        Hero: "./src/components/Hero.astro",
        SocialIcons: "./src/components/HeaderLinks.astro",
      },
      social: [{ icon: "github", label: "GitHub", href: "https://github.com/sgtwickool/codemop" }],
      customCss: [
        "@fontsource-variable/bricolage-grotesque/opsz.css",
        "@fontsource-variable/figtree/wght.css",
        "@fontsource-variable/figtree/wght-italic.css",
        "@fontsource/barlow-condensed/700.css",
        "@fontsource/barlow-condensed/800.css",
        "@fontsource-variable/jetbrains-mono/wght.css",
        "./src/styles/theme.css",
      ],
      head: [
        {
          // Moppy and the caution tape move, unless the visitor prefers reduced motion
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
