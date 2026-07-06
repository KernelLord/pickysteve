# Connecting PickySteve to coding agents

PickySteve exposes its picky-context retrieval through **three connector surfaces**, all
dependency-free (they run on the existing venv — nothing extra to `pip install`):

| Surface | Command | Connects to |
|---|---|---|
| **MCP stdio server** | `python -m pickysteve.connectors.mcp_server` | Claude Code, Codex, Cursor, Windsurf, Cline, Roo Code, Gemini CLI, Qwen Code, Goose, OpenHands, GitHub Copilot, Kimi Code, OpenCode, ZeroClaw |
| **OpenAI-compatible proxy** | `python -m pickysteve.connectors.http_server` → `http://localhost:8077/v1` | Aider, Hermes, ZeroClaw, OpenCode, OpenClaw, NanoClaw — anything that takes a custom OpenAI base URL |
| **REST `/pick` + CLI + import** | `POST /pick` · `python -m pickysteve "task"` · `Engine().pick()` | universal fallback for anything that can shell out, call HTTP, or import Python |

### One-command install (writes the config for you, with a backup)

```bash
python -m pickysteve.connectors.install --list          # show agents + which are detected
python -m pickysteve.connectors.install --all           # wire every DETECTED agent (backs up first)
python -m pickysteve.connectors.install --agent cursor --dry-run   # preview one
python -m pickysteve.connectors.install --all --uninstall          # remove (surgical + restorable)
```

`--uninstall` removes **only** the pickysteve entry — deleting configs it created, and preserving
every other setting/comment in configs it merged into (verified round-trip: Qwen's 5 keys and the
TOML `model`/`providers` survived). Backups (`*.pickysteve.bak`) let you revert either direction.

The installer **deep-merges** the pickysteve MCP entry into JSON configs (never clobbering your
existing settings — verified: Qwen's `env`/`modelProviders`/`model`/`security` survived), **appends**
a `[mcp_servers.pickysteve]` section to TOML configs (Codex/Kimi/ZeroClaw) only if absent, backs up
every file it touches (`*.pickysteve.bak`), and is idempotent. YAML/proxy/CLI agents (Goose, Hermes,
Aider, OpenHands, OpenClaw, NanoClaw) print exact manual steps instead of being auto-edited.
*(Applied here to 10 detected agents; all 10 configs parse + carry the entry.)*

The MCP server exposes two tools — **`pick_context(request)`** (returns the focused,
untrusted-data-boundaried skill bundle to inject) and **`list_skills()`**. The proxy runs
`pick()` on the last user message, injects the bundle as a system message, then forwards to
the upstream model — so context-picking happens transparently on every request.

Throughout, substitute your paths:
- `PYBIN` = `<PROJECT_ROOT>\.venv\Scripts\python.exe`  (e.g. `C:\path\to\pickysteve\.venv\Scripts\python.exe`)
- `PROJ`  = `<PROJECT_ROOT>`  (the absolute path to your cloned pickysteve repo)

---

## A. MCP stdio (native, deepest integration)

The same launcher everywhere: **command** `PYBIN`, **args** `["-m","pickysteve.connectors.mcp_server"]`, **cwd** `PROJ`.

### Claude Code
```bash
claude mcp add pickysteve --scope user -- PYBIN -m pickysteve.connectors.mcp_server
```
…or `.mcp.json` / `~/.claude.json`:
```json
{ "mcpServers": { "pickysteve": {
  "command": "PYBIN", "args": ["-m","pickysteve.connectors.mcp_server"], "cwd": "PROJ" } } }
```

### Codex  (`~/.codex/config.toml`)
```toml
[mcp_servers.pickysteve]
command = "PYBIN"
args = ["-m", "pickysteve.connectors.mcp_server"]
cwd = "PROJ"
```

### Cursor  (`.cursor/mcp.json` or `~/.cursor/mcp.json`)
```json
{ "mcpServers": { "pickysteve": {
  "command": "PYBIN", "args": ["-m","pickysteve.connectors.mcp_server"], "cwd": "PROJ" } } }
```

### Windsurf  (`~/.codeium/windsurf/mcp_config.json`)
```json
{ "mcpServers": { "pickysteve": {
  "command": "PYBIN", "args": ["-m","pickysteve.connectors.mcp_server"] } } }
```

### Cline / Roo Code  (VS Code → MCP Servers → "Configure MCP Servers")
```json
{ "mcpServers": { "pickysteve": {
  "command": "PYBIN", "args": ["-m","pickysteve.connectors.mcp_server"], "cwd": "PROJ" } } }
```

### Gemini CLI  (`~/.gemini/settings.json`) and Qwen Code  (`~/.qwen/settings.json`, same schema)
```json
{ "mcpServers": { "pickysteve": {
  "command": "PYBIN", "args": ["-m","pickysteve.connectors.mcp_server"], "cwd": "PROJ" } } }
```

### Goose  (`~/.config/goose/config.yaml`, or `goose configure → Add Extension → Command-line (stdio)`)
```yaml
extensions:
  pickysteve:
    type: stdio
    cmd: PYBIN
    args: ["-m", "pickysteve.connectors.mcp_server"]
    enabled: true
```

### OpenHands  (config.toml)
```toml
[mcp]
stdio_servers = [
  { name = "pickysteve", command = "PYBIN", args = ["-m","pickysteve.connectors.mcp_server"] },
]
```

### GitHub Copilot Agent  (VS Code `.vscode/mcp.json`)
```json
{ "servers": { "pickysteve": {
  "type": "stdio", "command": "PYBIN", "args": ["-m","pickysteve.connectors.mcp_server"] } } }
```

### Kimi Code  (`~/.kimi/config.toml`)
```toml
[mcp_servers.pickysteve]
command = "PYBIN"
args = ["-m", "pickysteve.connectors.mcp_server"]
```

### OpenCode  (`opencode.json` / `~/.config/opencode/opencode.json`)
```json
{ "$schema": "https://opencode.ai/config.json",
  "mcp": { "pickysteve": {
    "type": "local", "command": ["PYBIN","-m","pickysteve.connectors.mcp_server"], "enabled": true } } }
```

### ZeroClaw  (`~/.zeroclaw/config.toml`) — MCP if available, else use the proxy (§B)
```toml
[mcp_servers.pickysteve]
command = "PYBIN"
args = ["-m", "pickysteve.connectors.mcp_server"]
```

---

## B. OpenAI-compatible proxy (for tools without MCP)

Start it once: `PYBIN -m pickysteve.connectors.http_server` (listens on `http://localhost:8077`).
Then point the tool's OpenAI base URL at `http://localhost:8077/v1` (any non-empty API key).

### Aider
```bash
aider --openai-api-base http://localhost:8077/v1 --openai-api-key sk-x --model pickysteve
# or:  export OPENAI_API_BASE=http://localhost:8077/v1
```

### Hermes  (`~/.hermes/config.yaml`)
```yaml
model:
  provider: custom
  base_url: "http://localhost:8077/v1"
```

### ZeroClaw  (`~/.zeroclaw/config.toml`)
```toml
[providers.models.pickysteve]
provider = "openai"
base_url = "http://localhost:8077/v1"
```

### OpenCode / OpenClaw / NanoClaw  (custom OpenAI provider)
Point the provider's `baseURL`/`base_url` at `http://localhost:8077/v1`, model `pickysteve`.

---

## C. Universal fallback — REST, CLI, direct import

Works for anything that can make an HTTP call, run a shell command, or import Python.

```bash
# REST (server from §B running):
curl -s http://localhost:8077/pick -H "Content-Type: application/json" \
  -d '{"request":"audit my AMM for oracle manipulation"}'

# CLI:
PYBIN -m pickysteve "audit my AMM for oracle manipulation" --no-exec

# Direct import (Python agents — OpenClaw/NanoClaw/Hermes if Python):
#   from pickysteve.pipeline import Engine
#   bundle = Engine().pick("audit my AMM for oracle manipulation")
```

---

## Connectivity matrix

| Agent | Best path | Rating |
|---|---|---|
| Claude Code | MCP (`claude mcp add`) | deep |
| Codex | MCP (`config.toml`) | deep |
| Cursor | MCP (`.cursor/mcp.json`) | deep |
| Windsurf | MCP (`mcp_config.json`) | deep |
| Cline | MCP (settings) | deep |
| Roo Code | MCP (settings) | deep |
| Gemini CLI | MCP (`settings.json`) | deep |
| Qwen Code | MCP (`settings.json`) | deep |
| Goose | MCP (config.yaml extension) | deep |
| OpenHands | MCP (config.toml) | deep |
| GitHub Copilot Agent | MCP (`.vscode/mcp.json`) | easy |
| Kimi Code | MCP (`config.toml`) | deep |
| OpenCode | MCP (`opencode.json`) or proxy | deep |
| ZeroClaw | MCP or proxy (`config.toml`) | deep |
| Aider | proxy (`--openai-api-base`) | easy |
| Hermes | proxy (`provider: custom`) | deep |
| OpenClaw | proxy / REST / import | easy |
| NanoClaw | proxy / REST / import | easy |

## Connectivity test — both connectors proven (8/8 PASS)

`eval/test_connectors.py` drives the connectors exactly as a real agent would:

**MCP stdio server**
- `initialize` → `serverInfo.name = pickysteve`, protocol `2024-11-05` ✅
- `tools/list` → advertises `pick_context` + `list_skills` ✅
- `tools/call pick_context("review my rust code…")` → returns the real rust-reviewer
  context block (untrusted-data-boundaried, 1278 chars) ✅
- `tools/call list_skills` → returns the registry ✅

**HTTP / OpenAI proxy**
- `/health` ok · `/v1/models` advertises `pickysteve` ✅
- `POST /pick {"request":"my docker image is too big"}` → `survivors=["docker-optimizer"]` ✅
- `POST /v1/chat/completions` (AMM request) → injects `defi-amm-security` context **and**
  forwards to the upstream model, returning a completion ✅

So any MCP client and any OpenAI-base-URL client can connect with the configs above.

## Research-verified per-tool notes (2025/2026)

- **Claude Code** — `claude mcp add pickysteve --scope user -- …`; for a full model redirect
  instead, set `ANTHROPIC_BASE_URL` at the proxy.
- **Codex** — `codex mcp add pickysteve -- …` *or* `[mcp_servers.pickysteve]` in `config.toml`.
  Custom upstream provider uses `[model_providers.*]` with `wire_api = "responses"` (Chat
  Completions removed in 2026) — so prefer the **MCP** path here.
- **Cursor** — `.cursor/mcp.json` is the deep path; the "Override OpenAI Base URL" toggle only
  affects chat/plan mode (not Composer/inline), so MCP is preferred.
- **Windsurf** — MCP-only (Codeium's model stack is proprietary; no base-URL override). Config at
  `~/.codeium/windsurf/mcp_config.json` (or the Cascade MCP UI).
- **Cline / Roo Code** — MCP via the extension's `cline_mcp_settings.json` / `mcp_settings.json`,
  or `cline mcp install pickysteve -- …`; custom base URL via `cline auth --baseurl …`.
- **OpenHands** — most reliable path is the **proxy**: set the LLM `base_url` (env `LLM_BASE_URL`
  / `*_BASE_URL`) to `http://localhost:8077/v1`.
- **OpenClaw / NanoClaw** — (your tools) MCP (`~/.openclaw/.mcp.json` `mcpServers`) if supported,
  else the proxy via `OPENAI_BASE_URL`, else REST `/pick` or `Engine().pick()` direct import.

## Deeper-integration features added (so connection is not just possible, but good)

1. **`pick_context` tool** returns a self-contained, untrusted-data-boundaried bundle — the
   agent injects it verbatim; no parsing, no trust assumptions.
2. **`list_skills` tool** lets an agent discover the registry up front.
3. **Transparent proxy** — context-picking happens on *every* chat turn with zero prompt
   changes; the response carries a `pickysteve` field (status/survivors/search_query) for
   observability.
4. **Zero extra dependencies** — both servers are stdlib-only, so connecting adds nothing to
   install and can't break the agent's environment.
5. **Graceful degradation** — on `no_confident_match`/blocked, the connectors surface a
   clarifying note rather than dumping low-confidence context.
6. **One launcher, every agent** — the same `-m pickysteve.connectors.mcp_server` command drops
   into all MCP hosts; the same `:8077/v1` base URL drops into all OpenAI-compatible hosts.

## Obsidian second-brain export

```
python -m pickysteve.connectors.obsidian --vault <path-to-vault> [--folder PickySteve] [--stats]
```

Exports the registry as one note per skill under `<vault>/<folder>/Skills/`, plus a
`<folder>/PickySteve Skills.md` MOC index grouped by primary tag. Confusable-pair edges from
`eval/skill_kg.json` render as `[!warning]` callouts with `[[wikilinks]]` to the other skill's
note, so Obsidian's graph view visualizes the confusability graph. `--stats` adds a `picks:`
frontmatter count per skill (from `logs/runs.jsonl` survivors) and a "Most picked" list in the
MOC. Re-running is idempotent and safe — regenerates everything above a `%% your notes below %%`
marker while preserving anything a user typed below it. Stdlib only, no pyyaml.
