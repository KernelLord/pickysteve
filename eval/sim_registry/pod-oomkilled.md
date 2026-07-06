---
id: pod-oomkilled
name: Kubernetes Pod OOMKilled
description: Container killed with OOMKilled — memory limits vs requests, right-sizing.
tags: [kubernetes, pod, oom, oomkilled, memory-limit, container, restart]
---
# Kubernetes Pod OOMKilled

Use when Kubernetes restarts a CONTAINER with OOMKilled because it exceeded its memory LIMIT. NOT Prometheus metrics OOM (metrics-cardinality) and NOT CUDA/GPU OOM (gpu-oom-inference).
