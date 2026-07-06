---
id: gpu-oom-inference
name: GPU OOM at Inference
description: CUDA out-of-memory during inference — batch size, activation memory, offload.
tags: [gpu, cuda, oom, out-of-memory, inference, batch-size, vram]
---
# GPU OOM at Inference

Use when the model server crashes with CUDA OUT OF MEMORY at inference under load — reduce batch size / activation memory. NOT Kubernetes pod OOM and NOT Prometheus metrics OOM.
