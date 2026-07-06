---
id: vector-hnsw-tuning
name: Vector HNSW Index Tuning
description: Tune an HNSW approximate-nearest-neighbor index — ef_search, ef_construction, M, recall vs latency.
tags: [vector, ann, hnsw, nearest-neighbor, recall, ef_search, ef_construction, latency, embedding]
---
# Vector HNSW Index Tuning

Use when an HNSW vector index trades RECALL against LATENCY — e.g. lowering ef_search cut p99 but dropped nearest-neighbor recall. Tune ef_search/ef_construction/M. NOT keyword search (bm25) and NOT the keyword+vector merge (hybrid-search-fusion).
