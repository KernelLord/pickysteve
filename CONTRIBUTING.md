# Contributing to PickySteve

PickySteve is Phase 1 (MVP) only, built strictly to an architecture spec — see the
README's "Phase 1 non-goals" before proposing new subsystems (tracing, standing eval
harness, credential vault, sandbox). Those are added only when a real, observed
Phase-1 failure justifies them.

## Dev setup

```bash
# from the repo root (Windows; uv 0.10+, Ollama with qwen3:8b running locally)
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
```

Or with plain `pip`:

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Models are served locally via **Ollama**, default `qwen3:8b`:

```bash
ollama pull qwen3:8b
ollama serve
```

Config is all `PS_*` environment variables — see `pickysteve/config.py`. The client
uses Ollama's **native** `/api/chat` endpoint (`think:false`) by default, not the
OpenAI-compat one — the compat endpoint doesn't honor thinking control for qwen3.

## Running the eval / test suites

```bash
# Ollama-free, no downloads — pure Python, run this before every commit (<1s)
.venv/Scripts/python.exe eval/test_gate_security.py

# Requires the real ONNX defender + a running Ollama (router/judge calls, HF model downloads
# for the reranker/embeddings on first run)
.venv/Scripts/python.exe tests/test_security_gate.py
.venv/Scripts/python.exe tests/test_fixes.py

# Routing-quality trifecta — requires Ollama + calibrated floor (eval/calibrate.py first)
.venv/Scripts/python.exe eval/run_sim.py                          # sim_registry, PS_SIM_TASKS override
PS_SIM_TASKS=eval/sim_tasks_harder.jsonl .venv/Scripts/python.exe eval/run_sim.py
PS_SIM_TASKS=eval/sim_tasks_heldout.jsonl .venv/Scripts/python.exe eval/run_sim.py
```

CI (`.github/workflows/ci.yml`) only runs `eval/test_gate_security.py` — everything
else needs a live Ollama and/or first-run Hugging Face model downloads, so it's a local
gate, not (yet) a CI gate.

**Any change that can affect routing quality (router prompts, retrieval, reranker,
floor/dedupe, dominance ratio, compat check) must re-run the trifecta
(base/harder/held-out `run_sim.py` suites) before merge** and report the resulting
pass rate in the PR description. Don't merge a routing change on vibes.

## Code style

Match what's already there — no new formatter/linter config, no reformatting unrelated
lines. Broadly: `from __future__ import annotations`, type hints on public functions,
env-var config through `pickysteve/config.py` (no ad-hoc `os.getenv` scattered through
modules), fail-closed on anything security-gate related, and plain scripts over pytest
for eval/test runners (keeps the dependency list minimal per spec §6.5).

## Opening a PR

- Small, focused diffs. If it touches `security_gate.py` or `assembly.py`, call that out
  explicitly in the PR description — those are the highest-risk-surface files.
- If you found or fixed a real bug during review, add a regression check to
  `eval/test_gate_security.py` (see its docstring for the pattern: one `check()` per
  invariant, tied to the bug that was live).
- No PyPI package or `pyproject.toml` yet — don't add packaging config in an unrelated PR.

## Reporting issues

Open an issue with a failing request + the skill you expected, or a PR against a
`registry/*.md` skill doc if it's a routing/content problem rather than a code bug.
