"""Interactive setup: choose the model that powers PickySteve, then write it to .env.

Run:  python -m pickysteve.setup

Picks the provider + model for routing/judging/execution and saves them to a .env in
the repo root (git-ignored). Existing PS_* environment variables always override .env.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"

# id -> (label, base_url or None to prompt, api_key default or None to prompt, model default or None)
PROVIDERS = {
    "1": ("Local Ollama  — offline, no API key, zero cost",
          "http://localhost:11434/v1", "ollama", "qwen3:8b"),
    "2": ("OpenAI",
          "https://api.openai.com/v1", None, "gpt-4o-mini"),
    "3": ("Anthropic Claude  (OpenAI-compatible endpoint)",
          "https://api.anthropic.com/v1", None, "claude-3-5-sonnet-20241022"),
    "4": ("OpenRouter  — Claude / Gemini / Llama / etc. behind one key",
          "https://openrouter.ai/api/v1", None, "anthropic/claude-3.5-sonnet"),
    "5": ("Other OpenAI-compatible endpoint  (Together, Fireworks, Groq, vLLM, LM Studio, ...)",
          None, None, None),
}


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        raise SystemExit(1)
    return val or (default or "")


def main() -> int:
    print("\nPickySteve setup")
    print("Choose the model that powers routing, judging, and execution.")
    print("(You can re-run this any time, or edit the generated .env by hand.)\n")

    for key, (label, *_rest) in PROVIDERS.items():
        print(f"  {key}) {label}")

    choice = _ask("\nProvider", "1")
    if choice not in PROVIDERS:
        print(f"'{choice}' is not an option; using 1 (Local Ollama).")
        choice = "1"

    label, base, api_key, model = PROVIDERS[choice]
    if base is None:
        base = _ask("Base URL (OpenAI-compatible)")
        while not base:
            base = _ask("Base URL is required")
    model = _ask("Model name", model) if model else _ask("Model name")
    while not model:
        model = _ask("Model name is required")
    if api_key is None:
        api_key = _ask("API key (leave blank if the endpoint needs none)") or "none"

    judge = _ask("Judge model (Enter to reuse the model above; the precision-critical role)", model)

    lines = [
        "# Written by `python -m pickysteve.setup`. Your model choice.",
        f"# Provider: {label}",
        "# Real PS_* environment variables override these.",
        f"PS_LLM_BASE_URL={base}",
        f"PS_LLM_API_KEY={api_key}",
        f"PS_ROUTER_MODEL={model}",
        f"PS_EXEC_MODEL={model}",
        f"PS_JUDGE_MODEL={judge}",
        "",
    ]
    ENV.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n[ok] Saved your choice to {ENV}")
    print(f"     provider : {label}")
    print(f"     model    : {model}   judge: {judge}")
    if choice == "1":
        print("     note     : start Ollama and run `ollama pull qwen3:8b` if you haven't.")
    print('\nTry it:  python -m pickysteve "review my Rust endpoint for security and REST design"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
