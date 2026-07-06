---
id: cdn-cache-invalidation
name: CDN / Edge Cache Invalidation
description: Stale content served from the CDN/edge — cache keys, TTL, purge, stale-while-revalidate.
tags: [cdn, edge, cache, invalidation, purge, ttl, stale, storefront]
---
# CDN / Edge Cache Invalidation

Use when the ORIGIN/API already serves fresh data but USERS still see stale content for minutes — the staleness lives in a CDN/edge cache and needs a purge or shorter TTL. NOT a database problem (if the API itself returned stale data, see read-replica-lag).
