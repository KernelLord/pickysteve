"""Skill/document registry loader + index-staleness tracking (spec §2.3).

RETRIEVAL-UNIT DECISION (the spec §2.3 open question, decided explicitly):
  * Each markdown file is ONE retrieval unit.
  * A skill folder with multiple files yields multiple units that share a
    `skill_id` but have distinct `unit_id`s (skill_id/filename).
  * Near-duplicate collapse happens AFTER reranking, in assembly: if several
    units from the same skill_id survive the floor, only the best-scoring unit
    is handed to the execution model (so we never ship 3 chunks of one skill).
  This is documented here and in the README so it does not default silently.

STALENESS (spec §2.3): every unit is tagged with the file mtime at index time.
A small JSON cache lets us detect units whose content changed since last index
and flag them, so the system "knows it's serving stale content."
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import config


@dataclass
class Unit:
    unit_id: str
    skill_id: str
    name: str
    description: str
    tags: list[str]
    source: str           # path relative to the registry dir
    content: str          # body (frontmatter stripped)
    last_indexed: float   # file mtime captured at index build
    content_hash: str
    stale: bool = False   # True if file changed since the previous index build

    @property
    def text_for_search(self) -> str:
        return f"{self.name}\n{self.description}\nTags: {', '.join(self.tags)}\n{self.content}"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Minimal frontmatter parser (no PyYAML dependency — keeps deps minimal).

    Handles `key: value` and inline `key: [a, b, c]` lists. Good enough for the
    id/name/description/tags fields the registry uses.
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    block = text[3:end].strip("\n")
    body = text[end + 4:].lstrip("\n")
    meta: dict = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            val = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
        meta[key] = val
    return meta, body


def load_units(registry_dir: Path | None = None) -> list[Unit]:
    registry_dir = registry_dir or config.REGISTRY_DIR
    reg_root = registry_dir.resolve()
    MAX_DOC = 2 << 20   # 2 MiB — a skill doc is small; cap index-time read to bound memory
    prev = _load_cache()
    units: list[Unit] = []
    new_cache: dict = {}
    for path in sorted(registry_dir.rglob("*.md")):
        # A symlinked .md (or one resolving outside the registry) could pull an arbitrary
        # out-of-tree file — /etc/passwd, a secret — into the searchable corpus; skip it. Also
        # cap the read so one giant file can't exhaust memory at index time.
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(reg_root):
                continue
            if path.stat().st_size > MAX_DOC:
                continue
        except OSError:
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(raw)
        rel = path.relative_to(registry_dir).as_posix()
        # skill_id = explicit frontmatter id, else top folder, else filename stem
        parts = path.relative_to(registry_dir).parts
        skill_id = meta.get("id") or (parts[0] if len(parts) > 1 else path.stem)
        unit_id = f"{skill_id}/{path.name}" if len(parts) > 1 else skill_id
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,\s]+", tags) if t.strip()]
        chash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        mtime = path.stat().st_mtime
        stale = unit_id in prev and prev[unit_id].get("hash") != chash
        units.append(Unit(
            unit_id=unit_id, skill_id=skill_id,
            name=meta.get("name") or skill_id, description=meta.get("description") or "",
            tags=tags, source=rel, content=body.strip(),
            last_indexed=mtime, content_hash=chash, stale=stale,
        ))
        new_cache[unit_id] = {"hash": chash, "mtime": mtime}
    _save_cache(new_cache)
    return units


def _load_cache() -> dict:
    if config.INDEX_CACHE.exists():
        try:
            return json.loads(config.INDEX_CACHE.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    config.INDEX_CACHE.parent.mkdir(parents=True, exist_ok=True)
    config.INDEX_CACHE.write_text(json.dumps(cache, indent=2))
