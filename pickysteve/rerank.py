"""Cross-encoder re-ranking (spec §2.4).

Scores each candidate against the ORIGINAL user request (not the expanded query —
we rerank against what the user actually meant). Output is the reranker's NATIVE
score; we never assume it is a calibrated 0-1 probability. The score floor is set
empirically by eval/calibrate.py.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sentence_transformers import CrossEncoder

from . import config
from .retrieval import Candidate


class Reranker:
    def __init__(self, model: str | None = None):
        self.model_name = model or config.RERANK_MODEL
        self.model = CrossEncoder(self.model_name)
        # Optional persistent score cache. Cross-encoder scores are deterministic for a
        # (model, query, skill-text) triple, so caching makes repeated grade runs — and the
        # heavier v2-m3 model — fast. Opt-in via PS_RERANK_CACHE (a JSON path).
        self._cache = None
        self._cache_path = None
        self._dirty = 0
        if config.RERANK_CACHE:
            self._cache_path = Path(config.RERANK_CACHE)
            try:
                self._cache = json.loads(self._cache_path.read_text(encoding="utf-8")) \
                    if self._cache_path.exists() else {}
            except Exception:
                self._cache = {}

    def _key(self, query: str, text: str) -> str:
        h = hashlib.md5(f"{self.model_name}\x00{query}\x00{text}".encode("utf-8")).hexdigest()
        return h

    def _flush(self):
        if self._cache is not None and self._cache_path is not None and self._dirty:
            try:
                self._cache_path.write_text(json.dumps(self._cache), encoding="utf-8")
                self._dirty = 0
            except Exception:
                pass

    def _predict(self, pairs):
        pairs = list(pairs)
        if not pairs:
            return []
        if self._cache is None:
            return self._predict_raw(pairs)
        out = [None] * len(pairs)
        miss_idx, miss_pairs = [], []
        for i, (q, t) in enumerate(pairs):
            k = self._key(q, t)
            v = self._cache.get(k)
            if v is None:
                miss_idx.append(i); miss_pairs.append((q, t))
            else:
                out[i] = v
        if miss_pairs:
            preds = self._predict_raw(miss_pairs)
            for j, s in zip(miss_idx, preds):
                s = float(s)
                out[j] = s
                self._cache[self._key(*pairs[j])] = s
                self._dirty += 1
            self._flush()
        return out

    def _predict_raw(self, pairs):
        # CrossEncoder.predict's kwargs differ across sentence-transformers majors;
        # fall back to a bare call rather than crash on an unknown kwarg.
        try:
            return self.model.predict(pairs, show_progress_bar=False)
        except TypeError:
            return self.model.predict(pairs)

    def score(self, request: str, candidates: list[Candidate]) -> list[Candidate]:
        return self.score_multi(request, [], candidates)

    def score_multi(self, request: str, sub_queries: list[str],
                    candidates: list[Candidate]) -> list[Candidate]:
        """Rerank against the ORIGINAL request (spec §2.4 principle) AND each distinct
        sub-query, taking the MAX per candidate. This preserves "rerank vs what the user
        meant" while letting a secondary intent in a compound request rescue a skill the
        full-request score would have buried (the #15 case)."""
        if not candidates:
            return []
        texts = [c.unit.text_for_search for c in candidates]
        queries, seen = [], set()
        for q in [request, *sub_queries]:
            q = (q or "").strip()
            if q and q not in seen:
                seen.add(q)
                queries.append(q)
        if not queries:  # empty/whitespace request — guarantee ≥1 query so scores aren't None
            queries = [request or ""]
        best = [None] * len(candidates)
        winning_q = [request] * len(candidates)
        for q in queries:
            scores = self._predict([(q, t) for t in texts])
            for i, s in enumerate(scores):
                s = float(s)
                if best[i] is None or s > best[i]:
                    best[i], winning_q[i] = s, q
        for c, s, wq in zip(candidates, best, winning_q):
            c.rerank = s
            c.rerank_query = wq
        return sorted(candidates, key=lambda c: c.rerank, reverse=True)

    def raw_scores(self, request: str, texts: list[str]) -> list[float]:
        """Calibration helper: score (request, text) pairs, return native floats."""
        if not texts:
            return []
        return [float(s) for s in self._predict([(request, t) for t in texts])]

    def intent_winner(self, query: str, candidates: list[Candidate], min_rel: float = 0.15):
        """For a sub-query, return (candidate, sub_query_score) for the skill that is BOTH
        relevant to the sub-query (score >= min_rel) AND has the best ORIGINAL-request score
        (`c.rerank`, set by the primary pass) among those. This prevents a wrong skill that
        merely shares the sub-query's words (e.g. 'GPU' → gpu-oom) from winning over the skill
        the user actually wants (model-quantization), since the original request disambiguates."""
        if not candidates:
            return None, 0.0
        scores = [float(s) for s in self._predict([(query, c.unit.text_for_search) for c in candidates])]
        relevant = [(c, s) for c, s in zip(candidates, scores) if s >= min_rel]
        if not relevant:
            return None, 0.0
        win, scq = max(relevant, key=lambda cs: (cs[0].rerank or 0.0))
        return win, scq
