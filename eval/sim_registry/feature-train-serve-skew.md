---
id: feature-train-serve-skew
name: Train/Serve Feature Skew
description: Model good offline, bad in prod — feature pipeline skew between training and serving.
tags: [feature, skew, train-serve, pipeline, offline-online, ml, drift]
---
# Train/Serve Feature Skew

Use when a model scores well offline but poorly in production because features are computed differently at serving time. NOT quantization and NOT batching.
