"""Run a labelled injection corpus through the ACTUAL security gate and score it.

Reads logs/redteam_corpus.jsonl ({text, label: attack|benign, technique, surface, family}) and reports,
per family and overall: detection rate on attacks (blocked = good), false-positive rate on benign
(allowed = good), and lists every BYPASS (attack the gate allowed) and FALSE-BLOCK (benign it blocked)
so the gaps drive concrete hardening.

Run:  .venv/Scripts/python.exe eval/redteam_gate.py
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

from pickysteve import security_gate   # noqa: E402


def main() -> int:
    corpus = [json.loads(l) for l in Path("logs/redteam_corpus.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    per = defaultdict(lambda: {"atk": 0, "atk_caught": 0, "ben": 0, "ben_ok": 0})
    bypasses, false_blocks = [], []
    for i, c in enumerate(corpus, 1):
        surface = c.get("surface") or "user_request"
        try:
            g = security_gate.scan(c["text"], surface)
            blocked = not g.allowed
        except Exception as e:
            print(f"  scan error on #{i}: {e}", file=sys.stderr)
            blocked = True  # fail-closed
        fam = c.get("family", "?")
        if c["label"] == "attack":
            per[fam]["atk"] += 1
            if blocked:
                per[fam]["atk_caught"] += 1
            else:
                bypasses.append(c)
        else:
            per[fam]["ben"] += 1
            if not blocked:
                per[fam]["ben_ok"] += 1
            else:
                false_blocks.append(c)
        if i % 10 == 0:
            print(f"  scanned {i}/{len(corpus)}", flush=True)

    atk = sum(p["atk"] for p in per.values())
    atk_c = sum(p["atk_caught"] for p in per.values())
    ben = sum(p["ben"] for p in per.values())
    ben_ok = sum(p["ben_ok"] for p in per.values())
    print("\n=== GATE RED-TEAM RESULTS ===")
    print(f"detection (attacks blocked): {atk_c}/{atk} = {atk_c/max(atk,1):.0%}")
    print(f"benign allowed (no FP)     : {ben_ok}/{ben} = {ben_ok/max(ben,1):.0%}")
    print(f"\nper family (detect | benign-ok):")
    for fam in sorted(per):
        p = per[fam]
        d = f"{p['atk_caught']}/{p['atk']}" if p['atk'] else "-"
        b = f"{p['ben_ok']}/{p['ben']}" if p['ben'] else "-"
        print(f"  {fam:22} {d:>7} | {b:>6}")
    print(f"\nBYPASSES ({len(bypasses)}) — attacks the gate ALLOWED (harden these):")
    for c in bypasses:
        print(f"  [{c.get('family')}/{c.get('technique','')[:40]}] {c['text'][:90]!r}")
    print(f"\nFALSE-BLOCKS ({len(false_blocks)}) — benign the gate blocked (over-blocking):")
    for c in false_blocks:
        print(f"  [{c.get('family')}] {c['text'][:90]!r}")
    json.dump({"detection": [atk_c, atk], "benign_ok": [ben_ok, ben],
               "bypasses": bypasses, "false_blocks": false_blocks},
              open("logs/redteam_results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
