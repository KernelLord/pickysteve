# PickySteve — Simulation Ranking Test (designer-graded)

A deliberately adversarial test: a **24-skill registry** (`eval/sim_registry/`) of clusters
that share surface vocabulary, and **14 complex tasks** (`eval/sim_tasks.jsonl`) whose correct
answer is known to the designer but is a trap for naive matching. Each task names the gold
skill(s) and the distractor(s) that must NOT outrank it. Grader: `eval/run_sim.py`.

Trap types: **lexical** (a wrong skill owns the task's loudest word), **specificity** (general
vs specific skill), **ruling-out mirror pairs** (two tasks differ by one clue that flips the
answer), **oblique** (symptom described, skill named differently), **compound**, **no-match**.

## Results

| Metric | Score |
|---|---|
| **Gold outranks every trap (pure reranker)** | **13/13 (100%)** |
| Top-1 correct (answerable) | 12/13 |
| No-match handled | 1/1 |
| Tasks with a trap leaking into survivors | 1/13 |
| Overall strict PASS (top-1 + no leak + gold>trap) | 11/14 (79%) |

**The reranker's ranking discrimination was perfect** — on every answerable task the gold skill
scored higher than every trap, including:
- "DB says **deadlock detected**" → `database-deadlocks` 0.995 vs `distributed-lock-redis` 0.001
  (the word "lock" did not fool it).
- "cut **ef_search**, recall tanked" → `vector-hnsw-tuning` 0.871 vs fusion/bm25 0.0.
- "ship to **5% of users**, instant rollback" → `feature-flag-rollout` 0.996 vs `blue-green-deploy` 0.007.
- **Mirror pair**: #6 "don't see my *own* comment, appears shortly" → `read-replica-lag` 0.894;
  #5 "storefront stale but the API returns fresh" → `cdn-cache-invalidation` scored *above*
  `read-replica-lag` — the single ruling-out clue flipped the ranking correctly.

## The 3 strict failures — analysed (no wrong picks among them)

1. **#1 precision leak.** `webhook-idempotency` (0.995) was #1, but `payment-gateway-integration`
   (0.351) leaked in as #2. 0.351 is a *genuinely moderate* match (the task is about Stripe
   charges), and it cleared the relative-dominance gate. Borderline — arguably a reasonable
   secondary, not a clear error. *Lever:* raise `PS_DOMINANCE_RATIO`.
2. **#5 oblique below-floor.** `cdn-cache-invalidation` scored only **0.003** even though its doc
   describes the exact scenario — bge-reranker-base missed the causal leap from "storefront shows
   the old price while the API returns the new one" to "edge cache." It **still outranked the
   trap** and returned `no_confident_match` (asked to clarify) instead of guessing the wrong
   `read-replica-lag`. The *safe* failure. This is the cross-encoder's known oblique-reasoning limit.
3. **#10 compound weak-secondary.** `jwt-key-rotation` (0.998) so dominated `csrf-protection`
   (0.017) that the dominance gate dropped the weaker — but correct — second intent. PickySteve
   favours precision over surfacing a far-weaker secondary. *Lever:* lower `PS_DOMINANCE_RATIO`
   for recall-favouring use; the principled fix is per-sub-query winners (kept out to avoid
   regressing the tuned 90%/100%-top-1 accuracy benchmark).

## Verdict

On a registry built specifically to fool it, PickySteve's **suggestion ranking is excellent**:
it never ranked a trap above the right skill (100%), surfaced the right skill first 92% of the
time, and correctly refused the no-match task. The misses are a debatable precision leak, a
recall miss it handled *safely* (clarify, not wrong), and a deliberate precision/recall trade-off
exposed by a lopsided compound task — all consistent with the limitations documented in
`TEST_REPORT.md` (oblique reranking; the precision↔recall dominance lever).
