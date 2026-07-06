"""Lightweight escalation-judge warmer. Loads ONLY the registry (no v2-m3 / no embedder → ~2s
startup) + the pre-dumped judge pools (logs/judge_pools.json), and calls the reasoning judge
(PS_ESCALATION_MODEL) for each task's pool, caching each pick per-call. Because startup is tiny,
the whole runtime window is spent on the slow reasoning calls, and per-call caching makes it fully
resumable across the frequent background teardowns.

Run:  PS_JUDGE_CACHE=... PS_ESCALATION_MODEL=phi4-mini-reasoning:latest \
      .venv/Scripts/python.exe eval/phi4_warm.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pickysteve import config, kg, router      # noqa: E402
from pickysteve.registry import load_units       # noqa: E402

model = os.getenv("PS_ESCALATION_MODEL") or "phi4-mini-reasoning:latest"
units = {u.skill_id: u for u in load_units(config.ROOT / "eval" / "sim_registry")}
pools = json.loads(Path("logs/judge_pools.json").read_text(encoding="utf-8"))


print(f"escalation warm (FOCUSED top-{config.ESCALATION_TOP_K}, short desc): model={model} | "
      f"{len(pools)} pools", flush=True)
for i, p in enumerate(pools, 1):
    if p.get("blocked") or not p.get("pool_ids"):
        continue
    ids = [s for s in p["pool_ids"] if s in units][: config.ESCALATION_TOP_K]
    cand = [(s, units[s].description) for s in ids]  # SHORT one-line descriptions
    notes = kg.relational_notes(ids) if config.ENABLE_KG else None
    t0 = time.perf_counter()
    picks, _ = router.judge_skills(p["task"], cand, relational_notes=notes,
                                   model=model, max_tokens=config.ESCALATION_MAX_TOKENS)
    gold = p.get("gold")
    ok = "OK  " if (gold and picks == gold) else "----"
    print(f"  [{ok}] {i}/{len(pools)} gold={gold} phi4={picks}  ({time.perf_counter()-t0:.0f}s)", flush=True)
print("done", flush=True)
