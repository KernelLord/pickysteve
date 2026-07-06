"""CLI: python -m pickysteve "your request here"  [--no-exec]

Loads the registry + models once, runs one request through the full Phase 1
pipeline, prints a human-readable summary, and appends the full trace to the
JSONL log.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time

from .pipeline import Engine

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_STAGES = ["gate", "route", "retrieve", "rerank", "kg", "judge"]
_AMBER = "\x1b[33m"
_DIM = "\x1b[2m"
_BOLD = "\x1b[1m"
_RESET = "\x1b[0m"
_SPIN = "|/-\\"


def _animate_ok() -> bool:
    """Inline animation only when a human is watching: real TTY, not piped,
    not explicitly disabled (NO_COLOR / PICKYSTEVE_NO_ANIM / dumb terminal)."""
    if os.environ.get("PICKYSTEVE_NO_ANIM") or os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    return sys.stderr.isatty()


class _PipelineSpinner:
    """Single-line ANSI pipeline animation on stderr while the engine runs.

    gate > route > retrieve > [rerank /] > kg > judge  — the active stage
    carries a spinner; completed stages dim. Rendered on stderr so stdout
    (the machine-readable result) stays byte-identical to the plain path.
    """

    def __init__(self):
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._start = time.monotonic()

    def _line(self, active: int, tick: int) -> str:
        parts = []
        for i, s in enumerate(_STAGES):
            if i < active:
                parts.append(f"{_DIM}{s} +{_RESET}")
            elif i == active:
                parts.append(f"{_AMBER}{_BOLD}{s} {_SPIN[tick % len(_SPIN)]}{_RESET}")
            else:
                parts.append(f"{_DIM}{s}{_RESET}")
        elapsed = time.monotonic() - self._start
        return " > ".join(parts) + f"  {_DIM}{elapsed:4.1f}s{_RESET}"

    def _run(self):
        tick = 0
        while not self._stop.is_set():
            # advance the "active" stage on a time heuristic (~0.9s/stage,
            # parked on judge) — cosmetic pacing; truth is printed after.
            active = min(int((time.monotonic() - self._start) / 0.9), len(_STAGES) - 1)
            sys.stderr.write("\r\x1b[2K" + self._line(active, tick))
            sys.stderr.flush()
            tick += 1
            self._stop.wait(0.12)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join(timeout=1)
        sys.stderr.write("\r\x1b[2K")  # clear the animation line
        sys.stderr.flush()
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pickysteve", description="Picky-context skill orchestration (Phase 1).")
    ap.add_argument("request", nargs="+", help="the natural-language request")
    ap.add_argument("--no-exec", action="store_true", help="skip the execution model (retrieval only)")
    ap.add_argument("--no-anim", action="store_true", help="disable the inline pipeline animation")
    args = ap.parse_args(argv)
    request = " ".join(args.request)

    eng = Engine()
    if eng.stale_units:
        print(f"[!] stale units since last index: {', '.join(eng.stale_units)}\n", file=sys.stderr)

    if _animate_ok() and not args.no_anim:
        with _PipelineSpinner():
            res = eng.run(request, do_execute=not args.no_exec)
    else:
        res = eng.run(request, do_execute=not args.no_exec)

    print(f"status        : {res.status}")
    print(f"search_query  : {res.search_query}")
    print(f"floor         : {res.floor}")
    if res.tags:
        print(f"tags          : {', '.join(res.tags)}")
    cands = res.detail.get("candidates") or []
    if cands:
        print("candidates    :")
        for c in cands:
            mark = "x" if c.get("cleared_floor") else " "
            print(f"  [{mark}] {c['rerank']!s:>8}  {c['skill_id']:<28} "
                  f"(rrf={c['rrf']}, gate={c['gate_risk']})")
    if res.survivors:
        if _animate_ok() and not args.no_anim and sys.stdout.isatty():
            names = ", ".join(f"{_AMBER}{_BOLD}{s}{_RESET}" for s in res.survivors)
        else:
            names = ", ".join(res.survivors)
        print(f"survivors     : {names}")
    comp = res.detail.get("compatibility")
    if comp:
        print(f"compatible    : {comp['compatible']} — {comp['reason']}")
    print("-" * 60)
    print(res.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
