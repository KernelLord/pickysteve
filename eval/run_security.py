"""Deep security test — fire the adversarial corpus at both gate paths.

  REQUEST gate  (Tier-3 escalation ON): measures detection on attacks + the
                false-positive rate on benign / benign-security-talk (Tier-3's job).
  RETRIEVED gate (strict, no escalation): the real high-risk surface — every attack
                presented as retrieved content should block.

Run:  .venv/Scripts/python.exe eval/run_security.py
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pickysteve import config, security_gate  # noqa: E402


def main() -> int:
    attacks = [json.loads(l) for l in (config.ROOT / "eval" / "attacks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"corpus: {len(attacks)} items  (tier3={config.ENABLE_TIER3}, band=[{config.TIER3_BAND_LOWER},{config.TIER3_BAND_UPPER}))\n")

    rows = []
    t0 = time.time()
    for i, a in enumerate(attacks, 1):
        rq = security_gate.scan(a["text"], "user_request")     # Tier-3 path
        rt = security_gate.scan(a["text"], "retrieved_skill")  # strict path
        rows.append({**a, "req_allowed": rq.allowed, "req_tier2": rq.tier2_score,
                     "req_tier3": rq.tier3, "ret_allowed": rt.allowed, "ret_tier2": rt.tier2_score})
        if i % 20 == 0:
            print(f"  scanned {i}/{len(attacks)}  ({time.time()-t0:.0f}s)")

    block = [r for r in rows if r["expected"] == "block"]
    allow = [r for r in rows if r["expected"] == "allow"]

    def rate(items, pred):
        return (sum(1 for r in items if pred(r)) / len(items)) if items else 0.0

    print("\n================ REQUEST GATE (Tier-3 on) ================")
    print(f"  attack detection rate : {rate(block, lambda r: not r['req_allowed']):.1%}  ({sum(1 for r in block if not r['req_allowed'])}/{len(block)})")
    print(f"  attack BYPASS rate    : {rate(block, lambda r: r['req_allowed']):.1%}  (lower=better)")
    print(f"  benign false-pos rate : {rate(allow, lambda r: not r['req_allowed']):.1%}  ({sum(1 for r in allow if not r['req_allowed'])}/{len(allow)})")

    print("\n================ RETRIEVED GATE (strict) ================")
    print(f"  attack detection rate : {rate(block, lambda r: not r['ret_allowed']):.1%}  ({sum(1 for r in block if not r['ret_allowed'])}/{len(block)})")
    print(f"  attack BYPASS rate    : {rate(block, lambda r: r['ret_allowed']):.1%}")

    print("\n---- per-category detection (request gate) ----")
    bycat = defaultdict(list)
    for r in rows:
        bycat[r["category"]].append(r)
    for cat in sorted(bycat):
        items = bycat[cat]
        exp = items[0]["expected"]
        if exp == "block":
            d = rate(items, lambda r: not r["req_allowed"])
            print(f"  {cat:26} detect={d:.0%}  ({sum(1 for r in items if not r['req_allowed'])}/{len(items)})")
        else:
            fp = rate(items, lambda r: not r["req_allowed"])
            print(f"  {cat:26} false-pos={fp:.0%}  ({sum(1 for r in items if not r['req_allowed'])}/{len(items)})")

    print("\n---- BYPASSES on the RETRIEVED gate (real security holes) ----")
    holes = [r for r in block if r["ret_allowed"]]
    if not holes:
        print("  none — every attack blocked on the strict retrieved path ✅")
    for r in holes:
        print(f"  [{r['category']}/{r['technique']}] tier2={r['ret_tier2']:.3f}  {r['text'][:90]!r}")

    print("\n---- request-gate false positives (benign blocked) ----")
    fps = [r for r in allow if not r["req_allowed"]]
    if not fps:
        print("  none — no benign request blocked ✅")
    for r in fps:
        t3 = r.get("req_tier3")
        print(f"  [{r['category']}] tier2={r['req_tier2']:.3f} tier3={t3}  {r['text'][:80]!r}")

    out = config.ROOT / "logs" / "security_results.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {out}  ({time.time()-t0:.0f}s total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
