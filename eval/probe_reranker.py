"""Head-to-head reranker probe. For each FAILING task, measure whether the gold(s)
outrank ALL traps under two models x two scoring modes:
  models: bge-reranker-base (current)  vs  bge-reranker-v2-m3 (stronger)
  modes : ORIG (request only)          vs  MAXSUBQ (max over request + sub-queries)

'gold_top' = every gold scores strictly above every trap (the ranking the pipeline needs).
Prints a per-model/mode win count over the 19 fails so we can decide whether to upgrade.

Run:  .venv/Scripts/python.exe eval/probe_reranker.py
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pickysteve import config             # noqa: E402
from pickysteve.registry import load_units  # noqa: E402
from pickysteve.rerank import Reranker      # noqa: E402

reg = config.ROOT / "eval" / "sim_registry"
units = load_units(reg)
text = {u.skill_id: u.text_for_search for u in units}
fails = json.loads(Path("logs/fail_records.json").read_text(encoding="utf-8"))


def subs_of(rec):
    try:
        return ast.literal_eval(rec["sub_queries"]) if rec["sub_queries"] not in ("None", "") else []
    except Exception:
        return []


def eval_model(name):
    print(f"\n===== {name} =====", flush=True)
    rr = Reranker(name)
    def sc(q, sid):
        return float(rr.raw_scores(q, [text[sid]])[0]) if sid in text else None
    win = {"ORIG": 0, "MAXSUBQ": 0}
    for r in fails:
        task, gold, traps = r["task"], r["gold"], r["traps"]
        queries = [task] + list(subs_of(r))
        for mode in ("ORIG", "MAXSUBQ"):
            qs = [task] if mode == "ORIG" else queries
            def best(sid):
                vals = [sc(q, sid) for q in qs]
                vals = [v for v in vals if v is not None]
                return max(vals) if vals else -9.0
            gmin = min(best(g) for g in gold)
            tmax = max((best(t) for t in traps), default=-9.0)
            if gmin > tmax:
                win[mode] += 1
    print(f"  gold-outranks-all-traps:  ORIG={win['ORIG']}/{len(fails)}   MAXSUBQ={win['MAXSUBQ']}/{len(fails)}", flush=True)
    return win


for m in ["BAAI/bge-reranker-base", "BAAI/bge-reranker-v2-m3"]:
    try:
        eval_model(m)
    except Exception as e:  # noqa: BLE001
        print(f"  {m} FAILED: {e}", flush=True)
