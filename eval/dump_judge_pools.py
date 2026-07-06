"""Dump the exact judge POOL for each task — the ordered (skill_id, description) list the
pipeline hands the LLM judge. A capable-model judge (run offline via a workflow) then picks
from these pools, and its picks are written back into a judge cache keyed EXACTLY as the live
pipeline expects (request + '||' + '|'.join(pool_ids)). This lets us measure the pipeline's
ceiling with a strong judge without changing the live code path.

Run:  PS_*CACHE=... PS_SIM_TASKS=... .venv/Scripts/python.exe eval/dump_judge_pools.py
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

from pickysteve import assembly, config, security_gate  # noqa: E402
from pickysteve.pipeline import Engine                    # noqa: E402

tf = os.getenv("PS_SIM_TASKS") or str(config.ROOT / "eval" / "sim_tasks.jsonl")
tasks = [json.loads(l) for l in Path(tf).read_text(encoding="utf-8").splitlines() if l.strip()]
eng = Engine(registry_dir=config.ROOT / "eval" / "sim_registry")

import pickysteve.router as router  # noqa: E402
out = []
for t in tasks:
    task = t["task"]
    if not security_gate.scan(task, "user_request").allowed:
        out.append({"task": task, "gold": t["gold"], "traps": t["traps"], "blocked": True, "pool": []})
        continue
    ro = router.route(task)
    cand_map = {}
    for q in (ro.sub_queries or [ro.search_query]):
        for c in eng.retriever.search(q):
            ex = cand_map.get(c.unit.unit_id)
            if ex is None or c.rrf > ex.rrf:
                cand_map[c.unit.unit_id] = c
    kept = []
    for c in cand_map.values():
        g = security_gate.scan(c.unit.content, "retrieved_skill")
        if g.allowed:
            kept.append(c)
    reranked = eng.reranker.score_multi(task, ro.sub_queries, kept)
    pool = assembly.dedupe_by_skill(
        [c for c in reranked if c.rerank is not None and c.rerank >= config.JUDGE_PREFLOOR]
    )[: config.JUDGE_TOP_K]
    out.append({
        "task": task, "gold": t["gold"], "traps": t["traps"], "blocked": False,
        "pool_ids": [c.unit.skill_id for c in pool],
        "pool": [{"id": c.unit.skill_id, "desc": c.unit.description} for c in pool],
    })
Path("logs/judge_pools.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
n_pool = sum(1 for r in out if r.get("pool_ids"))
print(f"dumped {len(out)} tasks ({n_pool} with a non-empty judge pool) -> logs/judge_pools.json")
