---
id: webhook-idempotency
name: Webhook Idempotency & Replay Safety
description: Make webhook/event processing safe when the sender retries — idempotency keys, dedup, exactly-once effects.
tags: [webhook, idempotency, retry, replay, dedup, exactly-once, duplicate, stripe]
---
# Webhook Idempotency & Replay Safety

Use when a provider RETRIES a webhook (timeout/5xx) and you process the same event twice — e.g. charging or emailing a customer twice. Fix with an idempotency key / dedup table keyed on the event id, so repeated deliveries are no-ops. NOT about whether the webhook is authentic (signature-verification) or about the payment API itself.
