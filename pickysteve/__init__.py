"""PickySteve — a picky-context orchestration layer.

Uses a cheap model to decide which skills a request actually needs, retrieves
just those, and hands a small, focused, untrusted-data-boundaried context bundle
to a capable model — instead of dumping every tool/document into context.

Phase 1 (MVP) only. See README.md and the architecture spec.
"""

__version__ = "0.1.0"
