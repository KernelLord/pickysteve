---
id: database-deadlocks
name: Database Deadlock Resolution
description: Resolve DB deadlocks — lock ordering, 'deadlock detected', retry, shorter transactions.
tags: [deadlock, database, lock, transaction, lock-ordering, retry]
---
# Database Deadlock Resolution

Use when the DATABASE reports 'deadlock detected' and aborts a transaction because two transactions hold rows the other needs. Fix with consistent lock ordering and retries. NOT the silent last-write-wins overwrite (optimistic-concurrency) and NOT a Redis lock.
