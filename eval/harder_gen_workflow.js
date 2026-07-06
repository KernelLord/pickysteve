export const meta = {
  name: 'harder-sim-gen',
  description: 'Generate + blind-verify harder adversarial skill-routing tasks from KG confusable pairs',
  phases: [
    { title: 'Generate', detail: 'craft 2 oblique mirror tasks per confusable pair' },
    { title: 'Verify', detail: 'independent blind judge picks root cause; keep only agreements' },
  ],
}

// The 16 hardest confusable pairs (by KG similarity). Agents read the registry + KG from disk
// for full descriptions/distinguishers, so nothing large needs to cross the args boundary.
const PAIRS = [
  ['gpu-oom-inference', 'pod-oomkilled'],
  ['fulltext-bm25-tuning', 'hybrid-search-fusion'],
  ['cdn-cache-invalidation', 'read-replica-lag'],
  ['database-deadlocks', 'distributed-lock-redis'],
  ['grpc-deadline-propagation', 'tcp-connection-reuse'],
  ['hybrid-search-fusion', 'vector-hnsw-tuning'],
  ['blue-green-deploy', 'feature-flag-rollout'],
  ['fulltext-bm25-tuning', 'vector-hnsw-tuning'],
  ['http2-head-of-line', 'tcp-connection-reuse'],
  ['webhook-idempotency', 'webhook-signature-verification'],
  ['gpu-oom-inference', 'inference-batching-throughput'],
  ['cumulative-layout-shift', 'image-lazy-loading'],
  ['grpc-deadline-propagation', 'http2-head-of-line'],
  ['cdn-cache-invalidation', 'http-client-caching'],
  ['csrf-protection', 'webhook-signature-verification'],
  ['distributed-lock-redis', 'optimistic-concurrency-control'],
]
const REG = 'C:/Users/lasha/Desktop/pickysteve/eval/sim_registry'
const KG = 'C:/Users/lasha/Desktop/pickysteve/eval/skill_kg.json'

const GEN_SCHEMA = {
  type: 'object',
  properties: {
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          task: { type: 'string' },
          gold: { type: 'string' },
          traps: { type: 'array', items: { type: 'string' } },
          rationale: { type: 'string' },
        },
        required: ['task', 'gold', 'traps', 'rationale'],
      },
    },
  },
  required: ['tasks'],
}
const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    root_cause: { type: 'string' },
    also_accept: { type: 'array', items: { type: 'string' } },
    ambiguous: { type: 'boolean' },
    reason: { type: 'string' },
  },
  required: ['root_cause', 'also_accept', 'ambiguous', 'reason'],
}

const genPrompt = (a, b) => `You are authoring HARD-BUT-FAIR benchmark tasks for a skill-routing system.

FIRST, read the skill registry directory ${REG} (each *.md file's frontmatter has an id/name + description) so you know all 43 skill ids and what each covers. THEN read ${KG} and find the entry whose "a"/"b" are "${a}" and "${b}" — it gives a "distinguisher", "a_signal" (when ${a} is correct), and "b_signal" (when ${b} is correct).

${a} and ${b} are semantically ADJACENT and easily confused. Write EXACTLY TWO tasks — a mirror pair:
  Task 1: a realistic engineering SYMPTOM whose root cause is ${a} (gold="${a}"), with ${b} as the primary trap plus 1-2 other genuinely-adjacent skills as traps.
  Task 2: the mirror — root cause is ${b} (gold="${b}"), with ${a} as the primary trap plus 1-2 others.

Rules for fair-but-hard:
- Describe SYMPTOMS a real engineer reports. NEVER name the mechanism/skill or a jargon giveaway that trivially reveals it — describe OBSERVABLE behavior.
- The task MUST contain the ONE distinguishing detail from the correct side's signal, so exactly one skill is the true root cause. Hard = surface words point at the trap; the distinguishing detail points at the gold.
- Traps must be genuinely tempting (shared vocabulary/surface) but WRONG given the distinguishing detail.
- gold and traps must be exact skill ids from the registry.
Return JSON via the tool.`

const verifyPrompt = (taskText) => `You are an expert engineer triaging which ONE skill addresses the ROOT CAUSE of a reported problem.

Read the skill registry directory ${REG} (each *.md has an id/name + description) to learn the 43 available skills. Then, for this problem report, pick the SINGLE skill id whose scope is the true root cause:
"""
${taskText}
"""

If one or more OTHER skills would also be defensibly correct, list them in also_accept. If the report genuinely lacks any detail distinguishing between two+ skills, set ambiguous=true. Decide independently from surface wording — focus on the mechanism the symptom implies. Return JSON via the tool.`

phase('Generate')
const results = await pipeline(
  PAIRS,
  ([a, b]) => agent(genPrompt(a, b), { schema: GEN_SCHEMA, phase: 'Generate', label: `gen:${a}|${b}`, agentType: 'general-purpose' }),
  (gen, [a, b]) => parallel(((gen && gen.tasks) || []).map(t => () =>
    agent(verifyPrompt(t.task), { schema: VERIFY_SCHEMA, phase: 'Verify', label: `ver:${t.gold}`, agentType: 'general-purpose' })
      .then(v => ({ task: t, verdict: v, pair: `${a}|${b}` }))
      .catch(() => null)
  ))
)

const flat = results.filter(Boolean).flat().filter(Boolean)
const validated = []
const rejected = []
for (const r of flat) {
  const g = r.task.gold
  const v = r.verdict || {}
  const agrees = v.root_cause === g || (Array.isArray(v.also_accept) && v.also_accept.includes(g))
  if (agrees && !v.ambiguous) {
    const accept = v.root_cause && v.root_cause !== g ? [v.root_cause] : []
    validated.push({ task: r.task.task, gold: [g], traps: r.task.traps, accept,
                     rationale: r.task.rationale, category: `heldout2:${r.pair}` })
  } else {
    rejected.push({ gold: g, blind_pick: v.root_cause, ambiguous: v.ambiguous, reason: (v.reason || '').slice(0, 160), task: r.task.task.slice(0, 120) })
  }
}
log(`generated ${flat.length} tasks; ${validated.length} validated by blind judge; ${rejected.length} rejected`)
return { validated, rejected, counts: { generated: flat.length, kept: validated.length } }
