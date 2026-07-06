---
id: tcp-connection-reuse
name: TCP Connection Reuse
description: Connection churn — keep-alive, pooling, TIME_WAIT, ephemeral port exhaustion.
tags: [tcp, keep-alive, connection, time-wait, churn, ephemeral-ports, pooling]
---
# TCP Connection Reuse

Use when too many short-lived TCP connections cause churn/TIME_WAIT/port exhaustion. NOT gRPC deadlines and NOT HTTP/2 multiplexing.
