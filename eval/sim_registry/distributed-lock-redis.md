---
id: distributed-lock-redis
name: Distributed Lock (Redis)
description: Mutual exclusion across processes/nodes — Redis locks, leases, fencing tokens.
tags: [lock, mutex, distributed, redis, redlock, lease, fencing, exclusion]
---
# Distributed Lock (Redis)

Use when only ONE node may run a critical section at a time across a cluster (e.g. a singleton cron). NOT the lost-update record-edit problem (optimistic-concurrency) and NOT DB deadlocks.
