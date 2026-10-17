# CodeMop: product design

What CodeMop is, who it's for, the rules it doesn't break, and how every idea for it is
judged. The [roadmap](../ROADMAP.md) says what's being built and when; this says why, and is
what an idea has to fit before it becomes a phase.

Agreed 2026-10-10, with checkpoints added 2026-10-14 and the licence and making money on
2026-10-17. The decisions are at the end ([2026-10-10](#decided-2026-10-10),
[2026-10-14](#decided-2026-10-14), [2026-10-17](#decided-2026-10-17)).

## In one line

**CodeMop is the review loop for a change:** it reviews each push to a pull request, makes
every finding easy to act on (fix it, dismiss it, teach it), and tells you when the change
is safe to merge. Cheaply enough to run on every push, and safely enough to run on anyone's
pull request.

Everything CodeMop does should make that loop better. An idea that doesn't is a different
product, however good it is.

## Who it's for

| Who | What they need | Why CodeMop and not Claude's own review |
|---|---|---|
| **Open-source maintainers** | A first review of every PR, most of them from forks by people they don't know, without paying much or risking their key | Claude's Action reviews forks only when a maintainer asks, because it runs tools on the PR's code. CodeMop never does, so it can review every fork PR automatically |
| **Small teams** | Review on every PR with a merge check, on the provider and plan they already have (another provider, zero data retention, Bedrock) | Anthropic's managed Code Review is for Team and Enterprise plans, costs about $15–25 a review and takes about 20 minutes, and its check is always neutral. CodeMop costs about 2–3¢, takes seconds, and its check can block a merge |
| **Solo builders working with agents** | To notice what their agents got wrong, to understand the code they're shipping, and to keep the app's structure sound as it grows | Claude reviews the code. Nothing yet explains it to the person who has to own it, or gets their agent to choose the app's structure on purpose |

Not for: organisations that want a deep audit of the whole repository on every change (that's
what Anthropic's Code Review and Claude Code's `/code-review` are for, and tiered review hands
the changes that need it to them), or anyone who wants an agent that writes the fixes on its own.

## The loop

```
  push ──▶ 1. Review ──▶ 2. Respond ──▶ 3. Gate ──▶ merge
              ▲                              │
              └──────── the next push ◀──────┘
```

1. **Review:** find the real problems in what changed, and only those. Built: a diff review
   with repository context (whole functions, where the changed code is used, the definitions it
   uses), inline comments with one-click suggestions, and a summary comment edited in place.
   Re-reviews look at the new commits only and report only bugs and security issues.
   *Measured by the eval: 59/64 cases passed, 99% of comments right.*
2. **Respond:** every finding gets an answer that takes one action, and the answer sticks.
   Built: tick fixes and commit them as one commit; resolve a conversation to dismiss it on
   this PR; reply `/codemop learn <why>` to teach the whole repository, in a file anyone can
   read and edit; fixed code resolves its own conversation.
3. **Gate:** say when it's safe to merge. Built: the "CodeMop" status, which fails while bugs
   or security issues are open and can be required by branch protection; `/codemop check`
   updates it.

## The rules it doesn't break

1. **It never runs the pull request's code, and the model has no tools.** It reads the diff
   and the repository through the API, and holds them in memory. That's what makes it safe on
   fork PRs, and every feature keeps it so. (Tiered review's deep tiers run Claude Code, which
   does check out the code: on fork PRs they run only when a maintainer asks.)
2. **The repository decides how it's reviewed, never who reviews it or what that costs.**
   `.codemop.yml` is read from the default branch and can't choose the provider, model,
   endpoint or spending limits. Otherwise reviewing a stranger's PR could send your key to their
   server.
3. **Cheap and fast enough for every push.** A few cents and seconds is the default. Anything
   costlier is chosen for the change that needs it, and the review says why.
4. **Quiet and right.** Few comments, nearly all of them correct. A comment that's wrong costs
   more trust than a missed issue, so a new feature that adds comments has to hold the eval's
   false-alarm rate.
5. **Everything happens on the pull request.** One summary comment, edited in place, with
   everything that can be done; what it learns is in a file in the repository. No dashboard to
   visit and no hidden state. A repository that pushes straight to its default branch gets one
   issue in place of the pull request, for checkpoints.
6. **Your key, your provider, no hosted service.** CodeMop never holds anyone's code or pays
   for anyone's inference.
7. **Measured, not guessed.** A change to what the review finds goes through the eval first.

## What it isn't

- Not an agent: it doesn't explore the repository, run tests or write code on its own. When a
  change needs that, tiered review hands it to Claude Code
- Not a hosted service, and not a dashboard
- Not a coding assistant: it reviews and explains changes, it doesn't help write them.
  Checkpoints write down decisions for an agent to follow, never the code

## The ideas, judged against the loop

| Idea | Loop step | For | Verdict | Size |
|---|---|---|---|---|
| Context for more languages | Review | Everyone | **Core** | S–M |
| Measuring it in use | All | Us, and teams | **Core** | S |
| `/codemop explain` (teaching mode) | Respond | Solo builders, and newcomers on any team | **Core** | S–M |
| Checkpoints (strategic review) | Review, Respond | Solo builders working with agents | **Core** | M–L |
| Tiered review | Review | Teams, maintainers | **Core** | L |
| Cross-repository review | Review | Teams with several repositories | **Core** | L |
| GitLab, Gitea/Forgejo | All | New users | Distribution: when someone asks | M each |
| Self-hosted GitHub App | All | Organisations | Distribution: when someone asks | M |
| Multi-repository workspaces | None (writing code) | | **Doesn't fit:** cut | |
| VS Code extension, analytics dashboard | None | | **Doesn't fit:** cut (rule 5) | |

### Context for more languages

Repository context reads Python with the standard library's `ast`. Every other language only
gets the lines around each change: no whole functions, no definitions, and no "where it's used",
which is what found the cross-file bugs. Most potential users write TypeScript or JavaScript.

- **Design:** `tree-sitter` with its prebuilt grammars, behind the same steps as Python: the
  function around a change, what the change defines, where that's used in files that import it.
  TypeScript/JavaScript first, then Go
- **Measure:** cross-file eval cases in TypeScript, like the Python ones
- **Risk:** a native dependency in a package that's pure Python today; the grammars ship as
  wheels, so it should install anywhere the Action runs

### Measuring it in use

The eval measures the review against an answer key. Nothing yet measures whether people act on
what it finds, which is what matters. The summary already records every finding's outcome:
applied, addressed by a later commit, dismissed, or still open.

- **Design:** `codemop stats owner/repo` reads the summaries on recent PRs and reports the share
  of findings acted on against dismissed, by severity, and what reviews cost. Nothing is sent
  anywhere; it reads what's already on the PRs
- **Why first:** it tells us which of the ideas below matter, starting with dogfooding

### `/codemop explain` (teaching mode)

For people who are shipping code they didn't write and don't fully follow, mostly code their
agents wrote. Today's comments say what's wrong and how to fix it, for someone who already
knows why it matters.

- **Design: on demand, in the loop's own language.** Reply `/codemop explain` to a comment:
  CodeMop replies with the concept behind the mistake, why it's easy to make (and why agents
  often do), and links to the official documentation. Comment `/codemop explain` on the PR:
  the summary gains a short walkthrough of what the change does and how its parts fit together.
  On demand means nobody gets tutorials they didn't ask for, and it costs nothing until asked
- **Always-on**, for a repository whose people want it every time, is `explain: true` in
  `.codemop.yml`: each comment gains a collapsed "Learn more" section. It's how the repository
  is reviewed, not who reviews it, so it fits rule 2
- **Links have to be real.** A tutorial link that doesn't exist would undo the point. Only
  links to official documentation sites, each checked to load before it's posted; anything else
  is left out
- **Not going too far:** it explains this change and its findings. It's not a course, it
  doesn't quiz anyone, and it doesn't track what someone has learned
- **Measure:** the judge grades explanations for accuracy, and the link check runs in the eval

### Checkpoints (strategic review)

The review looks at one change at a time; nothing looks at where the app is heading. Someone
building with an agent gets a working app quickly, but nobody decides its structure: where data
access lives, what runs on the server, when a file should be split. The agent does whatever is
quickest each time, and the app becomes a tangle that nobody would want to share. The person
doesn't know which structures exist or when each one is right, but a model reading the app does.

- **Design: a question at the moment it matters, and the answer becomes a rule.**
  1. **Notice:** cheap rules on the diff and the file tree spot a stage the app has reached (see
     below). The model runs only when one does, so most pushes cost nothing extra
  2. **Ask:** one checkpoint, in plain words. Two or three options, a sentence or two on each,
     and one recommended for this app, with the reasons taken from its own files. Each option says
     when to revisit it. `/codemop explain` goes deeper on any of them
  3. **Record:** ticking an option writes the decision to `ARCHITECTURE.md`, in plain words, and
     points `AGENTS.md` (read by Cursor, Codex and Copilot) and `CLAUDE.md` (read by Claude Code)
     at it. From then on the person's agent builds that way. It's `/codemop learn` for the shape of the whole app
  4. **Hold:** the review checks later changes against the recorded decisions ("this page reads
     from the database directly, but data access lives in `lib/data/`"), as it does what it learns
- **The stages, each asked once** ("not now" asks again at a later stage):

  | When | The question |
  |---|---|
  | The first changes | What shape is the app: folders by feature or by kind of file? |
  | A database or ORM is added | Where does data access live? |
  | Auth or payments are added | What runs on the server, what in the browser, and where secrets go |
  | A file passes about 400 lines, or one component fetches, holds state and renders | How should it be split? |
  | The same logic in three places | A shared module, or leave it |
  | State passed down through many layers | Is it time for a store? |
  | A deploy config, a license or a README | Ready to share: tests for the core, `.env.example`, no secrets, a linter |

- **Proportional, not textbook.** The recommendation is the simplest structure that holds
  until the next stage. An agent building a layered service architecture for a to-do app is the
  other way to make a mess, and the person can't tell that from good advice either
- **Specific or silent.** A checkpoint cites the app's own files. "Consider a cleaner
  architecture" isn't one, and the eval fails it
- **Rare and quiet (rule 4).** A handful of checkpoints in an app's life, never more than one at
  a time. They don't fail the merge check unless the repository asks them to
- **Where people are.** Most people building with agents push straight to their default branch
  and never open a pull request. So checkpoints run on pushes to the default branch as well,
  in one pinned "CodeMop checkpoints" issue, edited in place like the summary. Ticking an option
  there commits the decision to the default branch (or opens a pull request for it, where the
  branch is protected). `codemop checkup` runs the same thing locally, with the person's own key
- **Fits the rules:** it reads the file tree and a few files through the API and never runs the
  code (rule 1). A checkpoint reads more than a diff review, perhaps 10–30¢, but is rare, and
  says why it ran (rule 3). The decisions are in the repository, for anyone to read and edit
  (rule 5)
- **Build it in this order:** `codemop checkup` first, run on real apps built with agents at
  different stages, to find out whether its recommendations are specific, right and in
  proportion. Nothing else is worth building until they are. Then pull requests, then the issue
- **Measure:** eval cases of apps at known stages, each with an answer key of sensible
  recommendations; the judge grades them for specificity (cites the files), correctness and
  proportion. Later, `codemop stats` counts options chosen against "not now"

### Tiered review

As in the roadmap's Phase 9: rules skip only what's certainly trivial; a quick, cheap triage
picks CodeMop's review (2–3¢) or Claude Code's `/code-review` at low or high effort (dollars,
reads the whole repository) for changes that are risky or reach widely; the summary says which
tier reviewed it and why.

- **Fits:** it's how CodeMop stays cheap for every push (rule 3) and still gets a deep review
  where one matters, and it's the answer to "Claude reads the whole repository"
- **Open question:** whether the deep tiers' findings come into CodeMop's summary and checklist
  (one loop, but parsing another tool's output) or stay in Claude's own comments (simpler, two
  places to respond, against rule 5). The first is the product; the second is a step to it
- **Measure:** add `/code-review` low and high as eval configurations, which also says how
  close CodeMop's own review gets to it

### Cross-repository review

As in the roadmap's Phase 10: PRs in different repositories that ship together, linked by the
same branch name or a `Ships with: org/backend#42` line, reviewed as one change for the bugs
that come from mismatches (request and response shapes, field names, the order they deploy in).

- **Fits:** it widens "a change" from one PR to the PRs that ship together; the loop is the
  same, with each comment on the PR it belongs to
- **Hard part:** reading other repositories needs a token that can (a GitHub App or a
  fine-grained token); an Action's own token can't
- **Measure:** eval cases made of linked pairs of diffs

### Cut

- **Multi-repository workspaces** (claude-squad for several repositories): a good idea, but it's
  for writing code, not reviewing it. It would make a separate tool, which could open the
  linked PRs that cross-repository review then reviews
- **VS Code extension:** the suggestion blocks and the checklist already put fixes one click
  away on the PR, where review happens
- **Analytics dashboard:** against rule 5; `codemop stats` gives the numbers without one

## Proposed order

After v1 (the end of dogfooding, about 2026-10-23), smallest and widest first, so the big bets
are chosen with real users' numbers:

1. **v1.1, everyone's reviews:** context for TypeScript/JavaScript, and `codemop stats`
2. **v1.2, explain:** `/codemop explain`
3. **v1.3, checkpoints:** `codemop checkup`, then pull requests and the checkpoints issue
4. **v1.4, tiered review**
5. **v1.5, cross-repository review**
6. GitLab, Gitea/Forgejo and the self-hosted App when people ask for them

Each is a roadmap phase (Phases 6–10) with its own "done when", and goes through the eval
before it ships.

## How we'll know it's working

- **The eval:** cases passed, comments right, false alarms, cost per review. No release makes
  them worse
- **In use (`codemop stats`):** most findings acted on rather than dismissed; few comments per
  PR; dismissals that drop over time as it learns a repository
- **Adoption:** someone installs it from the README alone in a few minutes; other people's
  repositories run it; issues come from people we don't know

## Making money

The Action stays free and complete: your key, your model, every feature. If CodeMop makes money,
it's from convenience, never from holding features back.

- **Hosted CodeMop, the likeliest:** a GitHub App installed with one click, with no key and no
  workflow file, and the model's cost in a monthly price. It's for the people least willing to
  set up an Action, above all the solo builders checkpoints are for. Cross-repository review
  needs a GitHub App anyway, so that could be the first thing it does that the Action can't
  - **It breaks rule 6** (no hosted service; never holds code or pays for inference), so
    building it means changing the rule for the hosted app only. The Action and self-hosting
    keep it as written
- **Paid setup and support** for companies that run it themselves (Bedrock, zero data retention)
- **GitHub Sponsors**, from now: small, but it shows the project is looked after
- **Not:** features held back from the free Action, ads, or anything done with people's code
- **When:** not before v1 has users. `codemop stats` and adoption say whether anyone would pay;
  it's decided alongside checkpoints (v1.3), whose users are the likeliest to

**The licence fits it:** Apache 2.0 lets anyone use, change and host the code, and its NOTICE
file has to travel with every copy. The name, the logo and Moppy are trademarks
([TRADEMARKS.md](../TRADEMARKS.md)), so a copy can't call itself CodeMop. Code that exists only
for a hosted service (accounts, billing) can stay private.

## Decided, 2026-10-10

1. **Solo builders working with agents are a target**, so `/codemop explain` is v1.2. It's
   small, nobody else does it, and on demand it costs the other users nothing
2. **Multi-repository workspaces are cut** from CodeMop; they could be their own project
3. **Tiered review comes before cross-repository review:** it improves every review, where
   cross-repository review serves fewer people and needs a GitHub App or token first
4. **The rules stand as written.** Rule 1 is the one most likely to be tested, by tiered review
   and by any idea that wants to run the code

## Decided, 2026-10-14

1. **Checkpoints are part of CodeMop**, not a separate product: the decisions they record are
   what the review then holds later changes to, and that only works in the same tool
2. **They reach people who don't use pull requests**: pushes to the default branch, one pinned
   issue, and `codemop checkup` locally. Rule 5 now says so
3. **They come before tiered review**, as v1.3: they build on explain and `learn`, and serve the
   solo builders that v1.2 starts on

## Decided, 2026-10-17

1. **Apache 2.0 from v1**, with a NOTICE file (0.1.0 stays MIT). The name, the logo and Moppy
   are trademarks, set out in `TRADEMARKS.md`, and CodeMop is to be registered as a UK trade
   mark (classes 9 and 42)
2. **Making money:** hosted CodeMop is the likeliest way, decided once v1 has users; rule 6
   stands until then
3. **The free Action keeps every feature**
