"""Connectivity test — proves the MCP server and HTTP/proxy connectors actually work,
the way a real agent would drive them.

  MCP : spawn the stdio server, run initialize -> tools/list -> tools/call(pick_context)
        -> tools/call(list_skills), validating each JSON-RPC response.
  HTTP: spawn the server, hit /health, POST /pick, GET /v1/models, and POST
        /v1/chat/completions (context-injection + upstream forward).

Run:  .venv/Scripts/python.exe eval/test_connectors.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
_p, _f = 0, 0


def check(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1; print(f"  PASS  {name}  {detail}")
    else:
        _f += 1; print(f"  FAIL  {name}  {detail}")


def test_mcp():
    print("\n[MCP] stdio JSON-RPC server")
    proc = subprocess.Popen([PY, "-m", "pickysteve.connectors.mcp_server"], cwd=str(ROOT),
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, bufsize=1)

    def rpc(obj, read=True):
        proc.stdin.write(json.dumps(obj) + "\n"); proc.stdin.flush()
        if not read:
            return None
        line = proc.stdout.readline()
        return json.loads(line) if line.strip() else None

    try:
        init = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        check("initialize returns serverInfo=pickysteve",
              init and init.get("result", {}).get("serverInfo", {}).get("name") == "pickysteve",
              f"protocol={init and init.get('result',{}).get('protocolVersion')}")
        rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, read=False)
        tl = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = [t["name"] for t in tl.get("result", {}).get("tools", [])]
        check("tools/list advertises pick_context + list_skills",
              "pick_context" in names and "list_skills" in names, f"tools={names}")
        call = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "pick_context",
                               "arguments": {"request": "review my rust code for ownership problems"}}})
        text = (call.get("result", {}).get("content") or [{}])[0].get("text", "")
        check("tools/call pick_context returns rust-reviewer context",
              "rust-reviewer" in text and "retrieved_skill" in text, f"len={len(text)}")
        call2 = rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                     "params": {"name": "list_skills", "arguments": {}}})
        text2 = (call2.get("result", {}).get("content") or [{}])[0].get("text", "")
        check("tools/call list_skills lists the registry",
              "rust-reviewer" in text2 and "incident-response" in text2, f"len={len(text2)}")
    finally:
        proc.stdin.close()
        proc.terminate()


def test_http():
    print("\n[HTTP] REST /pick + OpenAI-compatible proxy")
    port = 8079
    proc = subprocess.Popen([PY, "-m", "pickysteve.connectors.http_server", "--port", str(port)],
                            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"

    def get(path):
        with urllib.request.urlopen(base + path, timeout=30) as r:
            return json.loads(r.read())

    def post(path, obj, timeout=120):
        req = urllib.request.Request(base + path, data=json.dumps(obj).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    try:
        # wait for the server to warm (Engine load)
        ready = False
        for _ in range(60):
            try:
                if get("/health").get("status") == "ok":
                    ready = True; break
            except Exception:
                time.sleep(1)
        check("server comes up and /health is ok", ready)
        models = get("/v1/models")
        check("/v1/models advertises pickysteve",
              any(m["id"] == "pickysteve" for m in models.get("data", [])))
        pick = post("/pick", {"request": "my docker image is way too big"})
        check("/pick routes docker request to docker-optimizer",
              "docker-optimizer" in (pick.get("survivors") or []), f"survivors={pick.get('survivors')}")
        chat = post("/v1/chat/completions",
                    {"model": "pickysteve", "messages": [{"role": "user", "content":
                     "audit my AMM contract for oracle manipulation"}]}, timeout=300)
        ps = chat.get("pickysteve", {})
        check("/v1/chat/completions injects context (defi-amm-security) + forwards",
              "defi-amm-security" in (ps.get("survivors") or []) and chat["choices"][0]["message"]["content"],
              f"survivors={ps.get('survivors')}")
    finally:
        proc.terminate()


def main():
    test_mcp()
    test_http()
    print(f"\n{'='*50}\n{_p} passed, {_f} failed")
    return 1 if _f else 0


if __name__ == "__main__":
    raise SystemExit(main())
