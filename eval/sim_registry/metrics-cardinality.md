---
id: metrics-cardinality
name: Metrics Cardinality Control
description: Prometheus/metrics OOM from high-cardinality labels — drop/aggregate unbounded labels.
tags: [metrics, prometheus, cardinality, label, oom, timeseries, user_id]
---
# Metrics Cardinality Control

Use when metrics storage OOMs/explodes because an UNBOUNDED label (user_id, request_id) was added to a metric, creating millions of time series. Drop or bucket the label. NOT logging or tracing.
