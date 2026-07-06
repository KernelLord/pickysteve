---
id: payment-gateway-integration
name: Payment Gateway Integration
description: Integrate Stripe/Paddle to charge cards, manage payment methods, subscriptions, and refunds.
tags: [payment, stripe, paddle, charge, card, subscription, billing, webhook]
---
# Payment Gateway Integration

Use when wiring up a payment provider: creating charges/subscriptions, storing payment methods, handling refunds and proration. NOT for making webhook delivery safe under retries (see webhook-idempotency) or verifying webhook authenticity (see webhook-signature-verification).
