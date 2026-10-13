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

A tidy tool should look tidy, and fun: wet-floor-sign yellow and ink, a pale water blue, chunky
outlines with solid offset shadows, and flat colour (no shading or shine). Bricolage Grotesque
for headings, Figtree for text, Barlow Condensed for the small caution labels and JetBrains
Mono for code, all self-hosted. It was designed on a canvas, as direction D:
https://claude.ai/artifact/3gPHveubJAv6dAoKUZ9ec5

- **Moppy, the mascot**, in the hero: a fretful little mop, beside a wet-floor sign and its
  puddle. As the page loads he hops in, mops up the puddle, knocks the tipping sign straight
  and hops for joy; now and then a drip lands and he mops that up too; clicking him plays the
  routine again. His motion is CSS animations, switched by a class on his SVG (the routines are
  in `src/styles/mascot.css`). The scene is drawn as it rests, tidied up, which is all that
  reduced motion shows. He was first designed on a canvas:
  https://claude.ai/artifact/7cb2xzBSeYCZrxw3uCiuCp
- **The caution tape** across the home page creeps along, except with reduced motion
- Colour tokens are in `src/styles/theme.css`, mapped onto Starlight's variables for both
  themes, with the buttons, cards and labels the pages share

## Dependencies

`package.json` overrides `postcss-selector-parser` for `postcss-nested` (used by Starlight's
code blocks) with 7.1.6, past an advisory in the version it asks for (CPU exhaustion on hostile
CSS; it only ever parses this site's own CSS, at build time). Remove the override once
`postcss-nested` moves on.

## Deployment

`.github/workflows/site.yml` builds the site on every pull request that touches it or the docs
it's made from, and deploys it to GitHub Pages from `master`. The custom domain, codemop.com,
is set in the repository's Pages settings.
