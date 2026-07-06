---
id: dns-propagation-ttl
name: DNS Propagation & TTL
description: DNS record changes not visible everywhere yet — TTL, caching resolvers, propagation delay.
tags: [dns, ttl, propagation, a-record, resolver, stale, cutover]
---
# DNS Propagation & TTL

Use when you changed a DNS record (A/CNAME) but some clients still resolve the OLD IP because resolvers cache by TTL. NOT a CDN content cache (cdn-cache-invalidation) or HTTP cache.
