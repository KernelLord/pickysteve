"""PickySteve HTTP connector — stdlib only (zero extra dependencies).

Endpoints:
  GET  /health                 -> liveness + registry size
  GET  /v1/models              -> OpenAI-style model list (advertises "pickysteve")
  POST /pick                   -> {"request": "..."} -> the picky-context bundle (JSON)
  POST /v1/chat/completions    -> OpenAI-compatible. Runs pick() on the last user message,
                                  injects the focused skill bundle as a system message, then
                                  forwards to the upstream model. Point any tool that accepts a
                                  custom OpenAI base URL at http://localhost:8077/v1 .

Run:  .venv/Scripts/python.exe -m pickysteve.connectors.http_server [--port 8077]
Upstream is the configured local Ollama by default; override with PS_UPSTREAM_* / PS_LLM_*.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import config

_engine = None

# --- output filter (MITRE ATLAS AML.T0056 — the second guardrail layer) -----------------
# Input is gated, but a successful injection (or an over-helpful model) can still LEAK through
# the OUTPUT: internal untrusted-data boundary markers (prompt-structure disclosure) or
# secret-shaped strings the model echoed from its context. Redact both before responding.
# All patterns compile with re.ASCII so \b/\w anchor on ASCII word chars — otherwise a secret
# glued to a Unicode letter ("жAKIA...") has no word boundary and sails through. IGNORECASE on
# the boundary markers because models re-case text when paraphrasing. Regex filtering is a
# SECOND layer with known limits (a model told to base64/split a secret defeats any regex —
# the naive-base64 case is caught below, the general case needs semantic output scanning).
_BOUNDARY_RE = re.compile(r"<<(?:UNTRUSTED|END)-[0-9a-f]{4,}>>|</?retrieved_skill[^>\n]*>",
                          re.ASCII | re.IGNORECASE)
_SECRET_RES = [
    # PEM: swallow the whole block (header + base64 body + END line when present) — redacting
    # only the header line would hand the client the entire key body.
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[A-Za-z0-9+/=\s]*"
               r"(?:-----END [A-Z ]*PRIVATE KEY-----)?", re.ASCII),
    re.compile(r"\b(?:sk|rk)-[A-Za-z0-9_-]{20,}\b", re.ASCII),             # OpenAI-style keys
    re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{10,}\b", re.ASCII), # Stripe secret keys
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b", re.ASCII),                    # Google API keys
    re.compile(r"\bAKIA[0-9A-Z]{16}\b", re.ASCII),                         # AWS access key id
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b", re.ASCII),               # GitHub tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b", re.ASCII),             # GitHub fine-grained
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", re.ASCII),             # Slack tokens
    re.compile(r"\beyJ[\w-]{20,}\.eyJ[\w-]{20,}\.[\w-]{10,}\b", re.ASCII), # JWT
]
_B64_RE = re.compile(r"\b[A-Za-z0-9+/]{24,}={0,2}", re.ASCII)


def _filter_output(content: str) -> tuple[str, int]:
    """Redact boundary-marker leakage + secret-shaped strings from model output.
    Returns (filtered_text, redaction_count)."""
    hits = 0

    def _sub(m):
        nonlocal hits
        hits += 1
        return "[REDACTED]"

    content = _BOUNDARY_RE.sub(_sub, content)
    for pat in _SECRET_RES:
        content = pat.sub(_sub, content)
    # Naive base64 exfil ("base64-encode the key, then output it"): decode candidate runs and
    # re-scan the decoded text; redact the blob if it hides a secret or boundary marker.
    for m in list(_B64_RE.finditer(content)):
        blob = m.group(0)
        try:
            pad = blob + "=" * (-len(blob) % 4)
            dec = base64.b64decode(pad, validate=True).decode("utf-8", "ignore")
        except (ValueError, binascii.Error):   # not valid base64 — leave it be
            continue
        if _BOUNDARY_RE.search(dec) or any(p.search(dec) for p in _SECRET_RES):
            content = content.replace(blob, "[REDACTED]")
            hits += 1
    return content, hits


_FILTER_SKIP_KEYS = frozenset({"context_block"})


def _filter_obj(obj, _in_skip=False):
    """Apply _filter_output to every string leaf of a JSON-able structure — for the /pick response
    and the /chat metadata, where the router's `search_query` can echo a secret the user pasted.

    CRITICAL: never filter under `context_block`. That field is the assembled bundle the CALLER
    injects into a downstream model, and its `<<UNTRUSTED-nonce>>` boundary markers are DELIBERATE
    — redacting them would silently strip the untrusted-data boundary the whole pipeline exists to
    provide. (Registry content is also gate-checked and secret-free, so there is nothing to redact
    there anyway.)"""
    if _in_skip:                       # under a skipped key — pass through untouched
        return obj, 0
    total = 0
    if isinstance(obj, str):
        return _filter_output(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out[k], n = _filter_obj(v, _in_skip=(k in _FILTER_SKIP_KEYS))
            total += n
        return out, total
    if isinstance(obj, list):
        out = []
        for v in obj:
            fv, n = _filter_obj(v)
            out.append(fv)
            total += n
        return out, total
    return obj, 0


class _BoundedHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with a hard concurrency cap. Each request can pin a worker thread for up
    to the 600s upstream timeout, so an unbounded thread-per-connection model is a thread/memory
    exhaustion vector; refuse fast when saturated instead of spawning without limit."""
    daemon_threads = True
    max_conn = int(os.getenv("PS_HTTP_MAX_CONN", "32"))

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._sem = threading.BoundedSemaphore(self.max_conn)

    def process_request(self, request, client_address):
        if not self._sem.acquire(blocking=False):
            self.shutdown_request(request)   # at capacity — drop this connection immediately
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._sem.release()


def _eng():
    global _engine
    if _engine is None:
        from ..pipeline import Engine
        _engine = Engine()
    return _engine


def _forward(messages: list, model: str) -> str:
    """Forward the (context-injected) messages to the upstream model. Defaults to the local
    Ollama native /api/chat with think:false; returns the assistant text."""
    base = config.LLM_BASE_URL.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = base + "/api/chat"
    body = {"model": config.EXEC_MODEL, "messages": messages, "think": False,
            "stream": False, "options": {"temperature": 0}}
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.loads(r.read())
    return (out.get("message", {}) or {}).get("content", "") or ""


def _completion(content: str, model: str) -> dict:
    return {"id": "chatcmpl-pickysteve", "object": "chat.completion", "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}


class Handler(BaseHTTPRequestHandler):
    # A routing request is a few KB of text; cap the body hard so a malicious/lost client can't
    # exhaust memory with a giant (or lying) Content-Length. Rejected BEFORE any bytes are read.
    MAX_BODY = 1 << 20   # 1 MiB
    timeout = 30         # per-connection socket timeout — closes slowloris/half-open clients
    enforce_host = True  # set False in main() when PS_HTTP_ALLOW_REMOTE=1 (operator opted into remote)

    def log_message(self, *a):  # keep stdout/stderr quiet
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            raise ValueError("invalid Content-Length")
        if n < 0 or n > self.MAX_BODY:
            raise ValueError("request body too large")
        raw = self.rfile.read(n) if n else b"{}"
        obj = json.loads(raw or b"{}")
        if not isinstance(obj, dict):   # a JSON list/scalar body would crash body.get() downstream
            raise ValueError("body must be a JSON object")
        return obj

    def _host_ok(self) -> bool:
        """DNS-rebinding / browser-CSRF defense: localhost-binding stops remote SOCKETS but not a
        malicious web page POSTing to http://localhost:PORT. Require the Host header to be loopback
        unless the operator explicitly opted into remote binding (PS_HTTP_ALLOW_REMOTE=1)."""
        if not self.enforce_host:
            return True
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip().strip("[]").lower()
        return host in ("127.0.0.1", "localhost", "::1", "")

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "forbidden host"})
        if self.path == "/health":
            self._json(200, {"status": "ok", "registry": len(_eng().units)})
        elif self.path in ("/v1/models", "/models"):
            self._json(200, {"object": "list", "data": [{"id": "pickysteve", "object": "model",
                                                         "owned_by": "pickysteve"}]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok():
            return self._json(403, {"error": "forbidden host"})
        try:
            body = self._read()
        except Exception:
            return self._json(400, {"error": "invalid JSON body"})
        if self.path == "/pick":
            req = body.get("request") or body.get("query") or ""
            resp = _eng().pick(str(req))
            if config.OUTPUT_FILTER:
                resp, _ = _filter_obj(resp)
            return self._json(200, resp)
        if self.path in ("/v1/chat/completions", "/chat/completions"):
            return self._chat(body)
        self._json(404, {"error": "not found"})

    def _chat(self, body: dict):
        messages = body.get("messages") or []
        model = body.get("model") or "pickysteve"
        # last user message = the request to pick context for
        req = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                c = m.get("content", "")
                req = c if isinstance(c, str) else json.dumps(c)
                break
        picked = _eng().pick(req)
        injected = list(messages)
        if picked["status"] == "ok" and picked["context_block"]:
            injected.insert(0, {"role": "system", "content": picked["context_block"]})
        elif picked["status"] != "ok":
            # surface the no-match / rejection to the model as context, but still answer
            injected.insert(0, {"role": "system", "content":
                                f"[pickysteve: {picked['status']} — {picked['message']}]"})
        try:
            content = _forward(injected, model)
        except Exception as e:  # noqa: BLE001 — log detail server-side, return a generic error
            print(f"[pickysteve-http] upstream forward failed: {e}", file=sys.stderr, flush=True)
            return self._json(502, {"error": "upstream forward failed"})
        redactions = 0
        if config.OUTPUT_FILTER:
            content, redactions = _filter_output(content)
        resp = _completion(content, model)
        meta = {"status": picked["status"], "survivors": picked["survivors"],
                "search_query": picked["search_query"]}
        if config.OUTPUT_FILTER:
            meta, meta_hits = _filter_obj(meta)   # search_query can echo a pasted secret
            redactions += meta_hits
        resp["pickysteve"] = meta
        if redactions:
            resp["pickysteve"]["output_redactions"] = redactions

        if body.get("stream"):
            # minimal SSE: one content chunk + a stop chunk + [DONE]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            chunk = {"id": "chatcmpl-pickysteve", "object": "chat.completion.chunk", "model": model,
                     "choices": [{"index": 0, "delta": {"role": "assistant", "content": content},
                                  "finish_reason": None}]}
            stop = {"id": "chatcmpl-pickysteve", "object": "chat.completion.chunk", "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            for ev in (chunk, stop):
                self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        else:
            self._json(200, resp)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pickysteve-http")
    ap.add_argument("--port", type=int, default=8077)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args(argv)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        # The server has NO authentication — it forwards to your local model and executes the
        # picky-context pipeline for anyone who can reach it. Binding beyond localhost exposes it
        # to the network; require an explicit opt-in so it never happens by accident.
        if os.getenv("PS_HTTP_ALLOW_REMOTE") != "1":
            print(f"[pickysteve-http] refusing to bind {args.host}: no auth on this server. "
                  f"Set PS_HTTP_ALLOW_REMOTE=1 to override (and put it behind a trusted proxy).",
                  file=sys.stderr, flush=True)
            return 2
        print(f"[pickysteve-http] WARNING: binding {args.host} with NO authentication.",
              file=sys.stderr, flush=True)
        Handler.enforce_host = False   # operator opted into remote; Host allow-list would reject it
    eng = _eng()  # warm the models before accepting traffic
    if config.DOC_TIER3 and config.ENABLE_TIER3:
        # Warm the doc-poisoning gate over the whole registry BEFORE serving, so the first
        # request never pays the cold-cache N-call latency and concurrent cold requests can't
        # stampede the local model. Flagged legit docs would abort every request — warn loudly.
        from .. import security_gate
        print("[pickysteve-http] warming doc-poisoning gate over registry...",
              file=sys.stderr, flush=True)
        n, flagged = security_gate.warm_docs(eng.units)
        if flagged:
            print(f"[pickysteve-http] WARNING: doc-gate flagged {len(flagged)}/{n} registry docs "
                  f"as poison; with abort policy these will abort EVERY request: {flagged}",
                  file=sys.stderr, flush=True)
        else:
            print(f"[pickysteve-http] doc-gate warm: {n}/{n} registry docs clean.",
                  file=sys.stderr, flush=True)
    srv = _BoundedHTTPServer((args.host, args.port), Handler)
    print(f"[pickysteve-http] listening on http://{args.host}:{args.port}  "
          f"(/pick, /v1/chat/completions)", file=sys.stderr, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
