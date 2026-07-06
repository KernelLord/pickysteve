"""Calibrate the reranker score floor (spec §2.4).

Runs a labeled set of good/bad (query, skill) pairs through the SAME reranker the
pipeline uses, inspects the two score distributions, and picks a floor that
separates them. Writes eval/calibrated_floor.json, which config.rerank_floor()
reads. The floor lives in the reranker's NATIVE output space — we never assume 0-1.

Run:  .venv/Scripts/python.exe eval/calibrate.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pickysteve import config           # noqa: E402
from pickysteve.registry import load_units  # noqa: E402
from pickysteve.rerank import Reranker      # noqa: E402


def _stats(xs: list[float]) -> str:
    return (f"n={len(xs)} min={min(xs):.4f} p25={_pct(xs,25):.4f} "
            f"median={statistics.median(xs):.4f} p75={_pct(xs,75):.4f} "
            f"max={max(xs):.4f} mean={statistics.mean(xs):.4f}")


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def main() -> int:
    units = load_units()
    by_skill: dict[str, list[str]] = {}
    for u in units:
        by_skill.setdefault(u.skill_id, []).append(u.text_for_search)

    rr = Reranker()
    pairs_path = config.ROOT / "eval" / "labeled_pairs.jsonl"
    pairs = [json.loads(l) for l in pairs_path.read_text().splitlines() if l.strip()]

    good, bad = [], []
    for p in pairs:
        texts = by_skill.get(p["skill_id"])
        if not texts:
            print(f"  ! labeled pair references unknown skill_id: {p['skill_id']}")
            continue
        # multi-file skills: take the best-scoring unit (mirrors the pipeline, which
        # surfaces the best unit per skill after dedupe).
        score = max(rr.raw_scores(p["query"], texts))
        (good if p["label"] == "good" else bad).append(score)

    print(f"\nGOOD pairs: {_stats(good)}")
    print(f"BAD  pairs: {_stats(bad)}")

    max_bad, min_good = max(bad), min(good)
    if min_good > max_bad:
        floor = (min_good + max_bad) / 2.0  # clean separation -> midpoint
        sep = "clean (distributions do not overlap)"
    else:
        # overlap: pick the threshold maximizing Youden's J (TPR - FPR)
        floor, best_j = min(bad + good), -1.0
        for t in sorted(set(good + bad)):
            tpr = sum(1 for s in good if s >= t) / len(good)
            fpr = sum(1 for s in bad if s >= t) / len(bad)
            if tpr - fpr > best_j:
                best_j, floor = tpr - fpr, t
        sep = f"overlapping (Youden J={best_j:.3f})"

    tpr = sum(1 for s in good if s >= floor) / len(good)
    fpr = sum(1 for s in bad if s >= floor) / len(bad)
    print(f"\nseparation : {sep}")
    print(f"chosen floor = {floor:.4f}  -> good kept {tpr:.0%}, bad admitted {fpr:.0%}")

    out = {
        "floor": floor,
        "separation": sep,
        "good_kept": tpr,
        "bad_admitted": fpr,
        "good_stats": _stats(good),
        "bad_stats": _stats(bad),
        "rerank_model": config.RERANK_MODEL,
        "n_good": len(good),
        "n_bad": len(bad),
    }
    (config.ROOT / "eval" / "calibrated_floor.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote eval/calibrated_floor.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
