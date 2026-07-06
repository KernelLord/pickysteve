"""Grade PickySteve on the simulation registry against designer-known gold rankings.

Two measures per task:
  * end-to-end — what PickySteve actually surfaces (survivors), top-1 correctness, trap leakage.
  * pure ranking — the reranker's score for the gold skill vs each trap (does gold > every trap?).

Run:  .venv/Scripts/python.exe eval/run_sim.py
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


def main() -> int:
    import os
    tf = os.getenv("PS_SIM_TASKS") or str(config.ROOT / "eval" / "sim_tasks.jsonl")
    tasks = [json.loads(l) for l in Path(tf).read_text(encoding="utf-8").splitlines() if l.strip()]
    reg = config.ROOT / "eval" / "sim_registry"
    eng = Engine(registry_dir=reg)
    text = {u.skill_id: u.text_for_search for u in eng.units}
    rr = eng.reranker
    floor = config.rerank_floor()
    print(f"sim registry: {len(eng.units)} skills | floor={floor:.4f} | {len(tasks)} tasks\n")

    n_ans = n_top1 = n_rank = n_leak = n_pass = n_nm = n_nm_ok = 0

    def sc(queries, sid):
        # Score a skill under the SAME scheme the pipeline uses: max over the original request
        # and the router's sub-queries (config.RERANK_MODE). Using ORIG-only here while the
        # pipeline surfaces via maxsubq would falsely fail obliquely-phrased golds.
        if sid not in text:
            return None
        qs = queries if config.RERANK_MODE == "maxsubq" else queries[:1]
        return round(max(float(rr.raw_scores(q, [text[sid]])[0]) for q in qs), 3)

    for i, t in enumerate(tasks, 1):
        task, gold, traps = t["task"], t["gold"], t["traps"]
        res = eng.pick(task)
        sv = res["survivors"]
        queries = [task] + (res.get("sub_queries") or [])
        gold_sc = {g: sc(queries, g) for g in gold}
        trap_sc = {tr: sc(queries, tr) for tr in traps}

        if gold:
            n_ans += 1
            # `accept` = also-valid answers for label-contested tasks (an independent frontier
            # blind judge + cleanlab both disagreed with the single gold → the label is debatable).
            accept = set(t.get("accept", []))
            acc_gold = set(gold) | accept
            gmax = max(gold_sc.values()) if gold_sc else 0.0
            tmax = max(trap_sc.values()) if trap_sc else 0.0
            top1 = bool(sv) and sv[0] in acc_gold
            rank_ok = gmax > tmax  # DIAGNOSTIC only: pure cross-encoder quality
            leak = [tr for tr in traps if tr in sv and tr not in acc_gold]
            # PASS is judged on the system's actual OUTPUT (survivors) — the LLM judge is the
            # decider and legitimately overrides the cross-encoder's raw ordering, so a task
            # passes when it surfaces the gold(s) and leaks no trap, regardless of rank_ok.
            if len(gold) > 1:
                passed = all(g in sv for g in gold) and not leak
            else:
                passed = top1 and not leak
            n_top1 += top1; n_rank += rank_ok; n_leak += bool(leak); n_pass += passed
            print(f"[{'PASS' if passed else 'FAIL'}] #{i:<2} {t['category']:16} {task[:58]}")
            print(f"      gold {gold} -> {gold_sc}")
            print(f"      trap -> {trap_sc}")
            print(f"      survivors={sv}  | top1={top1}  gold>trap={rank_ok}  trap_leak={leak or '0'}")
            print(f"      why: {t['rationale']}")
            if not passed:
                cands = res.get("candidates") or []
                cstr = " ".join(f"{c['skill_id']}={c['rerank']}" for c in cands[:6])
                retr = [g for g in gold if any(c["skill_id"] == g for c in cands)]
                print(f"      DIAG sub_queries={res.get('sub_queries')}")
                print(f"      DIAG reranked: {cstr}")
                print(f"      DIAG gold retrieved={retr} of {gold} | floor={floor}")
        else:
            n_nm += 1
            ok = res["status"] == "no_confident_match" and not sv
            n_nm_ok += ok; n_pass += ok
            print(f"[{'PASS' if ok else 'FAIL'}] #{i:<2} no-match         {task[:58]}")
            print(f"      status={res['status']} survivors={sv}  (expected: reject)")
        print()

    total = len(tasks)
    print("=" * 60)
    print(f"  overall PASS         : {n_pass}/{total}  ({n_pass/total:.0%})")
    print(f"  top-1 correct        : {n_top1}/{n_ans}  (answerable)")
    print(f"  gold outranks traps  : {n_rank}/{n_ans}  (pure reranker quality)")
    print(f"  tasks with trap leak : {n_leak}/{n_ans}")
    print(f"  no-match handled     : {n_nm_ok}/{n_nm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
