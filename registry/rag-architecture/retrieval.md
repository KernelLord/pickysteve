---
id: rag-architecture
name: RAG Retrieval Design
description: Design the retrieval layer of a RAG system — chunking, hybrid keyword+embedding search, and fusion.
tags: [rag, retrieval, embeddings, bm25, hybrid-search, chunking, vector-search, fusion]
---
# RAG — Retrieval Design

Use when designing how a retrieval-augmented system finds candidate documents.

## Capabilities
- Chunking strategy: size, overlap, and respecting document structure.
- Hybrid retrieval: BM25 keyword search + dense embedding similarity, and why neither
  alone is enough.
- Score fusion: reciprocal rank fusion vs weighted-sum, and normalization pitfalls.
- Embedding model choice and the metadata to carry (source, timestamp) per candidate.
- Recall-first mindset at this stage — precision is the reranker's job.

## Notes
This is the retrieval half of the rag-architecture skill; the reranking half is a
sibling file. A request about RAG should not receive both halves as separate skills.
