---
id: webhook-signature-verification
name: Webhook Signature Verification
description: Verify inbound webhooks are authentic — HMAC signatures, timestamp tolerance, anti-forgery.
tags: [webhook, signature, hmac, verify, authenticity, forgery, secret]
---
# Webhook Signature Verification

Use when you must prove an inbound webhook really came from your provider and was not forged by someone POSTing to the public URL — verify the HMAC signature header against the shared secret and reject stale timestamps. NOT about duplicate processing under retries (idempotency).
