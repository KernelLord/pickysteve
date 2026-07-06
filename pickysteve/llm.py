"""Model client for both roles the spec needs (§2.2 router, §2.6 execution).

Defaults to Ollama's NATIVE /api/chat with think:false — qwen3 is a thinking model
and the OpenAI-compatible endpoint does NOT honor thinking control, so it dumps all
output into a `reasoning` channel and returns empty `content` (and is ~20x slower).
The native endpoint with think:false returns clean content fast.

Set PS_OLLAMA_NATIVE=0 (or point PS_LLM_BASE_URL at a non-Ollama host) to use the
OpenAI-compatible path via the `openai` SDK instead.

Carries the retry counter the spec calls for (§1.2).
"""
from __future__ import annotations

import json
import re
import time
import urllib.request

from . import config

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_openai_client = None


def strip_think(text: str) -> str:
    return _THINK_RE.sub("", text or "").strip()


def _native_chat(model, system, user, temperature, max_tokens, json_format, timeout):
    base = config.LLM_BASE_URL.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = base.rstrip("/") + "/api/chat"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "think": False,            # the whole point — disable qwen3 reasoning channel
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if json_format:
        body["format"] = "json"
    data = json.dumps(body).encode("utf-8")

    def _post(payload: bytes) -> str:
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out = json.loads(resp.read())
        return (out.get("message", {}) or {}).get("content", "") or ""

    try:
        return _post(data)
    except urllib.error.HTTPError as e:
        # some models reject `think`; retry once without it
        if e.code == 400 and "think" in body:
            body.pop("think", None)
            return _post(json.dumps(body).encode("utf-8"))
        raise


def _openai_chat(model, system, user, temperature, max_tokens, json_format):
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    kwargs = {}
    if json_format:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _openai_client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature, max_tokens=max_tokens, **kwargs,
    )
    return resp.choices[0].message.content or ""


def chat(model, system, user, *, temperature=0.0, max_tokens=1024,
         json_mode=False, retries=2, timeout=300) -> tuple[str, int]:
    """Return (text, attempts_used). Raises after exhausting retries."""
    last_err = None
    for attempt in range(1, retries + 2):
        try:
            if config.OLLAMA_NATIVE:
                text = _native_chat(model, system, user, temperature, max_tokens, json_mode, timeout)
            else:
                text = _openai_chat(model, system, user, temperature, max_tokens, json_mode)
            return strip_think(text), attempt
        except Exception as e:  # noqa: BLE001 — resilience over precision in the request path
            last_err = e
            time.sleep(0.4 * attempt)
    raise RuntimeError(f"LLM call failed after {retries + 1} attempts: {last_err}")


def extract_json(text: str) -> dict | None:
    text = strip_think(text)
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None
