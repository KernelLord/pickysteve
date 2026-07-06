---
id: rag-architecture
name: RAG Reranking & Thresholds
description: Design the reranking layer of a RAG system — cross-encoders, score calibration, and confidence floors.
tags: [rag, reranking, cross-encoder, calibration, threshold, relevance, precision, confidence]
---
# RAG — Reranking & Thresholds

Use when designing how a retrieval-augmented system ranks and filters candidates
after the initial recall pass.

## Capabilities
- Cross-encoder reranking: scoring (query, candidate) pairs for true relevance.
- Why rerank against the original user intent, not the expanded search query.
- Score calibration: cross-encoder output is a logit, not a probability — build a
  labeled set and pick a floor that separates good from bad empirically.
- No-confident-match handling: when nothing clears the floor, ask or escalate rather
  than passing the best-but-low candidate through.

## Notes
This is the reranking half of the rag-architecture skill; retrieval is a sibling file.
A request about RAG should collapse to one skill, not two.
