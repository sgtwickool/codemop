// Writes the site's docs pages from the repository's own markdown, so there's one copy of
// the docs, versioned with the code: the README's sections marked as pages become pages, and
// the other docs come in whole. Links between them become links between pages; links to
// anything else in the repository go to it on GitHub. Runs before every build (npm run sync).
//
// A README section becomes a page when the line before its heading is a marker:
//   <!-- page: <slug> | <title> | <description> -->
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { slug as anchor } from "github-slugger";

const repo = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const out = join(repo, "site", "src", "content", "docs");
const github = "https://github.com/sgtwickool/codemop/blob/master/";

// Whole files: the page each becomes.
const files = {
  "docs/self-hosting.md": { slug: "self-hosting", description: "Run CodeMop as a webhook server with a database." },
  "SECURITY.md": { slug: "security", description: "Reporting a vulnerability, and why fork PRs are safe to review." },
  "CHANGELOG.md": { slug: "changelog", description: "What changed in each release." },
  "CONTRIBUTING.md": { slug: "contributing", description: "Setting up, making a change, and releasing." },
};

// The README's marked sections: each one's page, and its body.
const readme = readFileSync(join(repo, "README.md"), "utf8");
const marked = /^<!-- page: (\S+) \| (.+?) \| (.+?) -->\n## (.+)\n([\s\S]*?)(?=^(?:<!-- page: |## )|(?![\s\S]))/gm;
const sections = [...readme.matchAll(marked)].map(([, slug, title, description, heading, body]) => ({
  slug, title, description, heading, body,
}));
if (!sections.length) throw new Error("README.md has no sections marked <!-- page: ... -->");
const readmeAnchors = Object.fromEntries(sections.map((s) => [anchor(s.heading), s.slug]));

/** Where a link in `from` (a repository path) goes on the site: a page, or GitHub */
function target(href, from) {
  if (href.startsWith("#")) return siteLink(from, href.slice(1)) ?? href;
  if (/^[a-z]+:/i.test(href) && !href.startsWith(github)) return href;
  const path = href.startsWith(github) ? href.slice(github.length) : normalize(join(dirname(from), href));
  const [file, hash = ""] = path.split("#");
  return siteLink(file, hash) ?? `${github}${path}`;
}

function siteLink(file, hash) {
  if (file === "README.md") {
    const slug = readmeAnchors[hash];
    return slug ? `/${slug}/` : hash ? undefined : "/";
  }
  const page = files[file];
  return page && `/${page.slug}/${hash ? `#${hash}` : ""}`;
}

function write(slug, title, description, body, from) {
  const text = body.trim().replace(/\]\(([^)\s]+)\)/g, (_, href) => `](${target(href, from)})`);
  const frontmatter = `---\ntitle: ${JSON.stringify(title)}\ndescription: ${JSON.stringify(description)}\n---\n\n`;
  writeFileSync(join(out, `${slug}.md`), frontmatter + text + "\n");
}

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
for (const s of sections) write(s.slug, s.title, s.description, s.body, "README.md");
for (const [file, page] of Object.entries(files)) {
  const [, title, body] = readFileSync(join(repo, file), "utf8").match(/^# (.+)\n([\s\S]*)$/) ?? [];
  if (!title) throw new Error(`${file} should start with a "# Title" line`);
  write(page.slug, title.trim(), page.description, body, file);
}

console.log(`sync-docs: wrote ${sections.length + Object.keys(files).length} pages to src/content/docs/`);
