---
id: prompt-injection-defense
name: Prompt Injection Defense
description: Detect and mitigate prompt-injection in LLM agent tool results and retrieved content before it reaches the model.
tags: [llm, prompt-injection, agent-security, ai-security, tool-results, untrusted-data, defender]
---
# Prompt Injection Defense

Use when an AI agent consumes untrusted content — emails, documents, web pages,
retrieved skills — and you need to stop indirect prompt injection.

## Capabilities
- Two-tier scanning: fast pattern/regex normalization (role-marker stripping,
  unicode/homoglyph normalization, encoded-payload detection) then an ML
  sentence-level injection classifier.
- Wraps untrusted text in an explicit data boundary so the model treats it as DATA,
  not instructions.
- Distinguishes the realistic threat (malicious instructions embedded in stored
  documents/tool results) from the user's own typed request.
- Policy guidance: block-on-detection vs sanitize-and-continue, and where to scan
  (raw input AND every retrieved item, not just one place).

## Notes
Treats all retrieved content as low-trust. Confidence scores measure plausibility,
never correctness.
