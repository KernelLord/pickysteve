---
id: optimistic-concurrency-control
name: Optimistic Concurrency Control
description: Prevent lost updates when two writers edit the same record — version column, compare-and-swap.
tags: [concurrency, lost-update, version, optimistic, compare-and-swap, conflict, overwrite]
---
# Optimistic Concurrency Control

Use for the LOST-UPDATE problem: two users load the same record, both save, and the second silently overwrites the first. Fix with a version/etag column and reject stale writes. NOT a deadlock (database-deadlocks) and NOT cross-node mutual exclusion (distributed-lock-redis).
