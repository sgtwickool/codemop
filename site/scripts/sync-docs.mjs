// Writes the site's docs pages from the repository's own markdown, so there's one copy of
// the docs, versioned with the code: the README's sections become pages, and the other docs
// come in whole. Links between them become links between pages; links to anything else in
// the repository go to it on GitHub. Runs before every build (npm run sync).
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const repo = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const out = join(repo, "site", "src", "content", "docs");
const github = "https://github.com/sgtwickool/codemop/blob/master/";

// The README's sections, by heading: the page each becomes. Sections not listed (the intro,
// "More") aren't pages; the home page says what they do.
const sections = {
  "Quick start: the GitHub Action": { slug: "quickstart", title: "Quick start", description: "Review every pull request with CodeMop's GitHub Action, in two steps." },
  "Responding to CodeMop": { slug: "responding", title: "Responding to CodeMop", description: "Fix, dismiss or teach: what to do with each issue CodeMop raises." },
  "Blocking merges": { slug: "merge-check", title: "Blocking merges", description: "CodeMop's merge check: a status that fails while bugs or security issues are open." },
  "Configuring reviews": { slug: "configuration", title: "Configuration", description: "Every .codemop.yml setting and Action input." },
  "Choosing a model": { slug: "models", title: "Choosing a model", description: "The providers and models CodeMop supports, and which the eval recommends." },
  "Privacy: what's sent where": { slug: "privacy", title: "Privacy", description: "Exactly what CodeMop sends, and where." },
  "The command line": { slug: "cli", title: "The command line", description: "Review a pull request or a local diff from your terminal." },
};

// Whole files: the page each becomes.
const files = {
  "docs/self-hosting.md": { slug: "self-hosting", description: "Run CodeMop as a webhook server with a database." },
  "SECURITY.md": { slug: "security", description: "Reporting a vulnerability, and why fork PRs are safe to review." },
  "CHANGELOG.md": { slug: "changelog", description: "What changed in each release." },
  "CONTRIBUTING.md": { slug: "contributing", description: "Setting up, making a change, and releasing." },
};

/** GitHub's anchor for a heading. */
const anchor = (heading) =>
  heading
    .toLowerCase()
    .trim()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .replace(/\s/g, "-");

const readmeAnchors = Object.fromEntries(Object.entries(sections).map(([heading, page]) => [anchor(heading), page.slug]));

/** Where a link from `from` (a repository path) should go on the site. */
function target(href, from) {
  if (/^(mailto:|#)/.test(href)) return href.startsWith("#") ? siteLink("README.md", href.slice(1), from) ?? href : href;
  let path = href;
  if (href.startsWith(github)) path = href.slice(github.length);
  else if (/^[a-z]+:/i.test(href)) return href;
  else path = normalize(join(dirname(from), href));
  const [file, hash = ""] = path.split("#");
  return siteLink(file, hash, from) ?? `${github}${path}`;
}

function siteLink(file, hash, from) {
  if (file === "README.md" || (file === "" && from === "README.md")) {
    const slug = readmeAnchors[hash];
    return slug ? `/${slug}/` : hash ? undefined : "/";
  }
  const page = files[file];
  return page && `/${page.slug}/${hash ? `#${hash}` : ""}`;
}

function rewriteLinks(markdown, from) {
  return markdown.replace(/\]\(([^)\s]+)\)/g, (_, href) => `](${target(href, from)})`);
}

const frontmatter = (title, description) =>
  `---\ntitle: ${JSON.stringify(title)}\ndescription: ${JSON.stringify(description)}\neditUrl: false\n---\n\n`;

function write(slug, title, description, body, from) {
  writeFileSync(join(out, `${slug}.md`), frontmatter(title, description) + rewriteLinks(body.trim(), from) + "\n");
}

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

// The README, a page per section. (Code blocks never start a line with "## ".)
const readme = readFileSync(join(repo, "README.md"), "utf8");
const found = new Set();
for (const part of readme.split(/^## /m).slice(1)) {
  const [heading, ...rest] = part.split("\n");
  const page = sections[heading.trim()];
  if (!page) continue;
  found.add(heading.trim());
  write(page.slug, page.title, page.description, rest.join("\n"), "README.md");
}
const missing = Object.keys(sections).filter((heading) => !found.has(heading));
if (missing.length) {
  throw new Error(`README.md has no section called ${missing.map((h) => `"${h}"`).join(", ")}: update sync-docs.mjs`);
}

for (const [file, page] of Object.entries(files)) {
  const text = readFileSync(join(repo, file), "utf8");
  const [, title, body] = text.match(/^# (.+)\n([\s\S]*)$/) ?? [];
  if (!title) throw new Error(`${file} should start with a "# Title" line`);
  write(page.slug, title.trim(), page.description, body, file);
}

console.log(`sync-docs: wrote ${Object.keys(sections).length + Object.keys(files).length} pages to src/content/docs/`);
