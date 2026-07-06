"""JSONL trace logging (spec §2.7) — the ONLY observability in Phase 1.

One JSON line per request: timestamp, raw request, router output, every retrieved
candidate with all scores, which cleared the floor, the assembled context, and the
execution output. Review it by hand — that is the Phase 1 eval process.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from . import config

# One process-wide lock serializes rotate + write. Under ThreadingHTTPServer, append() is called
# concurrently; without this, on Windows a rename during another thread's open append handle
# raises a sharing violation (rotation silently never happens — the DoS this exists to prevent),
# and on POSIX a concurrent writer's line lands in the just-renamed backup and is later evicted.
_lock = threading.Lock()


def _rotate_if_needed() -> None:
    """Size-based rotation: an unbounded trace log is a disk-exhaustion DoS (a 278MB one was
    observed). Keep LOG_BACKUPS numbered backups (.1 newest) so an attacker can't evict the
    forensic trace of an earlier probe with two flush waves. Caller holds _lock."""
    if config.LOG_MAX_MB <= 0 or not config.LOG_PATH.exists():
        return
    try:
        if config.LOG_PATH.stat().st_size < config.LOG_MAX_MB * 1024 * 1024:
            return
        keep = max(1, config.LOG_BACKUPS)
        oldest = config.LOG_PATH.with_name(config.LOG_PATH.name + f".{keep}")
        oldest.unlink(missing_ok=True)
        for i in range(keep - 1, 0, -1):     # shift .i -> .i+1
            src = config.LOG_PATH.with_name(config.LOG_PATH.name + f".{i}")
            if src.exists():
                src.replace(config.LOG_PATH.with_name(config.LOG_PATH.name + f".{i + 1}"))
        config.LOG_PATH.replace(config.LOG_PATH.with_name(config.LOG_PATH.name + ".1"))
    except OSError:
        pass


def append(record: dict) -> None:
    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": datetime.now(timezone.utc).isoformat(), **record}
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _lock:                               # rotate + write atomically w.r.t. other threads
        _rotate_if_needed()
        with config.LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
