"""Central configuration. Everything is overridable via PS_* environment vars.

Defaults point the model client at a local Ollama OpenAI-compatible endpoint, so
the system runs with no cloud API key. Swap PS_LLM_BASE_URL / PS_*_MODEL to use a
hosted model.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Load a .env written by `python -m pickysteve.setup`, so the chosen model persists
    without exporting env vars each shell. Real environment variables always take priority."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")

# True once the user has picked a model (via the setup wizard's .env or an explicit env var).
# When False, the code still runs on the local-Ollama fallback, but `python -m pickysteve`
# nudges the user to run `python -m pickysteve.setup` and choose.
MODEL_CONFIGURED = (ROOT / ".env").exists() or bool(os.getenv("PS_LLM_BASE_URL"))

REGISTRY_DIR = Path(os.getenv("PS_REGISTRY_DIR", str(ROOT / "registry")))
LOG_PATH = Path(os.getenv("PS_LOG_PATH", str(ROOT / "logs" / "runs.jsonl")))
INDEX_CACHE = ROOT / "logs" / ".index_cache.json"

# --- Model client (OpenAI-compatible; run `python -m pickysteve.setup` to choose) ----------
# Fallback if the setup wizard hasn't been run: local Ollama, so it works offline with no key.
LLM_BASE_URL = os.getenv("PS_LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("PS_LLM_API_KEY", "ollama")  # Ollama ignores it; SDK needs non-empty
ROUTER_MODEL = os.getenv("PS_ROUTER_MODEL", "qwen3:8b")   # cheap/fast (Haiku-tier role)
EXEC_MODEL = os.getenv("PS_EXEC_MODEL", "qwen3:8b")       # capable model (swap to a bigger one)
# The disambiguation JUDGE (spec §2.5) — the precision-critical role. Defaults to the router
# model but is separately swappable to a stronger deep-context reasoner (PS_JUDGE_MODEL), since
# it drives final skill selection on adjacent-skill confusions.
JUDGE_MODEL = os.getenv("PS_JUDGE_MODEL", ROUTER_MODEL)
# Output-token budget for the judge. Reasoning models (phi4-mini-reasoning, deepseek-r1) emit a long
# chain-of-thought BEFORE the JSON answer, so they need a large budget or the JSON is never reached.
JUDGE_MAX_TOKENS = int(os.getenv("PS_JUDGE_MAX_TOKENS", "200"))
# Judge escalation ensemble: a stronger REASONING model (e.g. phi4-mini-reasoning, MIT, local) that
# adjudicates only the CONFUSABLE cases (where the KG flags adjacency among the candidates). The fast
# qwen3 judge decides everything; the slow reasoner is consulted only when it matters — it corrects
# the adjacent-skill reasoning misses qwen3 makes (verified 3/3 on qwen3-miss cases). Opt-in.
ESCALATION_MODEL = os.getenv("PS_ESCALATION_MODEL") or None
ESCALATION_MAX_TOKENS = int(os.getenv("PS_ESCALATION_MAX_TOKENS", "1200"))
# A small reasoning judge excels on FOCUSED prompts but drowns in long context, so escalation shows
# it only the top-K candidates with SHORT (one-line) descriptions + the distinguisher — not full bodies.
ESCALATION_TOP_K = int(os.getenv("PS_ESCALATION_TOP_K", "3"))
EXEC_MAX_TOKENS = int(os.getenv("PS_EXEC_MAX_TOKENS", "400"))  # cap exec output (CPU inference is slow)

# Use Ollama's NATIVE /api/chat (with think:false) instead of the OpenAI-compat path.
# Required for qwen3-style thinking models — see llm.py. Auto-on for a localhost:11434
# base_url; override with PS_OLLAMA_NATIVE=0/1.
_native_env = os.getenv("PS_OLLAMA_NATIVE")
OLLAMA_NATIVE = (_native_env == "1") if _native_env is not None else ("11434" in LLM_BASE_URL)
# Opt-in router cache (the router is deterministic at temp 0 → reuse outputs across repeated
# test runs, skipping Ollama). Set PS_ROUTER_CACHE to a JSON path; default None = no caching.
ROUTER_CACHE = os.getenv("PS_ROUTER_CACHE") or None

# --- Embedding + reranker models ----------------------------------------------
EMBED_MODEL = os.getenv("PS_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
# bge-reranker-v2-m3 (568M) discriminates semantically-adjacent skills markedly better than
# the base model on adversarial oblique tasks (evidence: gold-outranks-traps 9/19 vs 6/19 on a
# hard fail set); the score cache below hides its extra CPU cost on repeated runs.
RERANK_MODEL = os.getenv("PS_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")  # spec §2.4
# Persistent cross-encoder score cache (deterministic per model+query+skill). Opt-in via
# PS_RERANK_CACHE=<json path>; makes repeated grade runs and the heavier reranker fast.
RERANK_CACHE = os.getenv("PS_RERANK_CACHE") or None

# --- Retrieval / rerank params ------------------------------------------------
# Retrieve a wide candidate set so an obliquely-phrased gold is present for the reranker to
# score (evidence: 6 of 19 hard fails were pure retrieval misses at N=8). The reranker + floor
# still gate precision, so a larger N costs recall-safety, not precision.
RETRIEVAL_N = int(os.getenv("PS_RETRIEVAL_N", "20"))   # raw hybrid candidates
# RECALL UPGRADE — for a SMALL registry the BM25+dense pre-filter is the only place a gold can be
# lost before the judge ever sees it (an obliquely-phrased request whose gold shares no lexical or
# strong dense signal never makes the top-N RRF cut). When the registry is small enough to
# cross-encode in full, skip the pre-filter and rerank EVERY skill — the cross-encoder + floor still
# gate precision, so this converts "retrieval recall" from a lossy bottleneck into a guarantee that
# no gold is dropped upstream. Costs ~len(units) cross-encoder calls/query (trivial + cached for ~43).
RECALL_ALL = os.getenv("PS_RECALL_ALL", "1") == "1"
RECALL_ALL_MAX = int(os.getenv("PS_RECALL_ALL_MAX", "120"))  # only rerank-all when len(units) <= this
# Primary rerank scoring: "orig" scores only vs the original request; "maxsubq" scores each
# candidate vs MAX(original, each router sub-query) — the router's jargon reformulation rescues
# obliquely-phrased golds the raw symptom request buries. Guarded downstream by the floor +
# single-survivor + dominance so a trap riding a drifted sub-query does not win.
RERANK_MODE = os.getenv("PS_RERANK_MODE", "maxsubq")
# LLM disambiguation judge (spec §2.5 spirit — the capable model decides). The cross-encoder
# gives RECALL (gold in the top-K); an LLM then picks the 1-2 skills that address the ROOT CAUSE,
# reading each skill's "NOT for X" disambiguation clauses that a cross-encoder cannot. This cracks
# the adjacent-skill confusions (cdn vs replica-lag, hnsw vs embedding-model) that no floor fixes.
ENABLE_LLM_JUDGE = os.getenv("PS_ENABLE_LLM_JUDGE", "1") == "1"
JUDGE_TOP_K = int(os.getenv("PS_JUDGE_TOP_K", "6"))          # candidates shown to the judge
# Low pre-floor so an obliquely-phrased gold the cross-encoder under-scores (e.g. read-replica-lag
# at 0.0015, csrf-protection at 0.0021) still enters the judge pool. Precision is the JUDGE's job,
# not this gate's; a true no-match yields an empty judge pick regardless of pool size.
JUDGE_PREFLOOR = float(os.getenv("PS_JUDGE_PREFLOOR", "0.001"))
JUDGE_CACHE = os.getenv("PS_JUDGE_CACHE") or None            # deterministic → cache for fast reruns
# Layer 1 knowledge graph (kg.py): a confused_with graph whose edges carry the DISTINGUISHER between
# adjacent skills. When ≥2 candidates share an edge, the distinguisher is injected into the judge as
# relational context so it decides on the discriminating feature. Opt-in via PS_KG_PATH.
ENABLE_KG = os.getenv("PS_ENABLE_KG", "1") == "1"
KG_PATH = os.getenv("PS_KG_PATH", str(ROOT / "eval" / "skill_kg.json"))
# Layer 2 — symbolic mutual-exclusion (clingo ASP over the KG): confusable pairs are alternatives,
# so drop one member if the judge surfaces both. OPT-IN (default off): on this hard set it proved
# net-negative — whichever member the rule keeps (reranker-top or judge-first), it sometimes keeps
# the trap, because "which member is right" IS the hard problem the judge already owns. The clingo
# machinery is retained for future precondition/ordering rules where the correct side is derivable.
ENABLE_LOGIC = os.getenv("PS_ENABLE_LOGIC", "0") == "1"
# Compound second-intent recall pass. OPT-IN (default off): the router over-emits sub-queries, so
# `is_compound` is noisy and the extra pass adds spurious 2nd survivors (trap leaks) on single-intent
# requests more often than it recovers a genuine 2nd gold. Needs a reliable compound signal to help.
ENABLE_COMPOUND2 = os.getenv("PS_ENABLE_COMPOUND2", "0") == "1"
# CONFORMAL ABSTENTION (conformal.py) — the honest handling of the irreducible residual: genuine
# label ambiguity between adjacent skills. Split-conformal (APS) over the softmax of the reranker
# pool scores, calibrated on labelled tasks, yields a PREDICTION SET guaranteed to contain the true
# skill with probability >= 1-alpha. It does NOT change the judge's top-1 pick; it ADDS a calibrated
# safety net — when the set has >1 member the request is flagged `ambiguous` and the set (top-k with
# a coverage guarantee) is surfaced, so a contested-label case returns "one of these two" instead of
# a confident-but-debatable single answer. Opt-in; needs eval/calibrate_conformal.py to write the cal.
ENABLE_CONFORMAL = os.getenv("PS_ENABLE_CONFORMAL", "0") == "1"
CONFORMAL_ALPHA = float(os.getenv("PS_CONFORMAL_ALPHA", "0.1"))   # target miscoverage → 90% sets
CONFORMAL_TEMP = float(os.getenv("PS_CONFORMAL_TEMP", "1.0"))     # softmax temperature over rerank scores
# Conformal pool width is PINNED independently of JUDGE_TOP_K: the softmax mass depends on how many
# candidates are in the pool, so calibration and inference must use the SAME width or the score
# function silently shifts and the coverage guarantee is void.
CONFORMAL_POOL_K = int(os.getenv("PS_CONFORMAL_POOL_K", "6"))
CONFORMAL_CAL = os.getenv("PS_CONFORMAL_CAL", str(ROOT / "eval" / "conformal_cal.json"))
TOP_K = int(os.getenv("PS_TOP_K", "2"))               # max survivors for a compound request
RRF_K = int(os.getenv("PS_RRF_K", "60"))              # reciprocal-rank-fusion constant
# Relative-dominance gate (pipeline §6): keep a secondary skill only if its rerank is
# >= DOMINANCE_RATIO x the top skill's. Restores precision after multi-query rerank +
# the lowered floor. Evidence-derived: legit secondaries >0.13x top, spurious <0.03x.
DOMINANCE_RATIO = float(os.getenv("PS_DOMINANCE_RATIO", "0.12"))
# Compound recall — per-sub-query winner gate (pipeline §6b). A winner is surfaced if it is a
# CONFIDENT sub-query match (>= SUBQ_STRONG_MIN) OR a decent one (>= SUBQ_MIN) that ALSO clears
# the floor against the ORIGINAL request. The dual gate rejects a wrong skill that rides a
# drifted sub-query's words (high sub-query score, ~0 against the real request) while still
# admitting a genuine secondary intent.
SUBQ_STRONG_MIN = float(os.getenv("PS_SUBQ_STRONG_MIN", "0.80"))
SUBQ_MIN = float(os.getenv("PS_SUBQ_MIN", "0.30"))
# A per-sub-query winner candidate must be at least this relevant to the sub-query to be
# considered (then the one with the best ORIGINAL-request score among those wins).
SUBQ_REL_MIN = float(os.getenv("PS_SUBQ_REL_MIN", "0.15"))
# Relative-leader rescue (pipeline §6c): if nothing clears the floor but the top candidate is
# >= RESCUE_MIN_ABS and >= RESCUE_RATIO x the 2nd, surface it as a low-confidence suggestion.
RESCUE_MIN_ABS = float(os.getenv("PS_RESCUE_MIN_ABS", "0.001"))
RESCUE_RATIO = float(os.getenv("PS_RESCUE_RATIO", "5.0"))

# --- Security-gate policy -----------------------------------------------------
# What to do when a RETRIEVED candidate trips the gate (high-risk injection):
#   "abort" — abort the whole request (spec §2.1 default, conservative)
#   "drop"  — drop just the poisoned candidate and continue with the rest
# This is an explicit, documented policy choice (the spec says do not let it default silently).
RETRIEVED_INJECTION_POLICY = os.getenv("PS_RETRIEVED_INJECTION_POLICY", "abort")

# Tier-3 LLM escalation on the USER-REQUEST gate only (spec §2.1 hook). When Tier-2
# lands in [lower, upper), a cheap LLM adjudicates attack-vs-legitimate and overrides
# Tier-2. The band is deliberately the GRAY ZONE JUST ABOVE the model's calibrated
# high-risk block threshold (~0.64): so Tier-3 only ever RESCUES a would-be block
# (never flips a would-be allow), and near-certain attacks (>= upper) still hard-block
# without consulting the weaker adjudicator. Retrieved content never escalates.
ENABLE_TIER3 = os.getenv("PS_ENABLE_TIER3", "1") == "1"
TIER3_BAND_LOWER = float(os.getenv("PS_TIER3_BAND_LOWER", "0.64"))
# Upper bound widened to 0.98: the ONNX classifier over-flags legitimate technical requests
# (code snippets like `user(id:1){...}`, "breaking change to the authentication system") at
# 0.85-0.96, so those must reach the Tier-3 LLM adjudicator rather than hard-blocking. Only
# near-certain attacks (>= 0.98) block without a second opinion. Re-verified on the red-team set.
TIER3_BAND_UPPER = float(os.getenv("PS_TIER3_BAND_UPPER", "0.98"))
# Multilingual/obfuscation backstop (the English MiniLM classifier is blind to non-English
# and unicode-obfuscated injections). If the classifier ALLOWED text that is non-Latin-heavy
# (>= ratio) — or, on the request path, scored in the moderate band [lower, TIER3_BAND_LOWER) —
# consult the multilingual LLM adjudicator. Evidence: a 115-attack red-team showed multilingual
# detection at 42% before this.
NONLATIN_ESCALATE_RATIO = float(os.getenv("PS_NONLATIN_ESCALATE_RATIO", "0.30"))
MODERATE_ESCALATE_LOWER = float(os.getenv("PS_MODERATE_ESCALATE_LOWER", "0.45"))
# Tier-3 doc-poisoning DETECTION on retrieved skill docs. Tier-2 catches overt injection; a
# poisoned doc that READS LIKE DOCUMENTATION (fake "license activation" that POSTs secrets,
# status-beacon exfil images, sleeper rules, non-English directives) sails under it — the
# red-team's worst family at 5/10 missed. When ON, every retrieved doc the classifier ALLOWED
# is adjudicated once by the multilingual LLM auditor; verdicts are disk-cached by content
# hash, so each doc costs one LLM call EVER and recall-all stays cheap. Detection-only: it can
# flip allow->block, never the reverse. Requires ENABLE_TIER3 (no LLM -> no doc adjudication).
DOC_TIER3 = os.getenv("PS_DOC_TIER3", "1") == "1"
DOCGATE_CACHE = Path(os.getenv("PS_DOCGATE_CACHE", str(ROOT / "logs" / "docgate_cache.json")))
# HTTP proxy OUTPUT filter (MITRE ATLAS AML.T0056 — the second guardrail layer): redact
# untrusted-boundary-marker leakage and secret-shaped strings from model output before it is
# returned to the client.
OUTPUT_FILTER = os.getenv("PS_OUTPUT_FILTER", "1") == "1"
# Rotate the JSONL trace log when it exceeds this many MB (a 278MB trace was observed in the
# wild). 0 disables rotation. LOG_BACKUPS numbered backups are kept (.1 newest) so an attacker
# can't evict the forensic trace of an earlier probe by flooding benign traffic past the cap.
LOG_MAX_MB = float(os.getenv("PS_LOG_MAX_MB", "64"))
LOG_BACKUPS = int(os.getenv("PS_LOG_BACKUPS", "5"))


def rerank_floor() -> float:
    """Calibrated reranker score floor (spec §2.4). Resolution order:
    PS_RERANK_FLOOR env > eval/calibrated_floor.json > 0.5 placeholder.
    The floor lives in the reranker's *native* output space — never assume 0-1.
    """
    env = os.getenv("PS_RERANK_FLOOR")
    if env is not None:
        return float(env)
    cal = ROOT / "eval" / "calibrated_floor.json"
    if cal.exists():
        try:
            return float(json.loads(cal.read_text())["floor"])
        except Exception:
            pass
    return 0.5  # pre-calibration placeholder; run eval/calibrate.py to set the real one
