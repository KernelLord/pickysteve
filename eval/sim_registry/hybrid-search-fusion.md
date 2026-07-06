---
id: hybrid-search-fusion
name: Hybrid Search Fusion
description: Combine keyword (BM25) and vector results into one ranking — reciprocal rank fusion, weighting.
tags: [hybrid, fusion, rrf, keyword, vector, combine, rerank, search]
---
# Hybrid Search Fusion

Use when you already have BOTH keyword and vector retrieval and need to MERGE their rankings (e.g. reciprocal rank fusion) — typically to fix typos/synonyms missed by keyword-only. NOT for tuning a single index (bm25 or hnsw) in isolation.
