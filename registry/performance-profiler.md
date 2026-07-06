---
id: performance-profiler
name: Performance Profiler
description: Measurement-driven performance optimization — find the real bottleneck before changing code.
tags: [performance, profiling, optimization, latency, throughput, benchmark, bottleneck, flamegraph]
---
# Performance Profiler

Use when something is slow and you need to find the actual bottleneck instead of
guessing — backend latency, CPU hot paths, memory growth. Typical triggers: it's slow
but I don't know where the time is going, can't pin down the bottleneck, make my app
faster, the endpoint is slow and I'm not sure why.

## Capabilities
- Profile-first discipline: reproduce, measure a baseline, profile, then optimize the
  top contributor — never optimize on a hunch.
- Reads flamegraphs and profiler output to find hot paths and allocation churn.
- Distinguishes latency vs throughput problems and tail-latency (p99) issues.
- Benchmarks with proper warmup and variance; detects regressions between revisions.
- Algorithmic vs constant-factor wins; caching only with a correct invalidation story.

## Notes
General performance methodology. For SQL specifically see postgres-optimizer.
