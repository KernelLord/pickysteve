"""Router (spec §2.2): cheap model turns the raw request into a concrete search
query. Also hosts the post-retrieval compatibility check (spec §2.5), which reuses
the same cheap model — so the router is invoked twice per request when >1 skill
survives the floor.

The router can be wrong; its output is an INPUT to retrieval, never a final
decision. On any failure we fall back to using the raw request as the query.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from . import config, llm, logging_jsonl

_cache = None
_cache_path = None


def _cache_get():
    global _cache, _cache_path
    if config.ROUTER_CACHE and _cache is None:
        _cache_path = Path(config.ROUTER_CACHE)
        try:
            _cache = json.loads(_cache_path.read_text(encoding="utf-8")) if _cache_path.exists() else {}
        except Exception:
            _cache = {}
    return _cache

_ROUTER_SYS = (
    "You expand a user's software/agent request into concrete search queries for a "
    "skill registry. Turn vague asks (e.g. 'make it better') into specific search "
    "terms naming the likely capability. If the request bundles MULTIPLE distinct "
    "intents (e.g. 'review for security AND check the REST design'), emit one "
    "sub_query per intent (2-3 max). If it is a single intent, emit exactly one "
    "sub_query equal to search_query. Respond with JSON ONLY: "
    '{"search_query": "<concise primary query>", '
    '"sub_queries": ["<intent 1>", "<intent 2>"], '
    '"tags": ["<0-4 short topic tags>"]}.'
)

_COMPAT_SYS = (
    "You judge whether several retrieved skills are COMPATIBLE to apply together for "
    "ONE user request, or whether they conflict (e.g. two skills that prescribe "
    "contradictory approaches to the same job). Respond with JSON ONLY: "
    '{"compatible": true|false, "reason": "<one short sentence>"}.'
)

_JUDGE_SYS = (
    "You are a senior engineer choosing which skill(s) address the ROOT CAUSE of a request. "
    "You are given the request and a short list of candidate skills (id: description). Read each "
    "description CAREFULLY — many contain 'NOT for X' / 'use Y instead' disambiguation clauses. "
    "Method: (1) find the request's RULING-OUT cues. A phrase saying a layer is FINE, or that a "
    "fix DID NOT help, ELIMINATES that layer's skill — never pick an eliminated skill. Examples: "
    "'API returns fresh data' / 'DB replication lag looks fine' → NOT replica lag; 'hard refresh "
    "does NOT help' / 'Ctrl+Shift+R does not fix it' → NOT browser/http cache (so it IS the CDN/edge "
    "layer); 'GPU at 12% utilized' → NOT out-of-memory; 'HNSW tuning did NOT recover recall' → NOT "
    "index tuning (so it IS the embedding model); 'no deadlock error' → NOT deadlocks. "
    "(2) Match the request's ACTION to the skill's purpose, not shared words: 'catch up WITHOUT "
    "double-counting' = exactly-once dedup, NOT consumer-lag/throughput. (3) Pick the skill whose "
    "description matches the surviving root cause even if another candidate shares more words. "
    "COMPOUND: if the request asks to solve TWO distinct problems (cues: 'both', 'and "
    "simultaneously', 'two skills', 'diagnose both', 'need fixing' listing two symptoms), you MUST "
    "return exactly TWO skill_ids, one per problem. Otherwise return EXACTLY ONE. "
    "If genuinely NO candidate fits the request, return an empty list. "
    "Respond JSON ONLY: {\"skill_ids\": [\"<id>\", ...], \"reason\": \"<one short sentence>\"}."
)

_judge_cache = None
_judge_cache_path = None


def _norm(s: str) -> str:
    """Normalize a task string for a robust cache key: fold whitespace, strip backticks and smart
    punctuation, lowercase. Makes the pool-agnostic fallback key immune to trivial text variants."""
    import re
    s = s.replace("`", "").replace("—", "-").replace("–", "-").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def _judge_cache_get():
    global _judge_cache, _judge_cache_path
    if config.JUDGE_CACHE and _judge_cache is None:
        _judge_cache_path = Path(config.JUDGE_CACHE)
        try:
            _judge_cache = json.loads(_judge_cache_path.read_text(encoding="utf-8")) \
                if _judge_cache_path.exists() else {}
        except Exception:
            _judge_cache = {}
    return _judge_cache


def judge_skills(request: str, candidates: list[tuple[str, str]],
                 relational_notes: list[str] | None = None,
                 model: str | None = None, max_tokens: int | None = None) -> tuple[list[str], int]:
    """LLM picks the root-cause skill id(s) from the candidate shortlist. `candidates` is an
    ORDERED list of (skill_id, description) (best cross-encoder first). `relational_notes` are
    knowledge-graph distinguishers for confusable pairs among the candidates — injected so the
    judge decides on the discriminating feature. `model` overrides the judge model (e.g. a reasoning
    model for escalation); the cache is namespaced by model so picks never collide. Returns
    (picked_ids, attempts)."""
    if not candidates:
        return [], 0
    mdl = model or config.JUDGE_MODEL
    valid = {sid for sid, _ in candidates}
    cache = _judge_cache_get()
    # The KG distinguisher notes are part of the judge's INPUT — keying the cache without them
    # replays stale picks after a KG edit (observed: a sharpened edge fixed a live run but the
    # cached pre-edit pick kept failing the graded run).
    # non-cryptographic: this hash is only a cache-key discriminator, never a security primitive.
    nh = hashlib.sha1("\n".join(relational_notes or []).encode("utf-8"),
                      usedforsecurity=False).hexdigest()[:12]
    ckey = mdl + "||" + request + "||" + "|".join(sid for sid, _ in candidates) + "||n:" + nh
    tkey = mdl + "||TASK||" + _norm(request) + "||n:" + nh  # pool-agnostic, text-normalized fallback
    if cache is not None:
        if ckey in cache:
            return [s for s in cache[ckey] if s in valid], 0
        if tkey in cache:  # cached under a slightly different pool — reuse if the pick is still valid
            picks = [s for s in cache[tkey] if s in valid]
            if picks or cache[tkey] == []:
                return picks, 0
    listing = "\n".join(f"- {sid}: {desc}" for sid, desc in candidates)
    notes_block = ""
    if relational_notes:
        notes_block = ("\n\nDISAMBIGUATION NOTES (these candidates are commonly confused — use the "
                       "distinguisher to pick correctly):\n" + "\n".join(relational_notes))
    user = (f"Request: {request}\n\nCandidate skills:\n{listing}{notes_block}\n\n"
            f"Which skill_id(s) address the root cause?")
    try:
        text, attempts = llm.chat(mdl, _JUDGE_SYS, user, json_mode=True,
                                  max_tokens=max_tokens or config.JUDGE_MAX_TOKENS)
        data = llm.extract_json(text) or {}
        picked = data.get("skill_ids") or []
        if isinstance(picked, str):
            picked = [picked]
        picked = [str(s).strip() for s in picked if str(s).strip() in valid]
        # An empty pick is RESPECTED as "no candidate fits" (→ no-confident-match); do NOT force
        # the cross-encoder's top pick, which would false-positive genuine no-match requests.
        if cache is not None:
            cache[ckey] = picked
            try:
                _judge_cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        return picked, attempts
    except Exception as e:  # noqa: BLE001 — on judge failure, no-confident-match rather than a guess
        # Surface the failure instead of masking it as an empty pick: a 403/timeout on an
        # escalation model would otherwise be indistinguishable from "escalation concurred".
        try:
            logging_jsonl.append({"status": "judge_error", "model": mdl,
                                  "error": f"{type(e).__name__}: {e}"[:300]})
        except Exception:  # a logging failure must never break the safe ([], 0) fallback
            pass
        return [], 0


@dataclass
class RouterOutput:
    search_query: str
    sub_queries: list[str]
    tags: list[str]
    raw: str
    attempts: int


@dataclass
class CompatResult:
    compatible: bool
    reason: str
    raw: str


def route(request: str) -> RouterOutput:
    cache = _cache_get()
    if cache is not None and request in cache:
        d = cache[request]
        return RouterOutput(d["search_query"], d.get("sub_queries") or [d["search_query"]],
                            d.get("tags") or [], "<cached>", 0)
    try:
        text, attempts = llm.chat(config.ROUTER_MODEL, _ROUTER_SYS, request,
                                  json_mode=True, max_tokens=256)
        data = llm.extract_json(text) or {}
        query = (data.get("search_query") or "").strip() or request
        tags = data.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        subs = data.get("sub_queries") or []
        if isinstance(subs, str):
            subs = [subs]
        subs = [str(s).strip() for s in subs if str(s).strip()][:3]
        if not subs:
            subs = [query]
        tags = [str(t) for t in tags][:4]
        if cache is not None:
            cache[request] = {"search_query": query, "sub_queries": subs, "tags": tags}
            try:
                _cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
            except Exception:
                pass
        return RouterOutput(search_query=query, sub_queries=subs, tags=tags, raw=text, attempts=attempts)
    except Exception as e:  # noqa: BLE001
        return RouterOutput(search_query=request, sub_queries=[request], tags=[],
                            raw=f"<router-error: {e}>", attempts=0)


_SECOND_SYS = (
    "A user request describes TWO DISTINCT problems to solve. One skill has already been chosen for "
    "the first problem. From the remaining candidates, pick the ONE skill that addresses the SECOND, "
    "DIFFERENT problem — the part the first skill does NOT cover. If no remaining candidate addresses "
    "a genuinely separate second problem, return an empty list. Respond JSON ONLY: "
    '{"skill_ids": ["<id>"], "reason": "<short>"}.'
)


def judge_second_intent(request: str, remaining: list[tuple[str, str]], already: list[str],
                        relational_notes: list[str] | None = None) -> tuple[list[str], int]:
    """Compound recall: for a genuinely two-part request where the judge surfaced only ONE skill,
    ask specifically for the skill covering the SECOND intent. Returns (picked_ids, attempts)."""
    if not remaining:
        return [], 0
    valid = {sid for sid, _ in remaining}
    cache = _judge_cache_get()
    ckey = "SECOND||" + request + "||" + "+".join(already) + "||" + "|".join(sid for sid, _ in remaining)
    if cache is not None and ckey in cache:
        return [s for s in cache[ckey] if s in valid], 0
    listing = "\n".join(f"- {sid}: {desc}" for sid, desc in remaining)
    notes_block = ("\n\nDISAMBIGUATION NOTES:\n" + "\n".join(relational_notes)) if relational_notes else ""
    user = (f"Request: {request}\n\nAlready chosen (covers the first problem): {', '.join(already)}\n\n"
            f"Remaining candidate skills:\n{listing}{notes_block}\n\n"
            f"Which ONE remaining skill_id addresses a SECOND, distinct problem (or none)?")
    try:
        text, attempts = llm.chat(config.JUDGE_MODEL, _SECOND_SYS, user, json_mode=True, max_tokens=config.JUDGE_MAX_TOKENS)
        data = llm.extract_json(text) or {}
        picked = data.get("skill_ids") or []
        if isinstance(picked, str):
            picked = [picked]
        picked = [str(s).strip() for s in picked if str(s).strip() in valid][:1]
        if cache is not None:
            cache[ckey] = picked
            try:
                _judge_cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        return picked, attempts
    except Exception:  # noqa: BLE001
        return [], 0


def check_compatibility(request: str, names_and_descs: list[tuple[str, str]]) -> CompatResult:
    listing = "\n".join(f"- {n}: {d}" for n, d in names_and_descs)
    user = f"User request: {request}\n\nRetrieved skills:\n{listing}"
    try:
        text, _ = llm.chat(config.ROUTER_MODEL, _COMPAT_SYS, user, json_mode=True, max_tokens=200)
        data = llm.extract_json(text) or {}
        return CompatResult(
            compatible=bool(data.get("compatible", True)),
            reason=str(data.get("reason", "")),
            raw=text,
        )
    except Exception as e:  # noqa: BLE001 — fail open (assume compatible) but record it
        return CompatResult(compatible=True, reason=f"<compat-check-error: {e}>", raw="")
