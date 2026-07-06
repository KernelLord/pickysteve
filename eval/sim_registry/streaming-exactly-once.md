---
id: streaming-exactly-once
name: Exactly-Once Stream Processing
description: Avoid double-counting on worker restart — checkpoints, transactional sinks.
tags: [streaming, exactly-once, double-count, checkpoint, transactional, restart, flink]
---
# Exactly-Once Stream Processing

Use when a STREAM PROCESSOR double-counts events after a worker restarts mid-batch — needs exactly-once via checkpoints/transactional sinks. NOT webhook idempotency (HTTP webhooks).
