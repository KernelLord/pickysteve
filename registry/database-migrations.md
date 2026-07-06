---
id: database-migrations
name: Safe Database Migrations
description: Plan zero-downtime schema migrations — expand/contract, backfills, locking, and reversibility.
tags: [database, migrations, schema, zero-downtime, backfill, locking, expand-contract, rollback]
---
# Safe Database Migrations

Use when changing a production database schema and you cannot take downtime or risk
a long table lock. Typical triggers: add a column to a huge / million-row table without
downtime, alter a big table while the site is live, change the schema safely in prod.

## Capabilities
- Expand/contract (parallel-change) pattern: add new, dual-write/backfill, switch, drop old.
- Lock-aware DDL: which ALTERs take a full lock, `CREATE INDEX CONCURRENTLY`, lock timeouts.
- Safe backfills in batches without saturating the DB or replication lag.
- Reversibility: every migration has a rollback or a forward-fix plan.
- Coordinating app deploys with migration steps so old and new code both work mid-migration.

## Notes
Migration safety and sequencing, distinct from query tuning (postgres-optimizer).
