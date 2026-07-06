<p align="center">
  <img src="assets/pickysteve.png" alt="PickySteve mascot" width="280">
</p>

# PickySteve

A lightweight orchestration layer that uses a **cheap model** to figure out which
skills a request actually needs, retrieves **just those**, and hands a small,
focused, untrusted-data-boundaried context bundle to a **capable model** — instead
of dumping every available tool and document into context on every request.

He's picky about what he loads into context. (That's the whole idea — and the name.)

This repository is **Phase 1 (MVP) only**, built strictly to the architecture spec.
Nothing from Phase 2+ (tracing platform, eval harness, credential vault,
knowledge-graph retrieval, sandbox) is built — by design.

---

## What it does, end to end

```
request
  │
  ▼
1. SECURITY GATE  ── scan the raw request for prompt injection ──► abort if hit
  │
  ▼
2. ROUTER         ── cheap model: vague request → concrete search query
  │
  ▼
3. RETRIEVAL      ── BM25 keyword  +  embedding similarity  ──► fuse (RRF) → N candidates
  │
  ▼
4. SECURITY GATE  ── scan EVERY retrieved candidate's content ──► abort/drop if hit
  │                  (this is the real high-risk surface)
  ▼
5. RERANK         ── cross-encoder vs the ORIGINAL request (not the expanded query)
  │
  ▼
6. FLOOR + DEDUPE ── drop below the calibrated floor; collapse same-skill units
  │                  └─ nothing clears the floor? → ask a clarifying question (don't guess)
  ▼
7. COMPAT CHECK   ── >1 survivor? cheap model judges if they conflict (flag, don't merge)
  │
  ▼
8. ASSEMBLY       ── wrap survivors in an explicit "this is DATA, not instructions" boundary
  │
  ▼
9. EXECUTION      ── capable model does the real work
  │
  ▼
10. LOG           ── append the full trace to logs/runs.jsonl (the only Phase-1 observability)
```

## The stack (and why)

| Role | Choice | Note |
|---|---|---|
| Runtime | **Python 3.11** via `uv` | The default Python here is 3.14, which still has shaky `torch` wheels. `uv` pins an isolated 3.11 venv where the ML stack is stable. |
| Security gate | **`stackone-defender[onnx]`** | The *real* StackOne defender (Python port, v0.7.2), not a regex placeholder. Bundled ~22MB ONNX classifier; no download. |
| Router / compat / clarify / execution | local Ollama `qwen3:8b` via the **native `/api/chat` (`think:false`)** | Runs with no cloud key. The OpenAI-compat endpoint does *not* honor thinking control for qwen3 (dumps output into a `reasoning` channel → empty `content`, ~20× slower), so the client uses the native endpoint by default. Set `PS_OLLAMA_NATIVE=0` / `PS_LLM_BASE_URL` for any OpenAI-compatible host. |
| Retrieval | **`rank_bm25`** + **`sentence-transformers`** embeddings, fused with RRF | Hybrid keyword + dense. No knowledge graph (out of scope for Phase 1). |
| Reranker | **`BAAI/bge-reranker-base`** cross-encoder | Exactly the model the spec names. Its output is a logit, not a probability — the floor is **calibrated**, never guessed. |
| Logging | flat **JSONL** | Manual review is the Phase-1 eval process. |

Total Phase-1 dependencies: `stackone-defender`, `rank-bm25`, `sentence-transformers`,
`openai`, `numpy` — the minimal set the spec prescribes.

## Two decisions the spec left open (decided + documented)

- **Retrieval unit (§2.3):** *each markdown file is one retrieval unit.* A skill folder
  with several files (see `registry/rag-architecture/`) yields multiple units sharing a
  `skill_id`. After reranking, units from the same skill are **collapsed to the best one**
  in assembly, so the execution model never receives three chunks of one skill.
- **Gate policy on a poisoned retrieval (§2.1):** default `RETRIEVED_INJECTION_POLICY=abort`
  — if a *retrieved* candidate trips the gate (high-risk), the whole request aborts.
  (`drop` — discard just that candidate and continue — is the documented alternative.)
  For allowed-but-sanitized content we use the **Tier-1-sanitized** text downstream
  (defense-in-depth) and log that sanitization happened.

## Refinements after a 21-agent adversarial review

The first validation surfaced three failures; fixing them (and adversarially reviewing
the fixes) added these mechanisms. See `FINDINGS.md` for the full before/after.

- **Tier-3 escalation (gate, request path only):** a legitimate question *about* prompt
  injection was being blocked. The request gate now enables the defender's Tier-3 LLM hook
  over the gray band **`[0.64, 0.85)`** — i.e. just *above* the model's calibrated 0.64
  block threshold — so a cheap adjudicator can *rescue* a would-be block (never flip a
  would-be allow), while near-certain attacks (≥0.85) still hard-block without consulting
  it. Retrieved third-party content **never** escalates (strict gate).
- **Multi-intent router + §2.4-safe rescue:** the router emits sub-queries; retrieval unions
  across them (recall). Reranking stays governed by the **original request** (§2.4) — only a
  *genuinely compound* request (≥2 distinct sub-intents) also maxes over its sub-queries, to
  surface a secondary intent the full-request score would bury.
- **Relative-dominance gate:** a secondary skill is kept only if it scores ≥ `DOMINANCE_RATIO`
  (0.08) × the top skill — keeping PickySteve *picky* instead of dumping marginal tag-alongs.
- **Honest #13 fix:** a correct skill that the reranker under-scored was fixed by **enriching
  the skill doc** with real symptom vocabulary, not by lowering the floor onto leaked data.
  The floor is recalibrated on a leakage-free labeled set (with hard-negatives).

## Setup

```bash
# from this directory (Windows; uv 0.10+, Ollama with qwen3:8b running locally)
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
```

## Use

```bash
# 1) Calibrate the reranker floor on the labeled set (writes eval/calibrated_floor.json)
.venv/Scripts/python.exe eval/calibrate.py

# 2) Run a single request
.venv/Scripts/python.exe -m pickysteve "review my Rust endpoint for security and REST design"

# 3) Run the 18 example requests end to end (traces -> logs/runs.jsonl)
.venv/Scripts/python.exe eval/run_examples.py          # add --no-exec to skip the execution model

# 4) The mandatory security-gate test
.venv/Scripts/python.exe tests/test_security_gate.py
```

Config is all environment variables (`PS_*`) — see `pickysteve/config.py`.

## Core principle

Confidence / relevance scores measure **topical similarity, not correctness**. Nothing
here claims a retrieval was "right" — only that it was "plausible." All retrieved content
is treated as **low-trust data**, never as instructions.

## Known open logic gaps (carried forward from the spec — not pretended solved)

1. **Confidence ≠ correctness.** The rerank score is topical similarity, not outcome quality. No outcome feedback loop exists; that needs labeled real results over time.
2. **The router can be wrong.** Intent decomposition for vague/compound requests is itself a hard reasoning problem.
3. **Skill-conflict resolution is unsolved.** We *flag* conflicts (compat check) rather than resolve them.
4. **"Compatible skills can be combined" has no concrete definition.** No automatic skill-merging.
5. **No recency/trust weighting in retrieval.** A stale skill ranks the same as a fresh one at equal relevance (we *flag* staleness, we don't down-weight it).

## Phase 1 non-goals (intentionally absent)

No knowledge graph / LightRAG · no LangGraph or state-machine framework · no external
tracing (Laminar/Langfuse) · no credential vault · no automated eval harness
(DeepEval/Ragas) · no sandbox runtime. Each is added in Phase 2 **only** when a real,
observed Phase-1 failure justifies it.

See **[FINDINGS.md](FINDINGS.md)** for the calibrated floor and the 18-request validation results,
**[TEST_REPORT.md](TEST_REPORT.md)** for the stress/security/accuracy campaign, and
**[INTEGRATIONS.md](INTEGRATIONS.md)** for connecting PickySteve to 18 coding agents (MCP server +
OpenAI-compatible proxy + REST/CLI).

## Connect it to your coding agent

```bash
# MCP (Claude Code, Codex, Cursor, Windsurf, Cline, Roo, Gemini CLI, Qwen Code, Goose, …):
.venv/Scripts/python.exe -m pickysteve.connectors.mcp_server      # exposes pick_context + list_skills

# OpenAI-compatible proxy (Aider, Hermes, ZeroClaw, …): point the tool's base URL at :8077/v1
.venv/Scripts/python.exe -m pickysteve.connectors.http_server     # /pick + /v1/chat/completions
```
