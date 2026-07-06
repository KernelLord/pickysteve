"""One-command connector installer — writes the correct PickySteve config into each
agent's actual config file (with a backup), so connecting is a single command.

  python -m pickysteve.connectors.install --list             # show agents + detected state
  python -m pickysteve.connectors.install --agent cursor      # install for one agent
  python -m pickysteve.connectors.install --all               # install for every DETECTED agent
  python -m pickysteve.connectors.install --agent codex --dry-run   # preview, write nothing

Safety:
  * JSON configs are deep-merged (only the mcpServers/servers/mcp key is touched — existing
    settings are preserved). TOML configs get an appended [mcp_servers.pickysteve] section
    only if absent (append-only, never rewrites). YAML/comment-heavy and proxy/CLI agents are
    NOT auto-edited — exact manual steps are printed instead.
  * Every file write is preceded by a `<file>.pickysteve.bak` backup.
  * Idempotent: re-running reports "already configured" instead of duplicating.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .. import config

PYBIN = sys.executable
PROJ = str(config.ROOT)
HOME = Path.home()
APPDATA = Path(os.getenv("APPDATA", str(HOME / "AppData" / "Roaming")))

MCP_ARGS = ["-m", "pickysteve.connectors.mcp_server"]


def _std_entry():            # standard mcpServers entry
    return {"command": PYBIN, "args": MCP_ARGS, "cwd": PROJ}


def _vscode_entry():         # VS Code / Copilot "servers" style
    return {"type": "stdio", "command": PYBIN, "args": MCP_ARGS}


def _opencode_entry():       # OpenCode "mcp" style
    return {"type": "local", "command": [PYBIN, *MCP_ARGS], "enabled": True}


# kind: json_mcp (deep-merge under `root`), toml_section (append if absent), manual
AGENTS = {
    "claude-code": {"kind": "json_mcp", "path": config.ROOT / ".mcp.json", "root": "mcpServers",
                    "entry": _std_entry, "note": "project-scoped .mcp.json (or: claude mcp add pickysteve -- ...)"},
    "codex":     {"kind": "toml_section", "path": HOME / ".codex" / "config.toml"},
    "cursor":    {"kind": "json_mcp", "path": HOME / ".cursor" / "mcp.json", "root": "mcpServers", "entry": _std_entry},
    "windsurf":  {"kind": "json_mcp", "path": HOME / ".codeium" / "windsurf" / "mcp_config.json", "root": "mcpServers", "entry": _std_entry},
    "cline":     {"kind": "json_mcp", "path": APPDATA / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json", "root": "mcpServers", "entry": _std_entry},
    "roo":       {"kind": "json_mcp", "path": APPDATA / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "mcp_settings.json", "root": "mcpServers", "entry": _std_entry},
    "gemini":    {"kind": "json_mcp", "path": HOME / ".gemini" / "settings.json", "root": "mcpServers", "entry": _std_entry},
    "qwen":      {"kind": "json_mcp", "path": HOME / ".qwen" / "settings.json", "root": "mcpServers", "entry": _std_entry},
    "kimi":      {"kind": "toml_section", "path": HOME / ".kimi" / "config.toml"},
    "zeroclaw":  {"kind": "toml_section", "path": HOME / ".zeroclaw" / "config.toml"},
    "opencode":  {"kind": "json_mcp", "path": HOME / ".config" / "opencode" / "opencode.json", "root": "mcp", "entry": _opencode_entry},
    "copilot":   {"kind": "json_mcp", "path": config.ROOT / ".vscode" / "mcp.json", "root": "servers", "entry": _vscode_entry,
                  "note": "workspace .vscode/mcp.json"},
    # not auto-edited (YAML / proxy / CLI) — printed instructions instead
    "goose":     {"kind": "manual", "msg": "Add a stdio extension in ~/.config/goose/config.yaml (or `goose configure`):\n"
                  f"  extensions:\n    pickysteve:\n      type: stdio\n      cmd: {PYBIN}\n      args: [\"-m\",\"pickysteve.connectors.mcp_server\"]\n      enabled: true"},
    "openhands": {"kind": "manual", "msg": f"Start the proxy (python -m pickysteve.connectors.http_server) and set the LLM base_url env: LLM_BASE_URL=http://localhost:8077/v1"},
    "hermes":    {"kind": "manual", "msg": "In ~/.hermes/config.yaml set:\n  model:\n    provider: custom\n    base_url: \"http://localhost:8077/v1\""},
    "aider":     {"kind": "manual", "msg": "Run the proxy, then: aider --openai-api-base http://localhost:8077/v1 --openai-api-key sk-x --model pickysteve"},
    "openclaw":  {"kind": "manual", "msg": "MCP: ~/.openclaw/.mcp.json mcpServers entry, or proxy via OPENAI_BASE_URL=http://localhost:8077/v1, or REST /pick."},
    "nanoclaw":  {"kind": "manual", "msg": "Proxy via OPENAI_BASE_URL=http://localhost:8077/v1, REST POST /pick, or import: Engine().pick(req)."},
}


def _backup(path: Path):
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".pickysteve.bak"))


def _install_json(spec, dry):
    path: Path = spec["path"]
    root, entry = spec["root"], spec["entry"]()
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except Exception as e:
            return f"SKIP {path}: existing file is not valid JSON ({e})"
    if not isinstance(data, dict):
        return f"SKIP {path}: top-level JSON is not an object"
    bucket = data.setdefault(root, {})
    if not isinstance(bucket, dict):
        return f"SKIP {path}: '{root}' is not an object"
    if bucket.get("pickysteve") == entry:
        return f"ok   {path}  (already configured)"
    bucket["pickysteve"] = entry
    if dry:
        return f"WOULD WRITE {path}\n{json.dumps({root: {'pickysteve': entry}}, indent=2)}"
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"WROTE {path}  (mcp entry under '{root}')"


def _install_toml(spec, dry):
    path: Path = spec["path"]
    # TOML LITERAL strings (single-quoted) so Windows backslashes aren't treated as escapes
    section = (
        "\n[mcp_servers.pickysteve]\n"
        f"command = '{PYBIN}'\n"
        'args = ["-m", "pickysteve.connectors.mcp_server"]\n'
        f"cwd = '{PROJ}'\n"
    )
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if "[mcp_servers.pickysteve]" in existing:
        return f"ok   {path}  (already configured)"
    if dry:
        return f"WOULD APPEND to {path}:\n{section}"
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(("" if existing.endswith("\n") or not existing else "\n") + section)
    return f"APPENDED [mcp_servers.pickysteve] to {path}"


def _uninstall_json(spec, dry):
    path: Path = spec["path"]
    root = spec["root"]
    if not path.exists():
        return f"{path}  (nothing to remove)"
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception as e:
        return f"SKIP {path}: not valid JSON ({e})"
    bucket = data.get(root) if isinstance(data, dict) else None
    if not isinstance(bucket, dict) or "pickysteve" not in bucket:
        return f"{path}  (not configured)"
    if dry:
        return f"WOULD REMOVE pickysteve from '{root}' in {path}"
    _backup(path)
    del bucket["pickysteve"]
    if not bucket:
        data.pop(root, None)
    if not data:  # file is now empty — remove it (we created it)
        path.unlink()
        return f"REMOVED entry + deleted now-empty {path}"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"REMOVED pickysteve from {path}"


def _uninstall_toml(spec, dry):
    path: Path = spec["path"]
    if not path.exists():
        return f"{path}  (nothing to remove)"
    text = path.read_text(encoding="utf-8")
    if "[mcp_servers.pickysteve]" not in text:
        return f"{path}  (not configured)"
    if dry:
        return f"WOULD REMOVE [mcp_servers.pickysteve] from {path}"
    _backup(path)
    lines = text.splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if l.strip() == "[mcp_servers.pickysteve]")
    end = start + 1
    while end < len(lines) and not lines[end].lstrip().startswith("["):
        end += 1
    if start > 0 and lines[start - 1].strip() == "":  # drop the blank line we prepended
        start -= 1
    del lines[start:end]
    path.write_text("".join(lines), encoding="utf-8")
    return f"REMOVED [mcp_servers.pickysteve] from {path}"


def _detected(spec) -> bool:
    if spec["kind"] == "manual":
        return False
    # detected if the config file OR its parent dir exists
    p: Path = spec["path"]
    return p.exists() or p.parent.exists()


def run(agent: str, dry: bool, uninstall: bool = False) -> str:
    spec = AGENTS[agent]
    note = f"  [{spec['note']}]" if spec.get("note") else ""
    if spec["kind"] == "manual":
        if uninstall:
            return f"manual {agent}: undo manually — {spec['msg'].splitlines()[0]}"
        return f"manual {agent}: {spec['msg']}"
    if spec["kind"] == "json_mcp":
        fn = _uninstall_json if uninstall else _install_json
        return f"[{agent}]{note} " + fn(spec, dry)
    if spec["kind"] == "toml_section":
        fn = _uninstall_toml if uninstall else _install_toml
        return f"[{agent}]{note} " + fn(spec, dry)
    return f"[{agent}] unknown kind"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pickysteve-install")
    ap.add_argument("--agent", help="agent name (see --list)")
    ap.add_argument("--all", action="store_true", help="install for every detected agent")
    ap.add_argument("--list", action="store_true", help="list agents + detected state")
    ap.add_argument("--dry-run", action="store_true", help="preview without writing")
    ap.add_argument("--uninstall", action="store_true", help="remove the pickysteve entry (restorable via *.pickysteve.bak)")
    args = ap.parse_args(argv)

    mode = "uninstall" if args.uninstall else "install"
    print(f"PickySteve {mode}er  (python={PYBIN})\n")
    if args.list or not (args.agent or args.all):
        print(f"{'agent':14} {'kind':12} {'detected':9} path")
        for name, spec in AGENTS.items():
            p = spec.get("path", "")
            print(f"{name:14} {spec['kind']:12} {str(_detected(spec)):9} {p}")
        print("\nUse --agent <name> or --all (add --dry-run to preview).")
        return 0

    targets = [a for a in AGENTS if _detected(AGENTS[a])] if args.all else [args.agent]
    if args.all:
        print(f"detected agents: {', '.join(targets) or '(none)'}\n")
    for a in targets:
        if a not in AGENTS:
            print(f"unknown agent: {a}  (see --list)"); continue
        try:
            print(run(a, args.dry_run, args.uninstall))
        except Exception as e:  # noqa: BLE001
            print(f"[{a}] ERROR: {e}")
    # show the manual ones as a reminder (install only)
    if args.all and not args.uninstall:
        print("\nManual (proxy/CLI/YAML) agents:")
        for a, s in AGENTS.items():
            if s["kind"] == "manual":
                print(f"  - {a}: {s['msg'].splitlines()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
