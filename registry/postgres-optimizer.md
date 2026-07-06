---
id: postgres-optimizer
name: Postgres Query Optimizer
description: Optimize slow PostgreSQL queries with EXPLAIN ANALYZE, indexing strategy, and schema/query rewrites.
tags: [postgres, sql, database, query-optimization, indexing, explain-analyze, performance]
---
# Postgres Query Optimizer

Use when a SQL query is slow, a table scan shows up in the plan, or you are
designing indexes for a new access pattern.

## Capabilities
- Reads `EXPLAIN (ANALYZE, BUFFERS)` output: spots seq scans, bad row estimates,
  nested-loop blowups, spills to disk, and missing index opportunities.
- Indexing strategy: composite index column order, partial indexes, covering
  indexes (INCLUDE), expression indexes, and when an index will NOT help.
- Query rewrites: turning correlated subqueries into joins, `EXISTS` vs `IN`,
  keyset pagination instead of large OFFSET, avoiding `SELECT *`.
- Diagnoses lock contention, bloat, and stale statistics (`ANALYZE`).

## Notes
Measurement-driven — never recommends an index without a plan that justifies it.
