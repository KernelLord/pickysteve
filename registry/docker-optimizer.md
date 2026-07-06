---
id: docker-optimizer
name: Docker Image Optimizer
description: Shrink and harden Docker images — multi-stage builds, layer caching, non-root, smaller base images.
tags: [docker, containers, dockerfile, image-size, multi-stage, layer-cache, devops, hardening]
---
# Docker Image Optimizer

Use when a Docker image is too large, builds slowly, or needs production hardening.

## Capabilities
- Multi-stage builds to drop build toolchains from the final image.
- Base-image choice: distroless/alpine/slim trade-offs and glibc gotchas.
- Layer ordering and cache mounts for fast incremental builds; `.dockerignore` hygiene.
- Hardening: non-root user, dropped capabilities, read-only rootfs, pinned digests.
- Diagnosing image bloat with layer inspection and reproducible builds.

## Notes
Container build/ops. For the orchestration layer (k8s) this hands off elsewhere.
