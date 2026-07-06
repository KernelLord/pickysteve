"""Probe: for each FAILING task, compare the reranker score of the gold vs the traps
under two scoring schemes:
  (A) ORIGINAL request only            (current pipeline)
  (B) MAX(original, each sub-query)    (candidate fix — use the router's reformulations)

Prints, per fail: does gold clear floor under B? does any trap ALSO clear floor / beat gold
under B (the inflation risk)? Net verdict per task: FIXED / STILL-MISS / NEW-LEAK.

Run:  .venv/Scripts/python.exe eval/probe_subq.py
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
rr = Reranker()
floor = config.rerank_floor()
fails = json.loads(Path("logs/fail_records.json").read_text(encoding="utf-8"))
print(f"floor={floor:.4f}  |  {len(fails)} fails\n")


def raw(q, sid):
    if sid not in text:
        return None
    return float(rr.raw_scores(q, [text[sid]])[0])


def subs_of(rec):
    try:
        return ast.literal_eval(rec["sub_queries"]) if rec["sub_queries"] not in ("None", "") else []
    except Exception:
        return []


fixed = still = leak = 0
for r in fails:
    task, gold, traps = r["task"], r["gold"], r["traps"]
    sqs = subs_of(r)
    queries = [task] + list(sqs)
    def best(sid):
        vals = [raw(q, sid) for q in queries]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else None
    def orig(sid):
        return raw(task, sid)
    gB = {g: best(g) for g in gold}
    tB = {t: best(t) for t in traps}
    gA = {g: orig(g) for g in gold}
    # verdict for single-gold; multi-gold checks all golds
    gminB = min([v for v in gB.values() if v is not None], default=0.0)
    tmaxB = max([v for v in tB.values() if v is not None], default=0.0)
    gmaxB = max([v for v in gB.values() if v is not None], default=0.0)
    # under B: all golds clear floor AND gold(min) > tmax  => single-gold: gold>floor and gold>tmax
    if len(gold) == 1:
        ok = (gmaxB >= floor) and (gmaxB > tmaxB)
    else:
        ok = all((v or 0) >= floor for v in gB.values()) and (gminB > tmaxB)
    tleak = any((v or 0) >= floor and (v or 0) >= gmaxB for v in tB.values())
    tag = "FIXED " if ok else ("LEAK  " if tleak else "STILL ")
    if ok: fixed += 1
    elif tleak: leak += 1
    else: still += 1
    ga = " ".join(f"{g}={gA[g]:.4f}" for g in gold)
    gb = " ".join(f"{g}={gB[g]:.4f}" for g in gold)
    tb = " ".join(f"{t}={tB[t]:.4f}" for t in traps)
    print(f"[{tag}] #{r['fid']}")
    print(f"    goldA {ga}")
    print(f"    goldB {gb}   (best over {len(queries)} queries)")
    print(f"    trapB {tb}")
print(f"\nUnder MAX(orig, sub-queries):  FIXED={fixed}  STILL-MISS={still}  NEW/STILL-LEAK={leak}  of {len(fails)}")
