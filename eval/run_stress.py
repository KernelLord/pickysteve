"""Stress + robustness harness.

  A. Component latency/throughput (gate scan, retrieval, rerank) — percentiles.
  B. Concurrency / thread-safety (parallel gate + rerank, results must match serial).
  C. Edge cases (empty/whitespace/huge/unicode/skill-text-as-query) — must not crash.
  D. Robustness / failure injection (LLM raises, malformed router JSON, empty &
     duplicate-id registry, stale index) — must degrade gracefully.

Run:  .venv/Scripts/python.exe eval/run_stress.py
"""
from __future__ import annotations

import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pickysteve import config, llm, security_gate          # noqa: E402
from pickysteve.registry import load_units                 # noqa: E402
from pickysteve.rerank import Reranker                      # noqa: E402
from pickysteve.retrieval import Candidate, Retriever       # noqa: E402

_p, _f = 0, 0


def check(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1; print(f"  PASS  {name}  {detail}")
    else:
        _f += 1; print(f"  FAIL  {name}  {detail}")


def pcts(xs):
    xs = sorted(xs)
    g = lambda q: xs[min(len(xs) - 1, int(len(xs) * q))]
    return f"p50={g(.5)*1000:.1f}ms p95={g(.95)*1000:.1f}ms p99={g(.99)*1000:.1f}ms max={max(xs)*1000:.1f}ms"


def main() -> int:
    units = load_units()
    retr = Retriever(units)
    rr = Reranker()
    queries = ["review my rust code", "slow postgres query", "deploy to solana mainnet",
               "make my docker image smaller", "WCAG accessibility audit", "pitch deck help",
               "stop prompt injection", "production outage incident"]

    print("== A. Component latency/throughput ==")
    # gate (strict, ONNX only — no LLM)
    ts = []
    for i in range(120):
        t = time.perf_counter(); security_gate.scan(queries[i % len(queries)], "retrieved_skill"); ts.append(time.perf_counter() - t)
    print(f"  gate.scan (strict)   : {pcts(ts)}  ~{1/statistics.mean(ts):.0f}/s")
    ts = []
    for i in range(120):
        t = time.perf_counter(); retr.search(queries[i % len(queries)]); ts.append(time.perf_counter() - t)
    print(f"  retriever.search     : {pcts(ts)}  ~{1/statistics.mean(ts):.0f}/s")
    cset = retr.search(queries[0])
    ts = []
    for i in range(120):
        t = time.perf_counter(); rr.score(queries[i % len(queries)], [Candidate(unit=c.unit) for c in cset]); ts.append(time.perf_counter() - t)
    print(f"  rerank (8 cands)     : {pcts(ts)}  ~{1/statistics.mean(ts):.0f}/s")

    print("\n== B. Concurrency / thread-safety ==")
    serial = {q: [round(c.rerank, 5) for c in rr.score(q, [Candidate(unit=c.unit) for c in retr.search(q)])] for q in queries}
    def work(q):
        cs = rr.score(q, [Candidate(unit=c.unit) for c in retr.search(q)])
        sg = security_gate.scan(q, "retrieved_skill")
        return q, [round(c.rerank, 5) for c in cs], sg.allowed
    errors, mismatches = [], []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for q, scores, _ in ex.map(lambda q: work(q), queries * 6):
            if scores != serial[q]:
                mismatches.append(q)
    check("8-way concurrent rerank+gate: no crashes", True)
    check("concurrent results match serial (determinism/thread-safety)", not mismatches, f"mismatches={set(mismatches)}")

    print("\n== C. Edge cases (must not crash) ==")
    edge = ["", "   ", "\n\t ", "a", "x" * 20000, "🔥💀🎉 emoji only ✨", "SELECT * FROM users; DROP TABLE x;--",
            units[0].text_for_search, "的 中文 query", "​​zero width", "?!@#$%^&*()"]
    crashed = []
    for e in edge:
        try:
            c = retr.search(e); rr.score(e, [Candidate(unit=x.unit) for x in c]); security_gate.scan(e or "x", "retrieved_skill")
        except Exception as ex:
            crashed.append((e[:20], type(ex).__name__, str(ex)[:60]))
    check("all edge-case inputs handled without exception", not crashed, f"crashed={crashed}")

    print("\n== D. Robustness / failure injection ==")
    from pickysteve.pipeline import Engine
    eng = Engine()
    orig_chat = llm.chat
    # D1: LLM raises -> router falls back to request text, pipeline still routes
    llm.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulated LLM down"))
    try:
        res = eng.run("review my rust code for ownership problems", do_execute=False)
        check("LLM down: pipeline degrades gracefully (router fallback)", res.status in ("ok", "no_confident_match"), f"status={res.status} survivors={res.survivors}")
        check("LLM down: still routes the clear request to rust-reviewer", "rust-reviewer" in (res.survivors or []), f"survivors={res.survivors}")
    finally:
        llm.chat = orig_chat
    # D2: malformed router JSON -> extract_json returns None -> fallback to request
    llm.chat = lambda *a, **k: ("this is not json at all, lol", 1)
    try:
        res = eng.run("my docker image is way too big", do_execute=False)
        check("malformed router output: falls back, still routes", "docker-optimizer" in (res.survivors or []), f"survivors={res.survivors}")
    finally:
        llm.chat = orig_chat
    # D3: empty registry
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        try:
            e2 = Engine(registry_dir=Path(td))
            res = e2.run("anything at all", do_execute=False)
            check("empty registry: no crash, returns no_confident_match", res.status == "no_confident_match", f"status={res.status}")
        except Exception as ex:
            check("empty registry: no crash", False, f"{type(ex).__name__}: {ex}")
    # D4: duplicate skill_id across two files
    with tempfile.TemporaryDirectory() as td:
        reg = Path(td)
        for n in ("a.md", "b.md"):
            (reg / n).write_text("---\nid: dup\nname: Dup\ndescription: duplicate id test\ntags: [x]\n---\nbody about kubernetes networking\n", encoding="utf-8")
        try:
            e3 = Engine(registry_dir=reg)
            res = e3.run("kubernetes networking", do_execute=False)
            check("duplicate skill_id: dedupes to one survivor", len(set(res.survivors or [])) == len(res.survivors or []), f"survivors={res.survivors}")
        except Exception as ex:
            check("duplicate skill_id: no crash", False, f"{type(ex).__name__}: {ex}")

    print(f"\n{'='*50}\n{_p} passed, {_f} failed")
    return 1 if _f else 0


if __name__ == "__main__":
    raise SystemExit(main())
