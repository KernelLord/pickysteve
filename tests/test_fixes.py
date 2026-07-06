"""Tests for the post-review fixes (runnable as a plain script):
    .venv/Scripts/python.exe tests/test_fixes.py

  1. Tier-3 escalation WIRING — deterministic via a stub provider (no LLM needed):
     a gray-band Tier-2 score gets the provider's verdict, which overrides Tier-2.
  2. §2.4 invariant — single-intent rerank is governed by the ORIGINAL request only
     (score_multi with no sub-queries == reranking against the request).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stackone_defender import create_prompt_defense  # noqa: E402

GRAY = ("I'm building an AI agent that reads emails and web pages. How do I stop prompt "
        "injection from the content it pulls in?")  # Tier-2 ~0.836, inside [0.64, 0.85)

_passed, _failed = 0, 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1; print(f"  PASS  {name}")
    else:
        _failed += 1; print(f"  FAIL  {name}  {detail}")


class _StubProvider:
    def __init__(self, decision):
        self.decision = decision
    def classify(self, text, ctx=None):
        return {"decision": self.decision, "score": 0.01 if self.decision == "allow" else 0.99}


def _gate(provider):
    # provider passed PER-INSTANCE (as security_gate.py does), not via the global —
    # so two gates in one process don't clobber each other's provider.
    d = create_prompt_defense(
        block_high_risk=True, enable_tier1=True, enable_tier2=True,
        enable_tier3=True, defender_mode="cascade",
        tier3={"provider": provider, "escalation_band": {"lower": 0.64, "upper": 0.85}},
    )
    d.warmup_tier2()
    return d


def test_tier3_wiring():
    print("\n[1] Tier-3 escalation wiring (deterministic stub provider)")
    allow_gate = _gate(_StubProvider("allow"))
    block_gate = _gate(_StubProvider("block"))
    r_allow = allow_gate.defend_tool_result({"content": GRAY}, "user_request")
    r_block = block_gate.defend_tool_result({"content": GRAY}, "user_request")
    check("gray-band score escalates and a stub 'allow' overrides to allowed=True", r_allow.allowed is True,
          f"allowed={r_allow.allowed} tier2={getattr(r_allow,'tier2_score',None)}")
    check("same score with stub 'block' stays blocked", r_block.allowed is False,
          f"allowed={r_block.allowed}")


def test_single_intent_rerank_original_only():
    print("\n[2] §2.4 invariant — single-intent rerank uses the ORIGINAL request only")
    from pickysteve.registry import load_units
    from pickysteve.rerank import Reranker
    from pickysteve.retrieval import Candidate
    units = load_units()[:6]
    rr = Reranker()
    req = "review my rust code for ownership and unwrap problems"
    a = rr.score(req, [Candidate(unit=u) for u in units])
    b = rr.score_multi(req, [], [Candidate(unit=u) for u in units])
    sa = [(c.unit.skill_id, round(c.rerank, 6)) for c in a]
    sb = [(c.unit.skill_id, round(c.rerank, 6)) for c in b]
    check("score() == score_multi(req, [], …): no expansion influences single-intent ranking", sa == sb,
          f"{sa} != {sb}")


def main():
    test_tier3_wiring()
    test_single_intent_rerank_original_only()
    print(f"\n{'='*50}\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
