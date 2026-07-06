"""Two-tier router evaluation on the UNSEEN held-out set.

Tier 1 (cheap): full local pipeline with the qwen3 judge + the conformal gate.
  - conformal set == 1 member  -> route the local answer directly
  - set != 1 (multi or empty)  -> ESCALATE
Tier 2 (frontier): the Claude blind judge's cached pick answers the escalated cases.

Reports: escalation fraction, per-tier accuracy, combined top-1, and conformal coverage.

Run:  PS_ENABLE_CONFORMAL=1 PS_JUDGE_CACHE=<qwen3 held cache> ... two_tier_eval.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pickysteve import config, conformal   # noqa: E402
from pickysteve.pipeline import Engine       # noqa: E402


def _norm(s: str) -> str:
    s = s.replace("`", "").replace("—", "-").replace("–", "-").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def main() -> int:
    held = [json.loads(l) for l in Path("eval/sim_tasks_heldout_clean.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    held = [t for t in held if t.get("gold") and len(t["gold"]) == 1]
    claude = json.loads(Path("logs/judge_cache_claude_held.json").read_text(encoding="utf-8"))
    eng = Engine(registry_dir=config.ROOT / "eval" / "sim_registry")
    cal = conformal.load()
    print(f"gate: method={cal.method} alpha={cal.alpha} q_hat={cal.q_hat:.3f} "
          f"temp={cal.temp} bonus={cal.bonus} (n={cal.n})\n")

    n = len(held)
    esc = cov = t1_right_direct = t2_right = 0
    routed = escalated = 0
    for t in held:
        gold = t["gold"][0]
        acc = set(t.get("accept") or []) | {gold}
        res = eng.run(t["task"], do_execute=False)
        cset = res.conformal_set
        local = res.survivors[0] if res.survivors else None
        if gold in cset:
            cov += 1
        if len(cset) == 1:
            routed += 1
            pick = cset[0]
            if pick in acc:
                t1_right_direct += 1
        else:
            escalated += 1
            cp = claude.get("claude||TASK||" + _norm(t["task"])) or []
            pick = cp[0] if cp else (local or (cset[0] if cset else None))
            if pick in acc:
                t2_right += 1
    combined = t1_right_direct + t2_right
    print(f"held-out tasks            : {n}")
    print(f"conformal coverage        : {cov}/{n} = {cov/n:.0%}  (target >= {1-cal.alpha:.0%})")
    print(f"routed cheap (singleton)  : {routed}/{n} = {routed/n:.0%} -> correct {t1_right_direct}/{routed}")
    print(f"escalated to frontier     : {escalated}/{n} = {escalated/n:.0%} -> correct {t2_right}/{escalated}")
    print(f"COMBINED top-1            : {combined}/{n} = {combined/n:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
