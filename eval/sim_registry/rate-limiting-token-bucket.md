---
id: rate-limiting-token-bucket
name: Rate Limiting (Token Bucket)
description: Per-client rate limiting — token bucket, sliding window, fairness, 429s.
tags: [rate-limit, throttle, token-bucket, abuse, quota, 429, per-client]
---
# Rate Limiting (Token Bucket)

Use to cap each client to N requests/sec so abusive clients don't starve others — token bucket / sliding window. NOT locks and NOT CSRF.
