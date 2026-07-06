"""Lightweight router-cache warmer. Loads ONLY the router (no Engine/reranker),
loops every task, and calls router.route() — which writes each result to the
PS_ROUTER_CACHE JSON per-call. Cheap startup + incremental writes = fully
resumable across kills. Run once to warm; the grader then runs cache-fast.

Run:  PS_ROUTER_CACHE=... PS_SIM_TASKS=... .venv/Scripts/python.exe eval/warm_cache.py
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

from pickysteve import config, router  # noqa: E402

tf = os.getenv("PS_SIM_TASKS") or str(config.ROOT / "eval" / "sim_tasks.jsonl")
tasks = [json.loads(l) for l in Path(tf).read_text(encoding="utf-8").splitlines() if l.strip()]
cache = router._cache_get()
if cache is None:
    print("PS_ROUTER_CACHE not set — nothing to warm."); raise SystemExit(1)

todo = [t for t in tasks if t["task"] not in cache]
print(f"warming: {len(tasks)} tasks, {len(cache)} cached, {len(todo)} to route", flush=True)
t0 = time.perf_counter()
for i, t in enumerate(todo, 1):
    router.route(t["task"])          # writes to cache per-call
    if i % 10 == 0 or i == len(todo):
        print(f"  {i}/{len(todo)}  (cache now {len(cache)})", flush=True)
print(f"done in {time.perf_counter()-t0:.0f}s — cache {len(cache)}/{len(tasks)}", flush=True)
