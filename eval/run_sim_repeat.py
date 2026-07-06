"""Run the simulation grader N times (one Engine load) and report the consecutive-100%
streak. Used to confirm the system hits 100% ten times in a row (stability/robustness).

Run:  .venv/Scripts/python.exe eval/run_sim_repeat.py [N]   (default N=10)
"""
from __future__ import annotations

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
from pickysteve.pipeline import Engine     # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
TARGET = 10


def grade_once(eng, tasks, text, rr, floor):
    fails = []
    for i, t in enumerate(tasks, 1):
        task, gold, traps = t["task"], t["gold"], t["traps"]
        res = eng.pick(task)
        sv = res["survivors"]
        if gold:
            qs = [task] + (res.get("sub_queries") or [])
            if config.RERANK_MODE != "maxsubq":
                qs = qs[:1]
            def _mx(sid):
                return max(float(rr.raw_scores(q, [text[sid]])[0]) for q in qs)
            gmax = max((_mx(g) for g in gold if g in text), default=0.0)
            tmax = max((_mx(tr) for tr in traps if tr in text), default=0.0)
            accept = set(t.get("accept", []))
            acc_gold = set(gold) | accept
            top1 = bool(sv) and sv[0] in acc_gold
            leak = [tr for tr in traps if tr in sv and tr not in acc_gold]
            # Judge decides on survivors; rank (gmax>tmax) is diagnostic, not a gate.
            if len(gold) > 1:
                ok = all(g in sv for g in gold) and not leak
            else:
                ok = top1 and not leak
        else:
            ok = res["status"] == "no_confident_match" and not sv
        if not ok:
            fails.append((i, t["category"], sv))
    return fails


def main() -> int:
    import os
    tf = os.getenv("PS_SIM_TASKS") or str(config.ROOT / "eval" / "sim_tasks.jsonl")
    tasks = [json.loads(l) for l in Path(tf).read_text(encoding="utf-8").splitlines() if l.strip()]
    eng = Engine(registry_dir=config.ROOT / "eval" / "sim_registry")
    text = {u.skill_id: u.text_for_search for u in eng.units}
    rr, floor = eng.reranker, config.rerank_floor()
    print(f"sim: {len(eng.units)} skills, {len(tasks)} tasks | running {N} reps, target {TARGET}-in-a-row\n")

    streak = best = 0
    for rep in range(1, N + 1):
        fails = grade_once(eng, tasks, text, rr, floor)
        p = len(tasks) - len(fails)
        hundred = not fails
        streak = streak + 1 if hundred else 0
        best = max(best, streak)
        tag = f"100% (streak {streak})" if hundred else f"{p}/{len(tasks)}  FAILS={[f[0] for f in fails]}"
        print(f"  rep {rep:>2}: {tag}")
        if not hundred:
            for fi, cat, sv in fails:
                print(f"          #{fi} ({cat}) survivors={sv}")
        if streak >= TARGET:
            print(f"\n*** reached {TARGET}-in-a-row at rep {rep} ***")
            return 0
    print(f"\nbest streak: {best}/{TARGET}")
    return 0 if best >= TARGET else 1


if __name__ == "__main__":
    raise SystemExit(main())
