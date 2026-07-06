"""Build a SIMULATION registry + task set with designer-known gold rankings.

The registry is intentionally trap-laden: clusters of overlapping skills that share
surface vocabulary, so a naive matcher is fooled. Each task has a gold answer and named
distractors (traps) that must NOT outrank the gold. Mirror pairs (e.g. CDN-cache vs
replica-lag) differ by a single ruling-out clue.

Run:  .venv/Scripts/python.exe eval/build_sim.py   ->  writes eval/sim_registry/*.md + sim_tasks.jsonl
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "eval" / "sim_registry"

# id: (name, description, tags, body)
SKILLS = {
    # --- cluster A: webhooks / payments (lexical traps) ---
    "payment-gateway-integration": ("Payment Gateway Integration",
        "Integrate Stripe/Paddle to charge cards, manage payment methods, subscriptions, and refunds.",
        "payment, stripe, paddle, charge, card, subscription, billing, webhook",
        "Use when wiring up a payment provider: creating charges/subscriptions, storing payment methods, "
        "handling refunds and proration. NOT for making webhook delivery safe under retries (see "
        "webhook-idempotency) or verifying webhook authenticity (see webhook-signature-verification)."),
    "webhook-idempotency": ("Webhook Idempotency & Replay Safety",
        "Make webhook/event processing safe when the sender retries — idempotency keys, dedup, exactly-once effects.",
        "webhook, idempotency, retry, replay, dedup, exactly-once, duplicate, stripe",
        "Use when a provider RETRIES a webhook (timeout/5xx) and you process the same event twice — e.g. "
        "charging or emailing a customer twice. Fix with an idempotency key / dedup table keyed on the "
        "event id, so repeated deliveries are no-ops. NOT about whether the webhook is authentic "
        "(signature-verification) or about the payment API itself."),
    "webhook-signature-verification": ("Webhook Signature Verification",
        "Verify inbound webhooks are authentic — HMAC signatures, timestamp tolerance, anti-forgery.",
        "webhook, signature, hmac, verify, authenticity, forgery, secret",
        "Use when you must prove an inbound webhook really came from your provider and was not forged by "
        "someone POSTing to the public URL — verify the HMAC signature header against the shared secret and "
        "reject stale timestamps. NOT about duplicate processing under retries (idempotency)."),
    # --- cluster B: search (specificity traps) ---
    "fulltext-bm25-tuning": ("Full-text BM25 Tuning",
        "Tune keyword/full-text search — inverted index, BM25 k1/b, analyzers, stemming.",
        "search, keyword, fulltext, bm25, inverted-index, analyzer, stemming, lexical",
        "Use for KEYWORD/lexical search relevance: BM25 parameters, analyzers, stemming, stop words. NOT "
        "for approximate nearest-neighbor / embedding search (vector-hnsw-tuning) or merging the two."),
    "vector-hnsw-tuning": ("Vector HNSW Index Tuning",
        "Tune an HNSW approximate-nearest-neighbor index — ef_search, ef_construction, M, recall vs latency.",
        "vector, ann, hnsw, nearest-neighbor, recall, ef_search, ef_construction, latency, embedding",
        "Use when an HNSW vector index trades RECALL against LATENCY — e.g. lowering ef_search cut p99 but "
        "dropped nearest-neighbor recall. Tune ef_search/ef_construction/M. NOT keyword search (bm25) and "
        "NOT the keyword+vector merge (hybrid-search-fusion)."),
    "hybrid-search-fusion": ("Hybrid Search Fusion",
        "Combine keyword (BM25) and vector results into one ranking — reciprocal rank fusion, weighting.",
        "hybrid, fusion, rrf, keyword, vector, combine, rerank, search",
        "Use when you already have BOTH keyword and vector retrieval and need to MERGE their rankings "
        "(e.g. reciprocal rank fusion) — typically to fix typos/synonyms missed by keyword-only. NOT for "
        "tuning a single index (bm25 or hnsw) in isolation."),
    "embedding-model-selection": ("Embedding Model Selection",
        "Choose an embedding model — dimensions, domain fit, multilingual, cost.",
        "embedding, model, dimensions, multilingual, semantic, vector",
        "Use when picking WHICH embedding model to use (dimensions, domain, cost). NOT about index "
        "parameters (hnsw) or fusing rankings."),
    # --- cluster C: caching / staleness (oblique + ruling-out traps) ---
    "cdn-cache-invalidation": ("CDN / Edge Cache Invalidation",
        "Stale content served from the CDN/edge — cache keys, TTL, purge, stale-while-revalidate.",
        "cdn, edge, cache, invalidation, purge, ttl, stale, storefront",
        "Use when the ORIGIN/API already serves fresh data but USERS still see stale content for minutes — "
        "the staleness lives in a CDN/edge cache and needs a purge or shorter TTL. NOT a database problem "
        "(if the API itself returned stale data, see read-replica-lag)."),
    "read-replica-lag": ("Read-Replica Replication Lag",
        "Read-after-write inconsistency from replica lag — route reads to primary, wait-for-LSN.",
        "replica, replication, lag, read-after-write, consistency, database, primary, stale",
        "Use when a user does NOT immediately see their OWN just-written data because the read hit a "
        "lagging replica (it appears a few seconds later). Fix by reading from the primary or waiting for "
        "the write to replicate. NOT when the API returns fresh data but an edge cache is stale (cdn)."),
    "http-client-caching": ("HTTP/Browser Caching",
        "Client-side caching — Cache-Control, ETag, max-age, browser revalidation.",
        "http, browser, cache-control, etag, max-age, client, stale",
        "Use when the BROWSER/HTTP client caches a response too long (Cache-Control/ETag). NOT server/CDN "
        "or database staleness."),
    # --- cluster D: concurrency ---
    "optimistic-concurrency-control": ("Optimistic Concurrency Control",
        "Prevent lost updates when two writers edit the same record — version column, compare-and-swap.",
        "concurrency, lost-update, version, optimistic, compare-and-swap, conflict, overwrite",
        "Use for the LOST-UPDATE problem: two users load the same record, both save, and the second "
        "silently overwrites the first. Fix with a version/etag column and reject stale writes. NOT a "
        "deadlock (database-deadlocks) and NOT cross-node mutual exclusion (distributed-lock-redis)."),
    "distributed-lock-redis": ("Distributed Lock (Redis)",
        "Mutual exclusion across processes/nodes — Redis locks, leases, fencing tokens.",
        "lock, mutex, distributed, redis, redlock, lease, fencing, exclusion",
        "Use when only ONE node may run a critical section at a time across a cluster (e.g. a singleton "
        "cron). NOT the lost-update record-edit problem (optimistic-concurrency) and NOT DB deadlocks."),
    "database-deadlocks": ("Database Deadlock Resolution",
        "Resolve DB deadlocks — lock ordering, 'deadlock detected', retry, shorter transactions.",
        "deadlock, database, lock, transaction, lock-ordering, retry",
        "Use when the DATABASE reports 'deadlock detected' and aborts a transaction because two "
        "transactions hold rows the other needs. Fix with consistent lock ordering and retries. NOT the "
        "silent last-write-wins overwrite (optimistic-concurrency) and NOT a Redis lock."),
    # --- cluster E: observability ---
    "metrics-cardinality": ("Metrics Cardinality Control",
        "Prometheus/metrics OOM from high-cardinality labels — drop/aggregate unbounded labels.",
        "metrics, prometheus, cardinality, label, oom, timeseries, user_id",
        "Use when metrics storage OOMs/explodes because an UNBOUNDED label (user_id, request_id) was added "
        "to a metric, creating millions of time series. Drop or bucket the label. NOT logging or tracing."),
    "distributed-tracing": ("Distributed Tracing",
        "Trace requests across services — spans, context propagation, sampling.",
        "tracing, spans, trace, propagation, opentelemetry, latency, distributed",
        "Use to follow a single request across services via spans/trace context. NOT metrics cardinality "
        "and NOT log formatting."),
    "structured-logging": ("Structured Logging",
        "Structured logs — JSON logs, levels, correlation ids, redaction.",
        "logging, logs, structured, json, correlation-id, levels",
        "Use for log structure/levels/correlation ids. NOT metrics or traces."),
    # --- cluster F: auth / security ---
    "jwt-key-rotation": ("JWT Signing Key Rotation",
        "Rotate JWT signing keys without invalidating live sessions — JWKS, multiple active kids.",
        "jwt, key-rotation, signing, jwks, kid, sessions, token",
        "Use to rotate JWT signing keys while keeping users logged in — publish both old and new keys in "
        "JWKS, sign with the new kid, retire the old after expiry. NOT OAuth flows or CSRF."),
    "oauth-pkce": ("OAuth PKCE Flow",
        "OAuth 2.0 authorization-code flow with PKCE for public clients.",
        "oauth, pkce, authorization-code, oidc, login, token",
        "Use to implement the OAuth authorization-code + PKCE login flow for SPAs/mobile. NOT key rotation "
        "and NOT CSRF specifically."),
    "csrf-protection": ("CSRF Protection",
        "Cross-site request forgery defense — same-site cookies, anti-CSRF tokens, double-submit.",
        "csrf, xsrf, same-site, token, forgery, login, cookie",
        "Use to stop cross-site request forgery on state-changing/login requests — SameSite cookies and "
        "anti-CSRF tokens. NOT general signature verification of webhooks."),
    "rate-limiting-token-bucket": ("Rate Limiting (Token Bucket)",
        "Per-client rate limiting — token bucket, sliding window, fairness, 429s.",
        "rate-limit, throttle, token-bucket, abuse, quota, 429, per-client",
        "Use to cap each client to N requests/sec so abusive clients don't starve others — token bucket / "
        "sliding window. NOT locks and NOT CSRF."),
    # --- standalone distractors ---
    "database-connection-pooling": ("Database Connection Pooling",
        "Tune DB connection pools — pool size, timeouts, pgbouncer, exhaustion.",
        "database, connection-pool, pgbouncer, pool-size, sql, exhaustion",
        "Use when the app exhausts DB connections or waits on the pool. NOT query count (n+1) or replicas."),
    "graphql-n-plus-one": ("GraphQL N+1 Query Elimination",
        "Eliminate N+1 queries in GraphQL/ORM resolvers — dataloader, batching, joins.",
        "graphql, n+1, dataloader, batching, resolver, orm, sql, queries",
        "Use when rendering one page fires HUNDREDS of tiny SQL queries (one per item) from GraphQL/ORM "
        "resolvers — batch them with a dataloader. NOT connection pool sizing and NOT replica lag."),
    "feature-flag-rollout": ("Feature Flag Percentage Rollout",
        "Ship to a % of users/traffic with instant kill-switch — flags, canary, gradual/percentage rollout.",
        "feature-flag, rollout, canary, percentage, traffic, requests, kill-switch, gradual, 5%, 10%",
        "Use to roll a change out to a PERCENTAGE of users or TRAFFIC — e.g. serve it to 5% or 10% of "
        "requests/traffic first — and roll back instantly via a flag if errors spike. This is a canary / "
        "percentage rollout. NOT a full environment swap (blue-green-deploy)."),
    "blue-green-deploy": ("Blue-Green Deployment",
        "Zero-downtime release by switching all traffic between two identical environments.",
        "blue-green, deploy, zero-downtime, environment, cutover, rollback",
        "Use to cut ALL traffic from the old (blue) to a new (green) environment at once, with instant "
        "rollback by switching back. NOT a per-percentage user rollout (feature-flag-rollout)."),
}

# task, gold (must rank top / survive), traps (must NOT outrank gold), rationale, category
TASKS = [
    ("Stripe retries a webhook when our endpoint is slow, and we end up charging the customer twice. How do we make processing safe under those retries?",
     ["webhook-idempotency"], ["payment-gateway-integration", "webhook-signature-verification"],
     "Double-charge under provider RETRIES = idempotency/dedup, not the payment API or signature auth.", "lexical-trap"),
    ("We can't be sure inbound webhooks really come from our provider and aren't forged by someone hitting the public URL.",
     ["webhook-signature-verification"], ["webhook-idempotency", "payment-gateway-integration"],
     "Authenticity/forgery = signature verification (mirror of the idempotency task).", "fine-distinction"),
    ("After we cut ef_search to drop our p99 latency, nearest-neighbor recall tanked. How do we get recall back without blowing latency?",
     ["vector-hnsw-tuning"], ["hybrid-search-fusion", "fulltext-bm25-tuning", "embedding-model-selection"],
     "ef_search + ANN recall/latency = HNSW tuning specifically, not fusion or keyword.", "specificity-trap"),
    ("We have keyword search today but synonyms and typos miss results. We want to add semantic matching and merge the two rankings.",
     ["hybrid-search-fusion"], ["fulltext-bm25-tuning"],
     "MERGE keyword + semantic rankings = hybrid fusion, not bm25 alone.", "specificity-trap"),
    ("When we update a product price the API immediately returns the new value, but the storefront keeps showing the old price for about 10 minutes.",
     ["cdn-cache-invalidation"], ["read-replica-lag", "http-client-caching"],
     "API returns FRESH -> DB/replica is fine -> staleness is in the CDN/edge cache.", "ruling-out-trap"),
    ("Right after a user posts a comment they sometimes don't see their own comment on refresh; it appears a few seconds later.",
     ["read-replica-lag"], ["cdn-cache-invalidation", "http-client-caching"],
     "Not seeing your OWN just-written data, appears shortly = read-after-write replica lag (mirror of CDN task).", "ruling-out-trap"),
    ("Two ops people open the same order in the dashboard, both click save, and the second save silently wipes out the first one's changes.",
     ["optimistic-concurrency-control"], ["distributed-lock-redis", "database-deadlocks"],
     "Silent last-write-wins overwrite = lost update -> optimistic concurrency, not a lock or deadlock.", "concurrency-trap"),
    ("Under load, two transactions each hold a row the other needs and the database kills one with a 'deadlock detected' error.",
     ["database-deadlocks"], ["distributed-lock-redis", "optimistic-concurrency-control"],
     "DB 'deadlock detected' = deadlock resolution; 'lock' is a lexical trap toward distributed-lock.", "lexical-trap"),
    ("Prometheus started OOMing right after we added a per-user_id label to one of our counters.",
     ["metrics-cardinality"], ["distributed-tracing", "structured-logging", "database-connection-pooling"],
     "Unbounded label -> timeseries explosion = metrics cardinality, not logging/tracing.", "oblique"),
    ("We need to rotate our JWT signing keys without logging everyone out, and separately stop the login CSRF reports.",
     ["jwt-key-rotation", "csrf-protection"], ["oauth-pkce", "rate-limiting-token-bucket"],
     "Two distinct intents: key rotation + CSRF; OAuth/rate-limit are lexical neighbors.", "compound"),
    ("A few abusive clients are hammering our API and starving everyone else; we want to cap each client to a few requests per second.",
     ["rate-limiting-token-bucket"], ["distributed-lock-redis", "csrf-protection"],
     "Per-client request cap = rate limiting, not a lock.", "lexical-trap"),
    ("Our GraphQL endpoint fires hundreds of tiny SQL queries to render a single list page.",
     ["graphql-n-plus-one"], ["database-connection-pooling", "read-replica-lag"],
     "Hundreds of tiny per-item queries = N+1; 'SQL/database' is a lexical trap toward pooling.", "oblique"),
    ("We want to ship a risky change to just 5% of users first and roll it back instantly if error rates spike.",
     ["feature-flag-rollout"], ["blue-green-deploy"],
     "5% of users + instant rollback = percentage flag/canary, not an all-or-nothing environment swap.", "specificity-trap"),
    ("Please plan the seating arrangement and the dinner menu for our company offsite next month.",
     [], ["feature-flag-rollout", "blue-green-deploy"],
     "No engineering skill fits -> should return no-confident-match.", "no-match"),
]


def main():
    REG.mkdir(parents=True, exist_ok=True)
    for sid, (name, desc, tags, body) in SKILLS.items():
        fm = (f"---\nid: {sid}\nname: {name}\ndescription: {desc}\n"
              f"tags: [{tags}]\n---\n# {name}\n\n{body}\n")
        (REG / f"{sid}.md").write_text(fm, encoding="utf-8")
    tasks_path = ROOT / "eval" / "sim_tasks.jsonl"
    with tasks_path.open("w", encoding="utf-8") as f:
        for task, gold, traps, why, cat in TASKS:
            f.write(json.dumps({"task": task, "gold": gold, "traps": traps,
                                "rationale": why, "category": cat}, ensure_ascii=False) + "\n")
    print(f"wrote {len(SKILLS)} skills to {REG}")
    print(f"wrote {len(TASKS)} tasks to {tasks_path}")


if __name__ == "__main__":
    main()
