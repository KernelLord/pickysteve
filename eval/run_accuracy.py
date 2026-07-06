"""Accuracy test on a HELD-OUT labeled set (disjoint from calibration + the original
18-request validation). Computes top-1 accuracy, full-recall, false-positive rate,
off-domain rejection, and MRR.

Run:  .venv/Scripts/python.exe eval/run_accuracy.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
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
    items = [json.loads(l) for l in (config.ROOT / "eval" / "accuracy_set.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    eng = Engine()
    print(f"held-out set: {len(items)} requests  floor={config.rerank_floor():.4f}\n")

    rows = []
    for i, it in enumerate(items, 1):
        res = eng.run(it["request"], do_execute=False)
        survivors = res.survivors or []
        cands = [c["skill_id"] for c in (res.detail.get("candidates") or [])]
        expected = it["expected"]
        ok_set = set(expected) | set(it.get("acceptable", []))
        rejected = res.status in ("no_confident_match", "blocked_request")

        if not expected:  # off-domain or deliberately-vague: rejection (or only-acceptable) is right
            if it.get("acceptable"):
                correct = rejected or (bool(survivors) and set(survivors) <= ok_set)
            else:
                correct = rejected and not survivors
            top1 = correct
            recall = correct
            fps = [] if correct else survivors
            mrr = 0.0
        else:
            top1 = bool(survivors) and survivors[0] in ok_set
            recall = set(expected) <= set(survivors)
            fps = [s for s in survivors if s not in ok_set]
            # MRR of the first expected skill in the reranked candidate order
            ranks = [cands.index(s) + 1 for s in expected if s in cands]
            mrr = 1.0 / min(ranks) if ranks else 0.0
            correct = recall and not fps

        rows.append({**it, "status": res.status, "survivors": survivors,
                     "top1": top1, "recall": recall, "fps": fps, "mrr": mrr, "correct": correct})
        flag = "OK " if correct else "XX "
        print(f"{flag}#{i:<2} [{it['category']:<16}] {it['request'][:52]!r}")
        print(f"      exp={expected} got={survivors} status={res.status}" + (f" FP={fps}" if fps else ""))

    answ = [r for r in rows if r["expected"]]
    offd = [r for r in rows if not r["expected"]]

    def pct(items, key):
        return (sum(1 for r in items if r[key]) / len(items)) if items else 0.0

    print("\n================ ACCURACY METRICS ================")
    print(f"  overall correct        : {pct(rows,'correct'):.1%}  ({sum(1 for r in rows if r['correct'])}/{len(rows)})")
    print(f"  top-1 accuracy (answerable): {pct(answ,'top1'):.1%}  ({sum(1 for r in answ if r['top1'])}/{len(answ)})")
    print(f"  full recall (answerable)   : {pct(answ,'recall'):.1%}")
    print(f"  MRR (answerable)           : {sum(r['mrr'] for r in answ)/len(answ):.3f}")
    print(f"  requests with false-positives: {sum(1 for r in answ if r['fps'])}/{len(answ)}")
    print(f"  off-domain/vague reject ok : {pct(offd,'correct'):.1%}  ({sum(1 for r in offd if r['correct'])}/{len(offd)})")

    print("\n---- by category ----")
    bycat = defaultdict(list)
    for r in rows:
        bycat[r["category"]].append(r)
    for cat in sorted(bycat):
        c = bycat[cat]
        print(f"  {cat:18} correct={pct(c,'correct'):.0%} ({sum(1 for r in c if r['correct'])}/{len(c)})")

    print("\n---- failures ----")
    for r in rows:
        if not r["correct"]:
            print(f"  [{r['category']}] {r['request'][:60]!r}\n      exp={r['expected']} got={r['survivors']} status={r['status']} fp={r['fps']}")

    out = config.ROOT / "logs" / "accuracy_results.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
