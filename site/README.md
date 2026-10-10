# codemop.com

CodeMop's website: a home page, and the docs, built with [Astro](https://astro.build/) and
[Starlight](https://starlight.astro.build/). It's separate from the `codemop` package: nothing
here is published to PyPI or used by the Action.

## Develop

```bash
npm install
npm run dev      # local dev server with hot reload (writes the docs pages first)
npm run build    # production build to dist/
npm run preview  # serve the production build locally
npm run check    # type-check the project
npm run sync     # just write the docs pages (scripts/sync-docs.mjs)
```

## The docs are the repository's own markdown

The docs pages aren't written here. `scripts/sync-docs.mjs` writes them before every build,
into `src/content/docs/` (not committed), from the README's sections marked as pages and from
`docs/self-hosting.md`, `SECURITY.md`, `CHANGELOG.md` and `CONTRIBUTING.md`. A README section
is a page when the line before its heading is an (invisible) marker:

```markdown
<!-- page: quickstart | Quick start | Review every pull request with CodeMop's GitHub Action, in two steps. -->
## Quick start: the GitHub Action
```

Links between them become links between pages, and links to anything else in the repository
go to it on GitHub. So edit those files, not the site.

## Design

The look is [gregkemp.dev](https://gregkemp.dev)'s (`github.com/sgtwickool/kempgt.com`): paper
and ink, Archivo for headings and Source Serif 4 for text, and colour kept for risograph prints
in three inks (pink `line`, blue `strong`, yellow `glow`) that overprint, multiplied on light
paper and screened on dark. The art library and the print component are copied from there,
each file saying so: change both together.

- **Prints** (`<Print name="..." />`): computed at build time, inline SVG, with motion driven by
  the scroll position, so they tell a small story as they scroll up the screen and rewind as
  they scroll back
- **Moppy, the mascot**, in the hero: a fretful little mop. He plays his routine once as the page
  loads, then peeks in now and then looking for dirt; clicking him plays it again. His motion
  is CSS animations, switched by a class on his SVG (his states are listed in
  `src/styles/mascot.css`). He was designed on a canvas:
  https://claude.ai/artifact/7cb2xzBSeYCZrxw3uCiuCp
- Both stand still for anyone who prefers reduced motion
- Colour tokens are in `src/styles/theme.css`, mapped onto Starlight's variables for both
  themes

## Structure

```
astro.config.mjs           Starlight: the sidebar, fonts, theme and the motion opt-in script.
scripts/sync-docs.mjs      Writes the docs pages from the repository's markdown.
public/                    Static files served as-is (the favicon).
src/pages/index.astro      The home page, including all of its copy.
src/content/docs/          The docs pages, written by sync-docs.mjs (not committed).
src/components/            Print and the filters the prints share, and SummaryDemo: a real
                           review from PR #20 whose boxes you can tick.
src/lib/art/               The prints, as on gregkemp.dev:
  index.ts                   every print, in page order
  prints/review-loop.ts      the prints for the review loop: mop, respond, gate
  geometry.ts, build.ts      helpers for path data, motions and print sizes
  style.ts                   turns a print's motions into CSS
  types.ts
src/lib/mascot.ts          The mascot's SVG.
src/scripts/               scroll-prints.ts moves the prints; mascot.ts says when the mascot moves.
src/styles/                theme.css: tokens, fonts and Starlight's colours; mascot.css: how
                           the mascot moves in each state.
```

To add a print, write a function in `src/lib/art/prints/`, add it to `prints` in
`src/lib/art/index.ts`, and use it with `<Print name="..." />`.

## Dependencies

`package.json` overrides `postcss-selector-parser` for `postcss-nested` (used by Starlight's
code blocks) with 7.1.6, past an advisory in the version it asks for (CPU exhaustion on hostile
CSS; it only ever parses this site's own CSS, at build time). Remove the override once
`postcss-nested` moves on.

## Deployment

`.github/workflows/site.yml` builds the site on every pull request that touches it or the docs
it's made from, and deploys it to GitHub Pages from `master`. The custom domain, codemop.com,
is set in the repository's Pages settings.
