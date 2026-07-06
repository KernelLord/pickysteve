"""Hybrid retrieval (spec §2.3): BM25 keyword + embedding similarity, fused
with Reciprocal Rank Fusion. No knowledge graph — that's explicitly out of scope
for Phase 1.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from . import config
from .registry import Unit

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class Candidate:
    unit: Unit
    bm25: float = 0.0
    emb: float = 0.0
    rrf: float = 0.0
    rerank: float | None = None
    rerank_query: str | None = None  # which (sub-)query produced the max rerank score
    # security-gate results on the retrieved content (filled in by the pipeline):
    gate_allowed: bool | None = None
    gate_tier2: float | None = None
    gate_risk: str | None = None
    gate_detections: list = field(default_factory=list)
    sanitized_content: str | None = None  # Tier-1-sanitized text used in assembly


def _ranks(scores: np.ndarray) -> dict[int, int]:
    """Map item index -> 1-based rank (highest score = rank 1)."""
    order = np.argsort(-scores, kind="stable")
    return {int(idx): r + 1 for r, idx in enumerate(order)}


class Retriever:
    def __init__(self, units: list[Unit], embed_model: str | None = None):
        self.units = units
        self._bm25 = None
        self._embedder = None
        self._unit_emb = None
        if not units:  # empty registry — BM25Okapi([]) divides by zero; skip index build
            return
        self._bm25 = BM25Okapi([tokenize(u.text_for_search) for u in units])
        self._embedder = SentenceTransformer(embed_model or config.EMBED_MODEL)
        self._unit_emb = self._embedder.encode(
            [u.text_for_search for u in units],
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    def search(self, query: str, n: int | None = None) -> list[Candidate]:
        if not self.units:
            return []
        n = n or config.RETRIEVAL_N
        bm25 = np.asarray(self._bm25.get_scores(tokenize(query)), dtype=float)
        q = self._embedder.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
        emb = self._unit_emb @ q  # cosine (vectors are normalized)

        bm25_rank, emb_rank = _ranks(bm25), _ranks(emb)
        k = config.RRF_K
        rrf = {
            i: 1.0 / (k + bm25_rank[i]) + 1.0 / (k + emb_rank[i])
            for i in range(len(self.units))
        }
        top = sorted(range(len(self.units)), key=lambda i: rrf[i], reverse=True)[:n]
        return [
            Candidate(unit=self.units[i], bm25=float(bm25[i]), emb=float(emb[i]), rrf=rrf[i])
            for i in top
        ]
