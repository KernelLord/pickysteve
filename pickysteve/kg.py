"""Layer 1 — skill Knowledge Graph + relational context (spec extension).

A tiny in-memory NetworkX graph (43 nodes is far too small to warrant a graph DB): nodes are
skills, `confused_with` edges carry the DISTINGUISHER between two semantically-adjacent skills
(the discriminating mechanism + the query cue that points to each side). At decision time we take
the induced subgraph over the current candidate set and hand the relevant distinguishers to the
judge, so it decides on the *discriminating feature* rather than raw cross-encoder similarity —
resolving adjacent-skill confusions (cdn-vs-replica-lag, gpu-oom-vs-batching) that no score fixes.

Graph is authored offline (eval/skill_kg.json). Confusable pairs come from embedding proximity;
each edge's distinguisher is general domain knowledge (not task-specific). Layer 2 (clingo ASP
hard constraints) and Layer 3 (FCA-derived minimal distinguishers via the `concepts` lib) build on
this same graph.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config

_G = None


def _graph():
    global _G
    if _G is None:
        try:
            import networkx as nx
        except Exception:
            _G = False
            return _G
        _G = nx.Graph()
        path = config.KG_PATH
        if path and Path(path).exists():
            try:
                for e in json.loads(Path(path).read_text(encoding="utf-8")):
                    _G.add_edge(e["a"], e["b"], a_id=e["a"], b_id=e["b"],
                                distinguisher=e.get("distinguisher", ""),
                                a_signal=e.get("a_signal", ""), b_signal=e.get("b_signal", ""))
            except Exception:
                pass
    return _G


def apply_exclusion(ranked: list[tuple[str, float]]) -> list[str]:
    """Layer 2 — symbolic mutual-exclusion via ASP (clingo). Two skills joined by a `confused_with`
    edge are ALTERNATIVES for one problem, so at most one may survive. The keeper is the one the JUDGE
    listed FIRST (its primary pick) — NOT the higher cross-encoder score, because on exactly these
    confused pairs the reranker systematically prefers the trap. Deterministic; kills judge over-pick
    trap-leaks (e.g. gpu-oom + inference-batching) without a model. Compound 2nd-golds are never
    confused pairs, so they are unaffected. Falls back to input order if clingo/graph is unavailable.

    `ranked` = [(skill_id, score)] in JUDGE-PICK order (primary first). Returns kept ids."""
    ids = [r[0] for r in ranked]
    G = _graph()
    if not G:
        return ids
    confused = [(a, b) for i, a in enumerate(ids) for b in ids[i + 1:] if G.has_edge(a, b)]
    if not confused:
        return ids
    prio = {sid: len(ids) - i for i, sid in enumerate(ids)}  # earlier in judge order = higher priority
    try:
        import clingo
    except Exception:
        # pure-Python fallback of the same rule: drop S if an earlier confused survivor exists
        drop = set()
        for a, b in confused:
            drop.add(a if prio[a] < prio[b] else b)
        return [s for s in ids if s not in drop]
    safe = {sid: sid.replace("-", "_").replace(".", "_") for sid in ids}
    prog = []
    for sid in ids:
        prog.append(f"survivor({safe[sid]}). rank({safe[sid]},{prio[sid]}).")
    for a, b in confused:
        prog.append(f"confused({safe[a]},{safe[b]}).")
    prog += [
        "confused(A,B) :- confused(B,A).",
        "dropped(S) :- survivor(S), survivor(T), confused(S,T), rank(S,RS), rank(T,RT), RS < RT.",
        "keep(S) :- survivor(S), not dropped(S).",
        "#show keep/1.",
    ]
    ctl = clingo.Control(["--warn=none"])
    ctl.add("base", [], "\n".join(prog))
    ctl.ground([("base", [])])
    kept = set()
    with ctl.solve(yield_=True) as h:
        for m in h:
            kept = {a.arguments[0].name for a in m.symbols(shown=True)}
            break
    return [sid for sid in ids if safe[sid] in kept]


def relational_notes(candidate_ids) -> list[str]:
    """For the candidate set, return one distinguisher note per confused_with pair PRESENT among
    the candidates (only pairs actually in contention — keeps the judge context focused)."""
    G = _graph()
    if not G:
        return []
    ids = [c for c in candidate_ids if c in G]
    notes, seen = [], set()
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if not G.has_edge(a, b):
                continue
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            seen.add(key)
            d = G[a][b]
            aid, bid = d.get("a_id", a), d.get("b_id", b)
            notes.append(
                f"- {aid} vs {bid}: {d['distinguisher']} "
                f"[{aid} when: {d['a_signal']}] [{bid} when: {d['b_signal']}]"
            )
    return notes
