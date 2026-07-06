---
id: grpc-deadline-propagation
name: gRPC Deadline Propagation
description: Cascading deadlines/timeouts across RPC calls so a slow dependency fails fast instead of hanging.
tags: [grpc, deadline, timeout, propagation, cascading, fail-fast, hang]
---
# gRPC Deadline Propagation

Use when one slow downstream makes the whole request HANG instead of failing fast — set and PROPAGATE deadlines across RPC hops. NOT TCP keep-alive and NOT rate limiting.
