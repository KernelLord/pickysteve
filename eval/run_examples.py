"""Run the example requests through the full pipeline and print a compact summary.
Full traces are appended to logs/runs.jsonl (spec §2.7).

Run:  .venv/Scripts/python.exe eval/run_examples.py [--no-exec]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pickysteve import config            # noqa: E402
from pickysteve.pipeline import Engine   # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    no_exec = "--no-exec" in sys.argv
    reqs = [
        l.strip()
        for l in (config.ROOT / "eval" / "example_requests.txt").read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    ]
    eng = Engine()
    print(f"floor={config.rerank_floor():.4f}  registry={len(eng.units)} units  "
          f"exec={'off' if no_exec else 'on'}\n")
    if eng.stale_units:
        print(f"[stale units: {', '.join(eng.stale_units)}]\n")

    counts: dict[str, int] = {}
    for i, r in enumerate(reqs, 1):
        res = eng.run(r, do_execute=not no_exec)
        counts[res.status] = counts.get(res.status, 0) + 1
        cands = res.detail.get("candidates") or []
        top = ", ".join(f"{c['skill_id']}={c['rerank']}" for c in cands[:3])
        print(f"#{i:<2} [{res.status:<18}] {r[:64]}")
        print(f"     query    : {res.search_query[:80]}")
        print(f"     top3     : {top}")
        if res.survivors:
            print(f"     survivors: {', '.join(res.survivors)}")
        comp = res.detail.get("compatibility")
        if comp:
            print(f"     compat   : {comp['compatible']} — {comp['reason'][:70]}")
        if res.status == "no_confident_match":
            best = res.detail.get("best_rerank")
            print(f"     best={best} (< floor)  clarifying Q: {res.output[:70]}")
        print()

    print("summary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"traces appended to {config.LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
