---
name: Bug report
about: Something in the pipeline (gate / router / retrieval / rerank / assembly) misbehaved
title: "[bug] "
labels: bug
---

**What happened**
A clear description of the wrong behavior.

**Request that triggered it**
```
(the exact request text you sent)
```

**Expected skill / outcome**
What should have been picked (or: expected `no_confident_match`).

**Actual result**
Paste the relevant `pick()` output or the response body, and, if you have it, the
matching entry from `logs/runs.jsonl`.

**Environment**
- OS:
- Python version:
- Ollama model (`PS_LLM_MODEL` or default `qwen3:8b`):
- Connector in use (MCP / HTTP proxy / direct import):
- Relevant `PS_*` env overrides, if any:

**Security-relevant?**
If this is a gate false-positive/false-negative or a prompt-injection bypass, say so
explicitly and please avoid posting a working exploit payload in a public issue —
email the maintainer directly and open a redacted issue instead.
