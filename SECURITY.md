# Security Policy

PickySteve's job includes refusing prompt-injection and treating retrieved content as
untrusted, so responsible disclosure matters here. Thank you for helping keep it safe.

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Report privately through GitHub's private vulnerability reporting:

1. Go to the [Security tab](https://github.com/KernelLord/pickysteve/security).
2. Click **Report a vulnerability**.
3. Include the affected file/component, the impact, reproduction steps, and a PoC if you have one.

This keeps the details private until a fix is available.

## What to expect

- An acknowledgment as soon as the report is reviewed.
- An assessment of severity and scope, and a fix or a documented decision if it is out of scope.
- Credit in the release notes if you would like it.

## Scope

This repo is Phase 1 (MVP). The primary security-relevant surface is the injection gate
(`pickysteve/security_gate.py`) and the assembly boundary (`pickysteve/assembly.py`). The
current threat model, what is covered, and the known residual limitations are documented in
[`SECURITY_AUDIT.md`](SECURITY_AUDIT.md) and the "Known limitations" section of the README.

Notes that are expected and not vulnerabilities:
- Fake credential strings in `eval/test_gate_security.py` are test fixtures used to verify the
  output filter detects key formats. They are not real secrets.
- Confidence/relevance scores measure topical similarity, not correctness. A "wrong but
  plausible" skill pick is a known limitation, not a security issue.
