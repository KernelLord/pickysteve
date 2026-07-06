"""Round-2 expansion of the simulation: +20 skills across 5 new clusters that create
CROSS-CLUSTER lexical collisions (3 different 'OOM' skills, 2 'lag', 2 'exactly-once',
2 'stale/TTL', multiple 'timeout/deadline') — the nastiest traps — plus 12 hard tasks.

Run:  .venv/Scripts/python.exe eval/build_sim_ext.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_sim import SKILLS, TASKS, REG, ROOT  # noqa: E402  (reuse the 24 base skills + 14 tasks)

NEW_SKILLS = {
    # --- networking ---
    "dns-propagation-ttl": ("DNS Propagation & TTL",
        "DNS record changes not visible everywhere yet — TTL, caching resolvers, propagation delay.",
        "dns, ttl, propagation, a-record, resolver, stale, cutover",
        "Use when you changed a DNS record (A/CNAME) but some clients still resolve the OLD IP because "
        "resolvers cache by TTL. NOT a CDN content cache (cdn-cache-invalidation) or HTTP cache."),
    "tcp-connection-reuse": ("TCP Connection Reuse",
        "Connection churn — keep-alive, pooling, TIME_WAIT, ephemeral port exhaustion.",
        "tcp, keep-alive, connection, time-wait, churn, ephemeral-ports, pooling",
        "Use when too many short-lived TCP connections cause churn/TIME_WAIT/port exhaustion. NOT gRPC "
        "deadlines and NOT HTTP/2 multiplexing."),
    "grpc-deadline-propagation": ("gRPC Deadline Propagation",
        "Cascading deadlines/timeouts across RPC calls so a slow dependency fails fast instead of hanging.",
        "grpc, deadline, timeout, propagation, cascading, fail-fast, hang",
        "Use when one slow downstream makes the whole request HANG instead of failing fast — set and "
        "PROPAGATE deadlines across RPC hops. NOT TCP keep-alive and NOT rate limiting."),
    "http2-head-of-line": ("HTTP/2 Head-of-Line Blocking",
        "HTTP/2 multiplexing and head-of-line blocking on a single connection.",
        "http2, multiplexing, head-of-line, hol, streams, connection",
        "Use for HTTP/2 stream multiplexing / head-of-line blocking issues. NOT gRPC deadlines or TCP reuse."),
    # --- kubernetes (note: OOM collision with metrics + gpu) ---
    "pod-oomkilled": ("Kubernetes Pod OOMKilled",
        "Container killed with OOMKilled — memory limits vs requests, right-sizing.",
        "kubernetes, pod, oom, oomkilled, memory-limit, container, restart",
        "Use when Kubernetes restarts a CONTAINER with OOMKilled because it exceeded its memory LIMIT. "
        "NOT Prometheus metrics OOM (metrics-cardinality) and NOT CUDA/GPU OOM (gpu-oom-inference)."),
    "hpa-autoscaling": ("Horizontal Pod Autoscaling",
        "Scale replicas automatically on CPU/custom metrics — HPA targets, thrash.",
        "hpa, autoscaling, replicas, cpu, scale-out, kubernetes, load",
        "Use when you want MORE REPLICAS to spin up automatically as CPU/load rises. NOT pod OOM and NOT "
        "disruption budgets."),
    "pod-disruption-budget": ("Pod Disruption Budget",
        "Limit how many replicas are evicted at once during node drains/upgrades.",
        "pdb, disruption, eviction, drain, node-upgrade, availability, kubernetes",
        "Use when too many replicas get EVICTED at once during node upgrades/drains, causing brief errors. "
        "Set a PodDisruptionBudget. NOT autoscaling and NOT deployment strategy."),
    # --- frontend ---
    "js-bundle-splitting": ("JS Bundle Splitting",
        "Reduce JS bundle size — code splitting, lazy chunks, tree-shaking.",
        "javascript, bundle, code-splitting, chunks, tree-shaking, size, frontend",
        "Use when the initial JS bundle is too big/slow — split into lazy chunks. NOT layout shift and "
        "NOT hydration."),
    "cumulative-layout-shift": ("Cumulative Layout Shift (CLS)",
        "Content jumps as images/ads load — reserve space, size attributes, CLS.",
        "cls, layout-shift, jump, reflow, reserve-space, web-vitals, frontend",
        "Use when page content JUMPS/shifts as images or ads finish loading and users mis-tap — reserve "
        "space to fix CLS. NOT lazy-loading mechanics per se and NOT bundle size."),
    "react-hydration-mismatch": ("React Hydration Mismatch",
        "SSR/CSR mismatch — 'text content did not match', flicker on load.",
        "react, hydration, ssr, mismatch, flicker, did-not-match, frontend",
        "Use when after enabling SSR the console shows 'text content did not match' and the UI flickers on "
        "load — a hydration mismatch. NOT bundle splitting and NOT layout shift."),
    "image-lazy-loading": ("Image Lazy Loading",
        "Defer offscreen images — loading=lazy, LCP, placeholders.",
        "image, lazy-loading, offscreen, lcp, placeholder, frontend",
        "Use to defer loading of offscreen images for faster initial load. NOT the content-jump problem "
        "(cumulative-layout-shift)."),
    # --- data engineering (lag collision + exactly-once collision) ---
    "kafka-consumer-lag": ("Kafka Consumer Lag",
        "Consumers falling behind — partition assignment, lag growth, scaling consumers.",
        "kafka, consumer, lag, partitions, rebalance, throughput, streaming",
        "Use when Kafka CONSUMERS fall behind the producers and lag grows at peak. NOT database read-replica "
        "lag (read-replica-lag) and NOT autoscaling pods."),
    "streaming-exactly-once": ("Exactly-Once Stream Processing",
        "Avoid double-counting on worker restart — checkpoints, transactional sinks.",
        "streaming, exactly-once, double-count, checkpoint, transactional, restart, flink",
        "Use when a STREAM PROCESSOR double-counts events after a worker restarts mid-batch — needs "
        "exactly-once via checkpoints/transactional sinks. NOT webhook idempotency (HTTP webhooks)."),
    "avro-schema-evolution": ("Avro Schema Evolution",
        "Evolve event schemas without breaking consumers — registry, backward compatibility.",
        "avro, schema, evolution, registry, backward-compatible, field, consumer",
        "Use when adding/removing an event FIELD breaks downstream consumers on the old schema — manage "
        "with a schema registry and backward-compatible changes. NOT backfilling data."),
    "data-backfill-strategy": ("Data Backfill Strategy",
        "Backfill historical data safely — chunking, idempotent reprocessing, throttling.",
        "backfill, historical, reprocess, chunk, throttle, data-pipeline",
        "Use to reprocess/backfill historical data safely without overwhelming the system. NOT schema "
        "changes and NOT consumer lag."),
    # --- ML serving (OOM collision + batching) ---
    "model-quantization": ("Model Quantization",
        "Shrink a model — int8/fp16 quantization, size and latency vs accuracy.",
        "quantization, int8, fp16, model-size, latency, accuracy, ml",
        "Use to shrink a model (int8/fp16) so it fits/serves faster, trading a little accuracy. NOT GPU OOM "
        "at runtime and NOT batching throughput."),
    "gpu-oom-inference": ("GPU OOM at Inference",
        "CUDA out-of-memory during inference — batch size, activation memory, offload.",
        "gpu, cuda, oom, out-of-memory, inference, batch-size, vram",
        "Use when the model server crashes with CUDA OUT OF MEMORY at inference under load — reduce batch "
        "size / activation memory. NOT Kubernetes pod OOM and NOT Prometheus metrics OOM."),
    "feature-train-serve-skew": ("Train/Serve Feature Skew",
        "Model good offline, bad in prod — feature pipeline skew between training and serving.",
        "feature, skew, train-serve, pipeline, offline-online, ml, drift",
        "Use when a model scores well offline but poorly in production because features are computed "
        "differently at serving time. NOT quantization and NOT batching."),
    "inference-batching-throughput": ("Inference Batching Throughput",
        "Raise serving throughput — dynamic batching, max batch size, queueing.",
        "batching, throughput, dynamic-batch, queue, inference, latency, ml",
        "Use to raise inference THROUGHPUT via dynamic batching/queueing. NOT GPU OOM and NOT quantization."),
}

NEW_TASKS = [
    ("Our model server crashes with CUDA out of memory when traffic spikes.",
     ["gpu-oom-inference"], ["pod-oomkilled", "metrics-cardinality"],
     "CUDA OOM at inference -> gpu-oom; the other two are different OOMs (container, Prometheus).", "oom-collision"),
    ("Kubernetes keeps restarting our pod with OOMKilled even though the JVM heap looks fine.",
     ["pod-oomkilled"], ["gpu-oom-inference", "metrics-cardinality"],
     "Container OOMKilled -> pod-oomkilled, not GPU or metrics OOM.", "oom-collision"),
    ("Our Kafka consumers fall behind during peak and the lag keeps growing.",
     ["kafka-consumer-lag"], ["read-replica-lag", "hpa-autoscaling"],
     "Kafka consumer lag, not DB replica lag (lexical 'lag' collision).", "lag-collision"),
    ("Our stream processor double-counts events whenever a worker restarts mid-batch.",
     ["streaming-exactly-once"], ["webhook-idempotency", "kafka-consumer-lag"],
     "Stream double-count on restart -> exactly-once streaming, not HTTP webhook idempotency.", "exactly-once-collision"),
    ("We changed our domain's A record an hour ago but some users still hit the old server.",
     ["dns-propagation-ttl"], ["cdn-cache-invalidation", "http-client-caching"],
     "Stale DNS resolution by TTL -> dns-propagation, not CDN content cache (stale/TTL collision).", "stale-collision"),
    ("On mobile the page content jumps down right as the banner image finishes loading and people mis-tap.",
     ["cumulative-layout-shift"], ["image-lazy-loading", "js-bundle-splitting"],
     "Content JUMP on image load -> CLS; lazy-loading is the tempting-but-wrong neighbor.", "oblique"),
    ("After enabling SSR the console floods with 'text content did not match' and the UI flickers on first load.",
     ["react-hydration-mismatch"], ["js-bundle-splitting", "image-lazy-loading"],
     "SSR 'did not match' + flicker -> hydration mismatch.", "oblique"),
    ("Under load our pods peg CPU at 100% and latency spikes; we want more replicas to kick in automatically.",
     ["hpa-autoscaling"], ["pod-oomkilled", "pod-disruption-budget"],
     "Auto add replicas on CPU -> HPA, not OOM or PDB.", "k8s-trap"),
    ("During node upgrades too many replicas get evicted at once and we briefly serve 503s.",
     ["pod-disruption-budget"], ["hpa-autoscaling", "blue-green-deploy"],
     "Evictions during drains -> PodDisruptionBudget, not autoscaling or deploy strategy.", "oblique"),
    ("Adding a new field to our event payload broke downstream consumers still on the old format.",
     ["avro-schema-evolution"], ["data-backfill-strategy", "kafka-consumer-lag"],
     "Schema field break -> schema evolution/registry, not backfill or lag.", "data-trap"),
    ("We're shipping a new ranking model: we need to shrink it to fit the GPU and serve it to 10% of traffic first.",
     ["model-quantization", "feature-flag-rollout"], ["gpu-oom-inference", "inference-batching-throughput"],
     "Two intents: shrink model (quantization) + 10% rollout (feature-flag); GPU-OOM/batching are neighbors.", "compound-cross"),
    ("One slow downstream service makes our whole request hang for 30s instead of failing fast; our timeouts don't seem to cascade.",
     ["grpc-deadline-propagation"], ["tcp-connection-reuse", "http2-head-of-line", "rate-limiting-token-bucket"],
     "Hang-not-fail-fast + timeouts not cascading -> deadline propagation, not TCP/HTTP2/rate-limit.", "deep-oblique"),
]


def main():
    skills = {**SKILLS, **NEW_SKILLS}
    tasks = TASKS + NEW_TASKS
    REG.mkdir(parents=True, exist_ok=True)
    for sid, (name, desc, tags, body) in skills.items():
        (REG / f"{sid}.md").write_text(
            f"---\nid: {sid}\nname: {name}\ndescription: {desc}\ntags: [{tags}]\n---\n# {name}\n\n{body}\n",
            encoding="utf-8")
    tp = ROOT / "eval" / "sim_tasks.jsonl"
    with tp.open("w", encoding="utf-8") as f:
        for task, gold, traps, why, cat in tasks:
            f.write(json.dumps({"task": task, "gold": gold, "traps": traps, "rationale": why, "category": cat}, ensure_ascii=False) + "\n")
    print(f"wrote {len(skills)} skills + {len(tasks)} tasks")


if __name__ == "__main__":
    main()
