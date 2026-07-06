---
id: pod-disruption-budget
name: Pod Disruption Budget
description: Limit how many replicas are evicted at once during node drains/upgrades.
tags: [pdb, disruption, eviction, drain, node-upgrade, availability, kubernetes]
---
# Pod Disruption Budget

Use when too many replicas get EVICTED at once during node upgrades/drains, causing brief errors. Set a PodDisruptionBudget. NOT autoscaling and NOT deployment strategy.
