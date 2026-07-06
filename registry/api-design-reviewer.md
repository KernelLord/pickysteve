---
id: api-design-reviewer
name: API Design Reviewer
description: Review REST/HTTP API design — resource naming, status codes, pagination, versioning, idempotency, error shapes.
tags: [api, rest, http, api-design, pagination, versioning, status-codes, idempotency, openapi]
---
# API Design Reviewer

Use when designing or reviewing an HTTP/REST API surface, before clients depend on it.

## Capabilities
- Resource modeling and naming: nouns not verbs, consistent pluralization, nesting depth.
- Correct status codes (201 vs 200, 422 vs 400, 409 conflicts), and `Location` headers.
- Pagination (cursor/keyset vs offset), filtering, sorting conventions.
- Versioning strategy and backward-compatible evolution; deprecation headers.
- Idempotency keys for unsafe retries; consistent error envelopes (problem+json).
- Auth scheme placement, rate-limit headers, and pagination/consistency trade-offs.

## Notes
Design-level review; pairs with security-reviewer for the security dimension and
api-test-suite tooling for contract tests.
