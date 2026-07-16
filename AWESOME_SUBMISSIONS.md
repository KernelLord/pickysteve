# Awesome-list & directory submission kit

Everything needed to submit PickySteve to the curated lists and directories where it
genuinely fits. Each target below has the exact entry line in that list's format, where to
place it, and a ready PR title/body.

**Read this first — how not to get rejected:**

- Submit to lists where the project actually belongs. Shotgunning every awesome-list gets
  PRs closed as spam and can get the repo flagged by curators who talk to each other.
  The targets below are the ones with a real claim.
- One PR per list, one entry per PR, placed **alphabetically** within the chosen section.
- Read each list's `CONTRIBUTING.md` before opening the PR — some have lint bots
  (`awesome-lint`), description length limits, or "project must be >30 days old" rules.
- Several reviewers click the install instructions. The README currently says there is no
  PyPI package yet while `server.json` references `pypi: pickysteve 0.1.0` — publish to
  PyPI (the trusted-publishing workflow is already in place) or align the two before
  submitting, so the first curator click doesn't hit a contradiction.
- Space submissions out over a few days rather than blasting all at once.

Canonical one-liner (keep it consistent everywhere):

> Skill router and context picker for coding agents — a cheap model picks the one skill a
> request needs and returns a small, focused, injection-scanned context bundle instead of
> loading everything.

---

## Tier 1 — strongest fits (MCP server lists)

### 1. punkpeye/awesome-mcp-servers
The largest MCP list; also powers mcpservers.org.

- **Section:** `🛠️ Developer Tools` (alphabetical by repo name)
- **Entry (their format uses author/repo + legend emoji — 🐍 Python, 🏠 local):**
  ```markdown
  - [KernelLord/pickysteve](https://github.com/KernelLord/pickysteve) 🐍 🏠 - Skill router and context picker for coding agents — picks the one skill a request needs and returns a focused, injection-scanned context bundle.
  ```
- **PR title:** `Add PickySteve (skill router / context picker for coding agents)`
- **PR body:**
  > Adds PickySteve under Developer Tools. It's an MCP stdio server (`pick_context`,
  > `list_skills`) that routes a request to the single most relevant skill and returns a
  > small, untrusted-data-boundaried context bundle, with prompt-injection scanning on
  > both the request and every retrieved doc. Python 3.11+, MIT, stdlib-only connectors.
  > Entry is alphabetical within the section and follows the legend (🐍 🏠).

### 2. wong2/awesome-mcp-servers
- **Section:** Community Servers (alphabetical)
- **Entry:**
  ```markdown
  - [PickySteve](https://github.com/KernelLord/pickysteve) - Skill router and context picker for coding agents, with prompt-injection scanning on requests and retrieved docs
  ```
- **PR title:** `Add PickySteve`

### 3. appcypher/awesome-mcp-servers
- **Section:** Developer Tools (alphabetical)
- **Entry:**
  ```markdown
  - [PickySteve](https://github.com/KernelLord/pickysteve) - Skill router and context picker for coding agents — one focused, injection-scanned skill bundle per request instead of everything in context.
  ```
- **PR title:** `Add PickySteve to Developer Tools`

### 4. punkpeye/awesome-mcp-devtools
PickySteve doubles as MCP developer tooling (routing/aggregation layer in front of skills).
Check the section layout at submission time (Routers/Gateways vs. Utilities) and reuse the
Tier-1 entry line.

---

## Tier 2 — good fits (Claude Code / agent ecosystems)

### 5. hesreallyhim/awesome-claude-code
PickySteve is installable as a Claude Code plugin and MCP server (`claude mcp add
pickysteve …`). **Note:** this list takes submissions through an issue template /
`/add-new-resource` workflow rather than direct PRs — follow their CONTRIBUTING.

- **Suggested entry (Tooling section):**
  ```markdown
  - [PickySteve](https://github.com/KernelLord/pickysteve) - Skill router that picks the one skill a prompt needs and injects a focused, injection-scanned context bundle via MCP; installable as a plugin.
  ```

### 6. e2b-dev/awesome-ai-agents
Fits the building-blocks/framework side rather than the agents side. Their entries are
structured subsections (name, links, one-paragraph description) — adapt the canonical
one-liner plus the 18-agent connector matrix as the differentiator.

---

## Tier 3 — directories that don't need an awesome-list PR

Already done in this repo (no action beyond publishing):
- **Official MCP registry** — `server.json` ✅
- **Glama** — `glama.json` ✅ (Glama auto-indexes GitHub; claim the listing at glama.ai)

Submit via their own flows (no fork/PR to a list needed):
- **mcp.so** — submission is an issue on their directory repo (chatmcp) or the on-site form.
- **PulseMCP** — on-site submission form; auto-indexes the official registry too.
- **Smithery** — publish via smithery.ai (works best once the package install path is real).
- **cursor.directory (MCP section)** — PR to `pontusab/directories` with a small JSON/MDX
  entry; reuse the canonical one-liner.

---

## Not worth submitting (and why)

- **jaw9c/awesome-remote-mcp-servers** — remote/hosted servers only; PickySteve is stdio/local.
- **awesome-python, awesome-selfhosted** — notability bars (age, adoption) the project
  doesn't clear yet; a rejected PR there ages badly.
- **Per-editor lists (awesome-cursor, awesome-windsurf, …)** — these mostly link back to
  the MCP lists above; Tier 1 coverage reaches the same audience without the spray.

## PR body boilerplate (adapt per list)

> **What it is:** PickySteve is an MCP stdio server + skill router for coding agents. A
> cheap model routes each request to the single most relevant skill (BM25 + embeddings,
> RRF-fused, cross-encoder reranked with a calibrated confidence floor) and returns a
> small, untrusted-data-boundaried context bundle. Both the raw request and every
> retrieved doc are scanned for prompt injection before anything reaches the main model.
>
> **Why it fits this list:** works with any MCP client (Claude Code, Codex, Cursor,
> Windsurf, Cline, Gemini CLI, Goose, and 11 more — see INTEGRATIONS.md), plus an
> OpenAI-compatible proxy for non-MCP tools. MIT licensed, Python 3.11+, connectors are
> stdlib-only.
>
> Checklist: entry is alphabetical in its section, one entry per PR, description follows
> the list's format.
