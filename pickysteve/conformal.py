"""Split-conformal prediction for the router (the honest handling of irreducible label ambiguity).

The reranker/judge stack gives a top-1 skill, but on genuinely-contested adjacent-skill pairs a
single answer is over-confident. Conformal prediction turns the reranker's score distribution into
a PREDICTION SET with a finite-sample coverage guarantee: calibrated at level alpha on labelled
tasks, the returned set contains the true skill with probability >= 1 - alpha (marginal), regardless
of whether the scores are well-calibrated probabilities.

Method: APS (Adaptive Prediction Sets, Romano et al. 2020) over a temperature-softmax of the pool's
cross-encoder scores. Non-conformity of the true class = cumulative softmax mass of all classes
ranked at or above it. The (1-alpha) empirical quantile of calibration non-conformities is the
threshold q̂; at test time the set is the smallest top-prob prefix whose cumulative mass reaches q̂.

Pure numpy — no sklearn/MAPIE/torch dependency. Deterministic (no randomized tie-break) so it slots
into the cached, reproducible pipeline.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import config


def _softmax(scores: np.ndarray, temp: float) -> np.ndarray:
    s = np.asarray(scores, dtype=float) / max(temp, 1e-6)
    s = s - s.max()
    e = np.exp(s)
    tot = e.sum()
    return e / tot if tot > 0 else np.full_like(e, 1.0 / len(e))


def _aps_nonconformity(probs: np.ndarray, true_idx: int) -> float:
    """Cumulative softmax mass of every class ranked at or above the true class (descending)."""
    order = np.argsort(-probs, kind="stable")
    cum = 0.0
    for idx in order:
        cum += float(probs[idx])
        if idx == true_idx:
            return cum
    return cum  # unreachable when true_idx is present


@dataclass
class Calibration:
    q_hat: float
    alpha: float
    temp: float
    n: int
    method: str = "aps"
    # Judge bonus: added to the reranker score of every skill the LLM judge picked BEFORE the
    # softmax. Raw reranker scores alone cannot yield tight sets here — on the adjacent-skill
    # confusions the reranker's top-1 is a trap and only the judge knows better — so the conformal
    # score function must see the judge's signal. Still a fixed deterministic function of the
    # request (reranker + cached judge), so the coverage guarantee is unaffected.
    bonus: float = 0.0


def adjust(candidate_scores: dict[str, float], judge_picks: list[str], bonus: float) -> dict[str, float]:
    """Apply the judge bonus to the picked skills' reranker scores — the conformal score function."""
    if not bonus or not judge_picks:
        return dict(candidate_scores)
    picked = set(judge_picks)
    return {k: v + (bonus if k in picked else 0.0) for k, v in candidate_scores.items()}


def calibrate(scored_tasks: list[tuple[dict[str, float], str]],
              alpha: float | None = None, temp: float | None = None,
              bonus: float = 0.0, method: str = "aps") -> Calibration:
    """`scored_tasks` = list of (candidate_scores {skill_id: adjusted_score}, true_skill_id) —
    scores must already be judge-adjusted via `adjust()` when a bonus is used.
    Returns the conformal threshold q̂ at level alpha. Two nonconformity methods:
      "aps" — cumulative mass of classes ranked at or above gold (adaptive set sizes, but the gold's
              own mass inflates q̂, so singletons need an unreachably-high top prob on this score scale)
      "lac" — 1 - p(gold) (Least Ambiguous Classifier: provably the smallest average sets; an EMPTY
              set is possible and means "predict nothing" → escalate — the natural gate semantics)
    Tasks whose gold is absent from the candidate scores are skipped — a retrieval failure, not a
    calibration signal; they would poison q̂ toward 1.0."""
    alpha = config.CONFORMAL_ALPHA if alpha is None else alpha
    temp = config.CONFORMAL_TEMP if temp is None else temp
    scores_nc: list[float] = []
    for cand, gold in scored_tasks:
        if not cand or gold not in cand:
            continue
        ids = list(cand.keys())
        probs = _softmax(np.array([cand[i] for i in ids]), temp)
        gi = ids.index(gold)
        if method == "lac":
            scores_nc.append(1.0 - float(probs[gi]))
        else:
            scores_nc.append(_aps_nonconformity(probs, gi))
    n = len(scores_nc)
    if n == 0:
        return Calibration(q_hat=1.0, alpha=alpha, temp=temp, n=0, bonus=bonus, method=method)
    # finite-sample-adjusted (1-alpha) quantile: ceil((n+1)(1-alpha)) / n
    level = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
    q_hat = float(np.quantile(np.array(scores_nc), level, method="higher"))
    return Calibration(q_hat=q_hat, alpha=alpha, temp=temp, n=n, bonus=bonus, method=method)


def prediction_set(candidate_scores: dict[str, float], cal: Calibration,
                   temp: float | None = None) -> list[str]:
    """The conformal set, in descending-score order (element 0 = point prediction).
    aps: smallest top-probability prefix whose cumulative softmax mass reaches q̂.
    lac: every class with p >= 1 - q̂ (may be EMPTY — "no confident prediction" → escalate)."""
    if not candidate_scores:
        return []
    temp = cal.temp if temp is None else temp
    ids = list(candidate_scores.keys())
    probs = _softmax(np.array([candidate_scores[i] for i in ids]), temp)
    order = np.argsort(-probs, kind="stable")
    if cal.method == "lac":
        thr = 1.0 - cal.q_hat
        return [ids[i] for i in order if float(probs[i]) >= thr]
    out, cum = [], 0.0
    for idx in order:
        out.append(ids[idx])
        cum += float(probs[idx])
        if cum >= cal.q_hat:
            break
    return out


# --- persistence --------------------------------------------------------------
_cal: Calibration | None = None
_loaded = False


def load(path: str | None = None) -> Calibration | None:
    global _cal, _loaded
    if _loaded and path is None:
        return _cal
    p = Path(path or config.CONFORMAL_CAL)
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            _cal = Calibration(q_hat=float(d["q_hat"]), alpha=float(d["alpha"]),
                               temp=float(d.get("temp", 1.0)), n=int(d.get("n", 0)),
                               method=d.get("method", "aps"), bonus=float(d.get("bonus", 0.0)))
        except Exception:
            _cal = None
    if path is None:
        _loaded = True
    return _cal


def save(cal: Calibration, path: str | None = None) -> None:
    p = Path(path or config.CONFORMAL_CAL)
    p.write_text(json.dumps({"q_hat": cal.q_hat, "alpha": cal.alpha, "temp": cal.temp,
                             "n": cal.n, "method": cal.method, "bonus": cal.bonus}, indent=0),
                 encoding="utf-8")
