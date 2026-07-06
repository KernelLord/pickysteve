"""Calibrate the split-conformal threshold q̂ for the router.

For each labelled calibration task, run the FULL pipeline (judge ON — the conformal score function
is judge-adjusted), take the deduped top-K pool scores plus the judge's picks, and record
(adjusted_scores, gold). Sweep (temp, bonus) to minimize average set size — coverage holds by
construction for any fixed pair; saturated thresholds (q̂ >= 0.999 → float-artifact sets) are
rejected. Writes eval/conformal_cal.json.

Calibrate on the SEEN tasks (base + harder); evaluate coverage on the UNSEEN held-out separately.

Run:  PS_JUDGE_CACHE=<merged base+harder cache> PS_RERANK_CACHE=... \
      .venv/Scripts/python.exe eval/calibrate_conformal.py
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

from pickysteve import config, conformal        # noqa: E402
from pickysteve.pipeline import Engine            # noqa: E402


def pool_scores(res, k):
    best: dict[str, float] = {}
    for c in (res.detail.get("candidates") or []):
        if c["rerank"] is None:
            continue
        if c["skill_id"] not in best or c["rerank"] > best[c["skill_id"]]:
            best[c["skill_id"]] = c["rerank"]
    return dict(sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:k])


def main() -> int:
    files = (os.getenv("PS_CAL_TASKS")
             or f"{config.ROOT/'eval'/'sim_tasks.jsonl'},{config.ROOT/'eval'/'sim_tasks_harder.jsonl'}"
             ).split(",")
    eng = Engine(registry_dir=config.ROOT / "eval" / "sim_registry")
    scored, seen = [], set()   # (raw_pool_scores, judge_picks, gold)
    for f in files:
        for line in Path(f.strip()).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            t = json.loads(line)
            if not t.get("gold") or len(t["gold"]) != 1 or t["task"] in seen:
                continue
            seen.add(t["task"])
            res = eng.run(t["task"], do_execute=False)
            scored.append((pool_scores(res, config.CONFORMAL_POOL_K), list(res.survivors), t["gold"][0]))
    present = sum(1 for c, _p, g in scored if g in c)
    judged_right = sum(1 for _c, p, g in scored if p and p[0] == g)
    print(f"collected {len(scored)} tasks: gold-in-pool {present}, judge-top1-right {judged_right}")
    # (temp, bonus) SWEEP. Raw reranker scores alone can't give tight sets (on adjacent-skill
    # confusions the reranker's top-1 is a trap only the judge corrects), so the score function
    # adds `bonus` to the judge's picks. Coverage holds by construction for any fixed (temp, bonus);
    # pick the pair minimizing average set size. Saturated q̂ (>= 0.999) means the sets are governed
    # by float rounding, not statistics — reject those regimes outright.
    best = None   # keyed by gate utility: (singleton_rate desc, avg_set asc)
    for method in ("lac", "aps"):
        for bonus in (0.0, 0.25, 0.5, 1.0, 2.0):
            adj = [(conformal.adjust(c, p, bonus), g) for c, p, g in scored]
            for temp in (0.05, 0.1, 0.2, 0.3, 0.5, 1.0):
                cal = conformal.calibrate(adj, temp=temp, bonus=bonus, method=method)
                if cal.q_hat >= 0.999:
                    continue  # saturated — float-artifact regime
                sizes = [len(conformal.prediction_set(c, cal)) for c, g in adj if c]
                avg = sum(sizes) / len(sizes)
                singles = sum(1 for s in sizes if s == 1) / len(sizes)
                print(f"  {method} bonus={bonus:<4} temp={temp:<4} q_hat={cal.q_hat:.4f} "
                      f"avg_set={avg:.2f} singletons={singles:.0%}")
                key = (-singles, avg)   # a gate is useful in proportion to its singleton rate
                if best is None or key < best[0]:
                    best = (key, cal, avg, singles)
    if best is None:
        print("ERROR: every configuration saturated — score function cannot separate golds.")
        return 1
    _, cal, avg, singles = best
    conformal.save(cal)
    print(f"\ncalibrated on {cal.n} tasks (gold-in-pool {present}/{len(scored)}) alpha={cal.alpha} "
          f"method={cal.method} temp={cal.temp} bonus={cal.bonus} → q_hat={cal.q_hat:.4f} "
          f"avg_set={avg:.2f} singletons={singles:.0%}")
    print(f"written: {config.CONFORMAL_CAL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
