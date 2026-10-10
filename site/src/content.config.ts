import { defineCollection } from "astro:content";
import { docsLoader } from "@astrojs/starlight/loaders";
import { docsSchema } from "@astrojs/starlight/schema";

// The docs pages are written by scripts/sync-docs.mjs, from the repository's own markdown.
export const collections = {
  docs: defineCollection({ loader: docsLoader(), schema: docsSchema() }),
};
