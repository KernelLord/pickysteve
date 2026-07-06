---
id: read-replica-lag
name: Read-Replica Replication Lag
description: Read-after-write inconsistency from replica lag — route reads to primary, wait-for-LSN.
tags: [replica, replication, lag, read-after-write, consistency, database, primary, stale]
---
# Read-Replica Replication Lag

Use when a user does NOT immediately see their OWN just-written data because the read hit a lagging replica (it appears a few seconds later). Fix by reading from the primary or waiting for the write to replicate. NOT when the API returns fresh data but an edge cache is stale (cdn).
