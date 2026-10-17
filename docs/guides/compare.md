# CodeMop compared: CodeRabbit, Copilot and Claude

There are good AI code reviewers, and CodeMop isn't the right one for everyone. Here's how it
differs from the ones you're most likely weighing it against, so you can choose. Checked against
each one's own documentation in October 2026; prices and features change, so follow the links.

| | CodeMop | [CodeRabbit](https://www.coderabbit.ai/pricing) | [Copilot code review](https://docs.github.com/en/copilot/concepts/agents/code-review) | [Claude Code Review](https://code.claude.com/docs/en/code-review) |
|---|---|---|---|---|
| Where it runs | Your GitHub Actions | CodeRabbit's servers | GitHub, with Actions minutes | Anthropic's servers |
| Who sees your code | Only the model provider you choose | CodeRabbit | GitHub and its models | Anthropic |
| Model | Your choice: Claude, OpenAI, Mistral, OpenRouter, or a local one with Ollama | CodeRabbit's | GitHub's | Anthropic's |
| Price | Free; you pay your provider, about 2–3¢ a review with Claude Opus 5.5 | Free for public repositories; from $24 a user a month | Paid Copilot plans; AI credits per review, about $0.25–5 at the default level, plus Actions minutes | Team and Enterprise plans; usage-based, no flat price |
| Pull requests from forks | Reviewed automatically | Public repositories' pull requests reviewed automatically | Not covered in its docs | Skipped by automatic reviews |
| Fixes | Tick the ones you want; they're committed as one commit | Suggestions you can commit | Suggestions, or a pull request with the fixes | Comments |
| Can it block a merge? | Yes: a check that fails while bugs or security issues are open | If you turn on its [request-changes workflow](https://docs.coderabbit.ai/pr-reviews/request-changes-workflow) and require reviews | No: its reviews don't count toward required approvals | No: its check never fails |
| Open source | Yes, Apache 2.0 | No | No | No |
| Platforms | GitHub | GitHub, GitLab | GitHub | GitHub |

## When to choose something else

- **CodeRabbit,** if you want no setup at all, are fine with your code going to a hosted
  service, or use GitLab. On public repositories it's free
- **Copilot code review,** if your team already pays for Copilot and wants review built into
  GitHub, with nothing to install
- **Claude Code Review,** if you're on a Claude Team or Enterprise plan and want several agents
  reading the whole repository on each change, and are happy for that to take longer and cost
  more than a diff review

## When CodeMop fits

- **You maintain open source,** and want every fork's pull request reviewed, without sending
  anyone's code to a third party or risking your key ([how](fork-pull-requests.md))
- **You want to choose the model,** or keep code on your own terms: your own key, zero data
  retention, Bedrock, or a model on your own machine
- **You want a review cheap enough for every push,** and a merge check that means something
- **You want to fix things in one tick,** and teach it what's fine in your repository, in a
  file anyone can read

The [quick start](../../README.md#quick-start-the-github-action) takes two steps, and
[how we chose the default model](model-comparison.md) shows how the review is measured.
