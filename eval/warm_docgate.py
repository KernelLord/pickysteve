"""Warm + validate the doc-poisoning gate cache over the REAL registry.

Runs every registry unit through security_gate.scan(..., "retrieved_skill") so the docgate
adjudicates each doc once and disk-caches the verdict (logs/docgate_cache.json). This kills the
one-time first-request latency AND validates the hard deployment requirement: with
RETRIEVED_INJECTION_POLICY=abort + recall-all, a single false-positive on a legitimate registry
doc aborts EVERY request — so this script exits non-zero if any registry doc is flagged.

Run:  .venv/Scripts/python.exe eval/warm_docgate.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pickysteve import registry, security_gate  # noqa: E402


def main() -> int:
    units = registry.load_units()
    print(f"warming docgate over {len(units)} registry units...")
    flagged = []
    t0 = time.time()
    for i, u in enumerate(units, 1):
        g = security_gate.scan(u.content, "retrieved_skill")
        trig = (g.tier3 or {}).get("trigger", "")
        if not g.allowed:
            flagged.append((u.unit_id, trig, (g.tier3 or {}).get("raw", "")))
        print(f"  [{i}/{len(units)}] {u.unit_id:40} allowed={g.allowed}"
              + (f"  <-- FLAGGED ({trig})" if not g.allowed else ""), flush=True)
    dt = time.time() - t0
    print(f"\ndone in {dt:.0f}s")
    if flagged:
        print(f"\nFALSE POSITIVES ({len(flagged)}) — these legit docs would abort every request:")
        for uid, trig, reason in flagged:
            print(f"  {uid}  [{trig}] {reason[:120]}")
        return 1
    print("0 false positives — safe to deploy with abort policy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
