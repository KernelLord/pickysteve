"""PickySteve MCP server — stdio JSON-RPC 2.0, hand-rolled (zero extra dependencies).

Exposes two tools any MCP-speaking agent can call:
  * pick_context(request)  -> the focused, untrusted-data-boundaried skill bundle to inject
  * list_skills()          -> the registry (skill id + description)

Run:  .venv/Scripts/python.exe -m pickysteve.connectors.mcp_server
Transport: newline-delimited JSON-RPC over stdio (the MCP stdio transport). All diagnostics
go to stderr so stdout stays a clean JSON-RPC stream.
"""
from __future__ import annotations

import json
import re
import sys

from .. import __version__

_engine = None
PROTOCOL_VERSION = "2024-11-05"

# list_skills returns registry metadata (skill_id + description) straight to the host agent. That
# metadata comes from each doc's FRONTMATTER, which the security gate NEVER scans (the gate only
# sees u.content, the frontmatter-stripped body) — so a poisoned frontmatter description is an
# un-gated injection channel into the agent. We close it here:
#   * descriptions are gated through security_gate.scan() and replaced with a safe placeholder if
#     blocked (metadata is low-stakes — withhold the one bad line, never brick the whole listing);
#   * skill_ids are sanitized to a slug-safe charset. skill_id is ALREADY mostly constrained
#     (registry.py derives it from a path folder/stem, or an explicit frontmatter `id`); the
#     explicit-id case is attacker-controllable free text, so we strip it to [A-Za-z0-9._/-] rather
#     than spend a second gate call on a short slug.
# Descriptions are static per process (registry is pinned in memory at Engine init), so each unique
# description is scanned at most ONCE and the verdict cached.
_DESC_PLACEHOLDER = "[description withheld by security gate]"
_desc_cache: dict[str, str] = {}
_SKILL_ID_UNSAFE = re.compile(r"[^A-Za-z0-9._/-]")


def _safe_skill_id(skill_id) -> str:
    sid = _SKILL_ID_UNSAFE.sub("", str(skill_id))[:128]
    return sid or "skill"


def _safe_description(text) -> str:
    text = str(text or "")
    if not text:
        return ""
    cached = _desc_cache.get(text)
    if cached is not None:
        return cached
    try:
        from .. import security_gate
        safe = text if security_gate.scan(text, "retrieved_skill").allowed else _DESC_PLACEHOLDER
    except Exception:
        safe = _DESC_PLACEHOLDER   # fail-closed: an errored gate withholds the description
    _desc_cache[text] = safe
    return safe

TOOLS = [
    {
        "name": "pick_context",
        "description": (
            "Given a natural-language coding task, return ONLY the confidently-relevant "
            "skills from the registry as a context block to inject (wrapped as untrusted "
            "reference DATA, not instructions). Picky: returns a focused bundle, or a "
            "clarifying question when nothing matches confidently. Use this before doing "
            "the task to load just the skills it needs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"request": {"type": "string", "description": "the task/request in natural language"}},
            "required": ["request"],
        },
    },
    {
        "name": "list_skills",
        "description": "List every skill in the registry (id + one-line description).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _log(*a):
    print("[pickysteve-mcp]", *a, file=sys.stderr, flush=True)


def _engine_get():
    global _engine
    if _engine is None:
        _log("loading engine (models)…")
        from ..pipeline import Engine
        _engine = Engine()
        _log(f"engine ready: {len(_engine.units)} units")
    return _engine


def _call_tool(name: str, args: dict) -> dict:
    try:
        if name == "pick_context":
            r = _engine_get().pick(str(args.get("request", "")))
            if r["status"] == "ok":
                text = r["context_block"] + f"\n\n[picked skills: {', '.join(r['survivors'])}]"
            else:
                text = f"[{r['status']}] {r['message']}"
            return {"content": [{"type": "text", "text": text}], "isError": False}
        if name == "list_skills":
            units = _engine_get().units
            lines = sorted({f"- {_safe_skill_id(u.skill_id)}: {_safe_description(u.description)}" for u in units})
            return {"content": [{"type": "text", "text": "\n".join(lines)}], "isError": False}
        return {"content": [{"type": "text", "text": f"unknown tool: {name}"}], "isError": True}
    except Exception as e:  # noqa: BLE001 — log detail to stderr, return a generic error to the caller
        _log(f"tool '{name}' error: {e}")
        return {"content": [{"type": "text", "text": "internal error handling the tool call"}], "isError": True}


def _dispatch(method: str, params: dict):
    """Return a result dict for a request method, or None for notification/unknown."""
    if method == "initialize":
        return {"protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "pickysteve", "version": __version__}}
    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return None  # notification — no response
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "prompts/list":
        return {"prompts": []}
    if method == "resources/list":
        return {"resources": []}
    if method == "tools/call":
        return _call_tool(params.get("name", ""), params.get("arguments") or {})
    return None


def main() -> int:
    _log(f"starting (stdio, protocol {PROTOCOL_VERSION})")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if not isinstance(msg, dict):   # a valid-JSON non-object line would crash msg.get() → drop it
            continue
        mid = msg.get("id")
        result = _dispatch(msg.get("method", ""), msg.get("params") or {})
        if mid is None:
            continue  # notification — no reply
        if result is None:
            resp = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}}
        else:
            resp = {"jsonrpc": "2.0", "id": mid, "result": result}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
