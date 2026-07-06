"""End-to-end Phase 1 pipeline (spec §1.1) — one orchestrating function with a
retry counter. No state-machine framework; a plain Engine holding the loaded
models is enough.

Flow:
  1. gate-scan the raw request                -> abort if injection
  2. router: request -> concrete search query
  3. hybrid retrieval (BM25 + embedding, RRF) -> N candidates
  4. gate-scan EVERY candidate's content      -> abort/drop on injection
  5. cross-encoder rerank vs the ORIGINAL request
  6. floor filter + dedupe-by-skill           -> survivors (or no-confident-match)
  7. compatibility check if >1 survivor
  8. assemble untrusted-data context bundle
  9. execution model produces the answer
 10. append the full trace to the JSONL log
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import assembly, conformal, config, execution, kg, logging_jsonl, router, security_gate
from .registry import load_units
from .rerank import Reranker
from .retrieval import Candidate, Retriever


@dataclass
class Result:
    status: str                       # ok | blocked_request | blocked_retrieved | no_confident_match
    request: str
    search_query: str = ""
    tags: list = field(default_factory=list)
    survivors: list = field(default_factory=list)   # skill_ids handed to execution
    floor: float = 0.0
    output: str = ""                  # execution answer, or clarifying question, or rejection note
    detail: dict = field(default_factory=dict)
    llm_attempts: int = 0
    conformal_set: list = field(default_factory=list)  # calibrated top-k set (coverage guarantee)
    ambiguous: bool = False           # conformal set has >1 member → contested label, surface the set


def _cand_row(c: Candidate, floor: float) -> dict:
    return {
        "unit_id": c.unit.unit_id,
        "skill_id": c.unit.skill_id,
        "name": c.unit.name,
        "source": c.unit.source,
        "stale": c.unit.stale,
        "bm25": round(c.bm25, 4),
        "emb": round(c.emb, 4),
        "rrf": round(c.rrf, 6),
        "rerank": None if c.rerank is None else round(c.rerank, 4),
        "rerank_query": c.rerank_query,
        "cleared_floor": (c.rerank is not None and c.rerank >= floor),
        "gate_allowed": c.gate_allowed,
        "gate_tier2": None if c.gate_tier2 is None else round(c.gate_tier2, 4),
        "gate_risk": c.gate_risk,
        "gate_detections": c.gate_detections,
    }


class Engine:
    def __init__(self, registry_dir=None):
        self.units = load_units(registry_dir)
        self.stale_units = [u.unit_id for u in self.units if u.stale]
        self.retriever = Retriever(self.units)
        self.reranker = Reranker()
        # A retrieved skill's CONTENT is static, so an ALLOW verdict never changes across requests —
        # memoize it (essential so RECALL_ALL doesn't re-gate all N units every call). A BLOCK is
        # NOT cached: a block can come from a transient docgate LLM timeout or a nondeterministic
        # small-model false-positive, and caching that would turn a momentary blip into a permanent
        # (abort-policy) outage — nullifying the docgate's own "don't persist error verdicts" rule.
        # Blocks are cheap to recompute (the ONNX gate is ~ms; the costly LLM only runs on
        # classifier-allowed docs) and MUST re-check so the gate self-heals.
        self._gate_cache: dict = {}

    def _scan_unit(self, unit):
        g = self._gate_cache.get(unit.unit_id)
        if g is None:
            g = security_gate.scan(unit.content, "retrieved_skill")
            if g.allowed:                       # only durable allows are memoized; blocks re-check
                self._gate_cache[unit.unit_id] = g
        return g

    def run(self, request: str, *, do_execute: bool = True) -> Result:
        floor = config.rerank_floor()
        attempts = 0
        trace: dict = {"registry_size": len(self.units), "stale_units": self.stale_units}

        # 1. gate-scan the raw request -------------------------------------------------
        greq = security_gate.scan(request, "user_request")
        trace["request_gate"] = {
            "allowed": greq.allowed, "risk": greq.risk_level,
            "tier2": greq.tier2_score, "detections": greq.detections,
            "tier3": greq.tier3,   # adjudicator verdict + reason — the WHY of a block (forensics)
        }
        if not greq_ok(greq):
            res = Result(status="blocked_request", request=request, floor=floor,
                         output="Request rejected: prompt-injection detected in the input.",
                         detail=trace)
            logging_jsonl.append({"status": res.status, **_log_base(res), "trace": trace})
            return res

        # 2. router: request -> search query -------------------------------------------
        ro = router.route(request)
        attempts += ro.attempts
        trace["router"] = {"search_query": ro.search_query, "sub_queries": ro.sub_queries,
                           "tags": ro.tags, "raw": ro.raw}

        # 3. hybrid retrieval — multi-intent: retrieve per sub-query, union candidates --
        #    RECALL UPGRADE: for a small registry, retrieve the FULL set (n = |units|) so the
        #    BM25+dense pre-filter can never drop an obliquely-phrased gold before the cross-encoder
        #    scores it. Precision is still the reranker+floor+judge's job downstream.
        recall_all = config.RECALL_ALL and 0 < len(self.units) <= config.RECALL_ALL_MAX
        n_ret = len(self.units) if recall_all else config.RETRIEVAL_N
        trace["recall_all"] = recall_all
        cand_map: dict[str, Candidate] = {}
        for q in (ro.sub_queries or [ro.search_query]):
            for c in self.retriever.search(q, n=n_ret):
                ex = cand_map.get(c.unit.unit_id)
                if ex is None or c.rrf > ex.rrf:
                    cand_map[c.unit.unit_id] = c
        candidates = list(cand_map.values())

        # 4. gate-scan EVERY retrieved candidate (the real high-risk surface) ----------
        kept: list[Candidate] = []
        for c in candidates:
            g = self._scan_unit(c.unit)
            c.gate_allowed, c.gate_tier2, c.gate_risk = g.allowed, g.tier2_score, g.risk_level
            c.gate_detections = g.detections
            c.sanitized_content = g.sanitized_text
            if not g.allowed:
                if config.RETRIEVED_INJECTION_POLICY == "abort":
                    trace["candidates"] = [_cand_row(x, floor) for x in candidates]
                    trace["blocked_unit"] = c.unit.unit_id
                    res = Result(status="blocked_retrieved", request=request,
                                 search_query=ro.search_query, tags=ro.tags, floor=floor,
                                 output=f"Request aborted: injection detected in retrieved "
                                        f"skill '{c.unit.unit_id}'.",
                                 detail=trace, llm_attempts=attempts)
                    logging_jsonl.append({"status": res.status, **_log_base(res), "trace": trace})
                    return res
                # policy == "drop": skip this candidate, keep going
                continue
            kept.append(c)

        # 5. rerank PRIMARY. In "maxsubq" mode each candidate is scored against MAX(original,
        #    each sub-query) so the router's jargon reformulation rescues an obliquely-phrased
        #    gold the raw symptom request buries (e.g. "cloudfront cache stale" → cdn-cache-
        #    invalidation, which the symptom text scores ~0). Precision is preserved by the
        #    floor + single-survivor + dominance gate downstream; a stronger cross-encoder
        #    (v2-m3) keeps a trap from riding a drifted sub-query. "orig" mode = request only.
        if config.RERANK_MODE == "maxsubq":
            reranked = self.reranker.score_multi(request, ro.sub_queries, kept)
        else:
            reranked = self.reranker.score(request, kept)
        trace["candidates"] = [_cand_row(c, floor) for c in reranked]

        # distinct intents = router's primary query + its sub-queries (deduped). Compound
        # when these resolve to >1 intent — the router may split intents across search_query
        # and sub_queries (the jwt+csrf case), so check the union, not just len(sub_queries).
        distinct_intents = []
        for q in [ro.search_query, *ro.sub_queries]:
            q = (q or "").strip()
            if q and q not in distinct_intents:
                distinct_intents.append(q)
        is_compound = len(distinct_intents) > 1

        if config.ENABLE_LLM_JUDGE:
            # 6*. LLM-judge survivor selection. The cross-encoder supplies RECALL (top-K above a
            #     low pre-floor); the capable model supplies PRECISION — it reads each skill's
            #     "NOT for X" clauses and the request's ruling-out cues to pick the root-cause
            #     skill(s). This resolves adjacent-skill confusions no score threshold can.
            survivors, low_confidence, ja = self._judge_survivors(request, reranked, floor, is_compound)
            attempts += ja
            trace["judged"] = [c.unit.skill_id for c in survivors]
            trace["low_confidence"] = low_confidence
        else:
            # 6. primary survivor = the single best skill that clears the floor. ALL additional
            #    survivors come from per-sub-query winners (6b) — so a tag-along that merely shares
            #    a word with the task is never added on relative-score grounds (no dominance gate).
            over_floor = [c for c in reranked if c.rerank is not None and c.rerank >= floor]
            deduped = assembly.dedupe_by_skill(over_floor)
            survivors = deduped[:1] if deduped else []

            # 6b. compound recall — per-sub-query WINNERS. For each distinct intent, the candidate
            #     that best matches THAT intent (scored against the sub-query, not a global max) is
            #     surfaced if it is a strong, above-floor match. Recovers a weak second intent
            #     (csrf, feature-flag) WITHOUT inflating a wrong skill that merely shares a word.
            if is_compound and kept:
                have = {c.unit.skill_id for c in survivors}
                seen_q: set[str] = set()
                for q in ro.sub_queries:  # the primary already covers the main intent
                    q = (q or "").strip()
                    if not q or q in seen_q:
                        continue
                    seen_q.add(q)
                    win, scq = self.reranker.intent_winner(q, kept, config.SUBQ_REL_MIN)
                    # if this intent's winner is one we already have (a facet of the same intent),
                    # don't force a different — wrong — skill in its place.
                    if not win or win.unit.skill_id in have:
                        continue
                    primary_score = win.rerank or 0.0  # winner's score vs the ORIGINAL request
                    # add if it's genuinely relevant to the original request, OR a very confident
                    # sub-query match (a real secondary intent the full request under-scores).
                    if primary_score >= floor or scq >= config.SUBQ_STRONG_MIN:
                        win.rerank = max(primary_score, scq)
                        survivors.append(win)
                        have.add(win.unit.skill_id)
                survivors = assembly.dedupe_by_skill(survivors)[: max(config.TOP_K, len(ro.sub_queries) + 1)]

            # 6c. relative-leader rescue — if nothing clears the floor but ONE candidate clearly
            #     leads (oblique phrasing the cross-encoder under-scores in absolute terms),
            #     surface it as a LOW-CONFIDENCE suggestion instead of refusing. A true no-match
            #     has no leader (all candidates ~0).
            low_confidence = False
            if not survivors and reranked:
                top = reranked[0].rerank or 0.0
                second = (reranked[1].rerank or 0.0) if len(reranked) > 1 else 0.0
                if top >= config.RESCUE_MIN_ABS and top >= config.RESCUE_RATIO * max(second, 1e-9):
                    survivors = [reranked[0]]
                    low_confidence = True
            trace["low_confidence"] = low_confidence

        # 6.5 CONFORMAL PREDICTION SET — calibrated safety net over the JUDGE-ADJUSTED pool scores
        #     (reranker score + calibrated bonus for the judge's picks — a fixed deterministic score
        #     function, so the coverage guarantee holds). Does not change `survivors`; surfaces a set
        #     guaranteed to contain the true skill >= 1-alpha of the time. Singleton = reranker and
        #     judge agree confidently (route cheap); >1 member = contested (escalate/flag ambiguous).
        conf_set: list = []
        ambiguous = False
        if config.ENABLE_CONFORMAL:
            cal = conformal.load()
            if cal is not None:
                cpool = assembly.dedupe_by_skill(
                    [c for c in reranked if c.rerank is not None]
                )[: config.CONFORMAL_POOL_K]
                cscores = conformal.adjust(
                    {c.unit.skill_id: (c.rerank or 0.0) for c in cpool},
                    [c.unit.skill_id for c in survivors], cal.bonus)
                conf_set = conformal.prediction_set(cscores, cal)
                # singleton = confident (route cheap); >1 = contested; EMPTY (lac) = "no confident
                # prediction" — both non-singleton cases are ambiguous → escalate.
                ambiguous = len(conf_set) != 1
                trace["conformal_set"] = conf_set
                trace["conformal_ambiguous"] = ambiguous

        if not survivors:
            # no-confident-match: ask ONE clarifying question (chosen policy; the
            # alternative — escalate to a bigger model with no context — is a config swap)
            q, a = execution.clarify(request)
            attempts += a
            best = reranked[0].rerank if reranked else None
            res = Result(status="no_confident_match", request=request,
                         search_query=ro.search_query, tags=ro.tags, floor=floor,
                         output=q, detail={**trace, "best_rerank": best}, llm_attempts=attempts,
                         conformal_set=conf_set, ambiguous=ambiguous)
            logging_jsonl.append({"status": res.status, **_log_base(res),
                                  "clarifying_question": q, "best_rerank": best, "trace": trace})
            return res

        # 7. compatibility check when >1 skill survives --------------------------------
        compat = None
        if len(survivors) > 1:
            compat = router.check_compatibility(
                request, [(c.unit.name, c.unit.description) for c in survivors]
            )
            trace["compatibility"] = {"compatible": compat.compatible, "reason": compat.reason}

        # 8. assemble untrusted-data context bundle ------------------------------------
        context = assembly.assemble(survivors, compat)
        trace["assembled_context"] = context

        # 9. execution -----------------------------------------------------------------
        output = ""
        if do_execute:
            output, a = execution.execute(request, context)
            attempts += a

        res = Result(status="ok", request=request, search_query=ro.search_query,
                     tags=ro.tags, survivors=[c.unit.skill_id for c in survivors],
                     floor=floor, output=output, detail=trace, llm_attempts=attempts,
                     conformal_set=conf_set, ambiguous=ambiguous)

        # 10. log the full trace -------------------------------------------------------
        logging_jsonl.append({
            "status": res.status, **_log_base(res),
            "survivors": res.survivors, "compatibility": trace.get("compatibility"),
            "assembled_context": context, "execution_output": output,
            "llm_attempts": attempts, "trace": trace,
        })
        return res

    def _judge_survivors(self, request, reranked, floor, is_compound=False):
        """Recall (cross-encoder) → precision (LLM). Build the judge pool from the top-K distinct
        skills clearing a LOW pre-floor, let the LLM pick the root-cause skill(s), and map its
        picks back to candidates (rerank order preserved). Empty pool = genuine no-match."""
        pool = assembly.dedupe_by_skill(
            [c for c in reranked if c.rerank is not None and c.rerank >= config.JUDGE_PREFLOOR]
        )[: config.JUDGE_TOP_K]
        if not pool:
            return [], False, 0
        # Hand the judge each skill's FULL body, not just the one-line description — the body holds
        # the "NOT for X / see Y instead" disambiguation clauses that resolve adjacent-skill
        # confusions. This is the deepest context the registry already carries.
        def _ctx(u):
            body = (u.content or "").strip()
            return f"{u.description}\n{body}"[:600]
        # Layer 1: pull knowledge-graph distinguishers for any confusable pairs in the pool.
        notes = kg.relational_notes([c.unit.skill_id for c in pool]) if config.ENABLE_KG else None
        cand_ctx = [(c.unit.skill_id, _ctx(c.unit)) for c in pool]
        picked, attempts = router.judge_skills(request, cand_ctx, relational_notes=notes)
        # Escalation: when the pool is CONFUSABLE (KG notes present), consult a stronger reasoning
        # model — it resolves the adjacent-skill reasoning misses the fast judge makes. Its pick,
        # when non-empty, overrides. Fires only on the hard (confusable) cases, so the slow model's
        # cost is paid only where it changes the answer.
        if config.ESCALATION_MODEL and notes:
            # FOCUSED prompt: top-K candidates, SHORT one-line descriptions (a small reasoning model
            # picks well on a tight choice but is overwhelmed by many full skill-bodies).
            esc_cand = [(c.unit.skill_id, c.unit.description) for c in pool[: config.ESCALATION_TOP_K]]
            picked2, a2 = router.judge_skills(request, esc_cand, relational_notes=notes,
                                              model=config.ESCALATION_MODEL,
                                              max_tokens=config.ESCALATION_MAX_TOKENS)
            attempts += a2
            # picked2 == [] can mean "nothing fits" OR "escalation call failed" (router logs a
            # judge_error record for the failure case); the fast pick stands either way.
            # CONSENSUS GATE: the escalation model may PRUNE/reorder among already-nominated
            # candidates (fast-judge picks or the reranker leader) but may not unilaterally
            # crown a candidate BOTH other signals rejected — observed: it fixed a fast-judge
            # over-pick (kept the nominated gold, dropped the leaked trap) but, ungated, also
            # overrode a correct fast-judge+reranker consensus with the trap.
            if picked2 and picked2[0] in (set(picked) | {pool[0].unit.skill_id}):
                picked = picked2
        by_id = {c.unit.skill_id: c for c in pool}
        survivors = [by_id[sid] for sid in picked if sid in by_id][: config.TOP_K]
        # Compound recall: a genuinely two-part request that surfaced only ONE skill — ask
        # specifically for the skill covering the SECOND, distinct intent (recovers an
        # under-picked 2nd gold, e.g. read-replica-lag alongside jwt-key-rotation).
        if config.ENABLE_COMPOUND2 and is_compound and len(survivors) == 1 and len(pool) > 1:
            have = {c.unit.skill_id for c in survivors}
            remaining = [c for c in pool if c.unit.skill_id not in have]
            p2, a2 = router.judge_second_intent(
                request, [(c.unit.skill_id, _ctx(c.unit)) for c in remaining], list(have), notes
            )
            attempts += a2
            for sid in p2:
                if sid in by_id and sid not in have:
                    survivors.append(by_id[sid]); have.add(sid)
            survivors = survivors[: config.TOP_K]
        # Layer 2: symbolic mutual-exclusion — a confused_with pair are alternatives, so drop the
        # lower-ranked member if the judge surfaced both (kills over-pick trap-leaks).
        if config.ENABLE_LOGIC and len(survivors) > 1:
            keep = set(kg.apply_exclusion([(c.unit.skill_id, c.rerank or 0.0) for c in survivors]))
            survivors = [c for c in survivors if c.unit.skill_id in keep]
        # An empty judge pick is a genuine no-confident-match (the judge is told to return [] when
        # nothing fits) — we do NOT fall back to the cross-encoder leader, which would surface a
        # wrong skill for an off-domain request.
        low_conf = bool(survivors) and all((c.rerank or 0.0) < floor for c in survivors)
        return survivors, low_conf, attempts

    def pick(self, request: str) -> dict:
        """Retrieval-only entry point for CONNECTORS (MCP / proxy / REST): run the
        picky-context pipeline WITHOUT the execution model, and return a clean bundle the
        calling agent injects into its own context."""
        res = self.run(request, do_execute=False)
        d = res.detail or {}
        return {
            "status": res.status,
            "request": request,
            "search_query": res.search_query,
            "sub_queries": (d.get("router") or {}).get("sub_queries"),
            "low_confidence": bool(d.get("low_confidence")),
            "survivors": res.survivors,
            # calibrated safety net: a >1-member set flags a contested-label case — a connector can
            # surface "one of these" (guaranteed to hold the right skill >= 1-alpha) instead of a
            # single debatable pick. Empty/1-member when the pick is unambiguous.
            "conformal_set": res.conformal_set,
            "ambiguous": res.ambiguous,
            "context_block": d.get("assembled_context", "") if res.status == "ok" else "",
            "candidates": [
                {"skill_id": c["skill_id"], "rerank": c["rerank"], "cleared_floor": c["cleared_floor"]}
                for c in (d.get("candidates") or [])
            ],
            "compatibility": d.get("compatibility"),
            "message": res.output,  # clarifying question / rejection note when status != ok
        }


def greq_ok(gate_result) -> bool:
    return gate_result.allowed


def _log_base(res: Result) -> dict:
    t = res.detail
    return {
        "request": res.request,
        "search_query": res.search_query,
        "tags": res.tags,
        "router": t.get("router"),
        "request_gate": t.get("request_gate"),
        "candidates": t.get("candidates"),
        "floor": res.floor,
    }
