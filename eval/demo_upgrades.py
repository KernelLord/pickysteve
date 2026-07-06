"""Demonstrate the two upgrades on the UNSEEN held-out set:
  1. Recall upgrade — gold-in-pool rate with RECALL_ALL on vs off (the rescued retrieval misses).
  2. Conformal abstention — coverage (gold in the set), avg set size, and the escalation split
     (singletons routed cheaply vs ambiguous cases that a connector would send to the frontier judge).

Conformal is judge-independent (computed from the reranker scores), so run with the judge off for speed.
Run:  PS_ENABLE_CONFORMAL=1 PS_RERANK_CACHE=... .venv/Scripts/python.exe eval/demo_upgrades.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pickysteve import config          # noqa: E402
from pickysteve.pipeline import Engine   # noqa: E402


def gold_in_pool(eng, tasks):
    hits = 0
    misses = []
    for t in tasks:
        res = eng.run(t["task"], do_execute=False)
        ids = {c["skill_id"] for c in (res.detail.get("candidates") or []) if c["rerank"] is not None}
        if t["gold"][0] in ids:
            hits += 1
        else:
            misses.append((t["gold"][0], t["task"][:55]))
    return hits, misses


def main() -> int:
    held = [json.loads(l) for l in Path("eval/sim_tasks_heldout.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    held = [t for t in held if t.get("gold") and len(t["gold"]) == 1]
    eng = Engine(registry_dir=config.ROOT / "eval" / "sim_registry")

    # 1. RECALL — gold-in-pool with recall-all ON (default). Then flip it OFF for the same engine.
    on_hits, on_miss = gold_in_pool(eng, held)
    config.RECALL_ALL = False
    off_hits, off_miss = gold_in_pool(eng, held)
    config.RECALL_ALL = True
    print(f"\n=== RECALL UPGRADE (gold reaches the reranked pool) ===")
    print(f"  RECALL_ALL on : {on_hits}/{len(held)} golds in pool")
    print(f"  RECALL_ALL off: {off_hits}/{len(held)} golds in pool")
    rescued = {m[1] for m in off_miss} - {m[1] for m in on_miss}
    print(f"  rescued by recall-all: {len(rescued)}")
    for g, tk in off_miss:
        if tk in rescued:
            print(f"     + {g}  ::  {tk}")

    # 2. CONFORMAL — coverage + escalation split (judge-independent; run with judge off for speed)
    covered = sizes = ambiguous = 0
    from pickysteve import conformal
    cal = conformal.load()
    for t in held:
        res = eng.run(t["task"], do_execute=False)
        cset = res.conformal_set
        if t["gold"][0] in cset:
            covered += 1
        sizes += len(cset)
        if res.ambiguous:
            ambiguous += 1
    n = len(held)
    print(f"\n=== CONFORMAL ABSTENTION (alpha={cal.alpha}, q_hat={cal.q_hat:.3f}) ===")
    print(f"  coverage (gold in set): {covered}/{n} = {covered/n:.0%}  (target >= {1-cal.alpha:.0%})")
    print(f"  avg set size          : {sizes/n:.2f}")
    print(f"  singletons (route cheap): {n-ambiguous}/{n} = {(n-ambiguous)/n:.0%}")
    print(f"  ambiguous (escalate)    : {ambiguous}/{n} = {ambiguous/n:.0%}  <- frontier judge only here")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
