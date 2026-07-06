"""Connectors that wire PickySteve into external coding agents.

- mcp_server  : MCP stdio JSON-RPC server (Claude Code, Codex, Cursor, Windsurf, Cline,
                Roo Code, Gemini CLI, Goose, OpenHands, Copilot agent, ...). Zero extra deps.
- http_server : REST /pick + an OpenAI-compatible /v1/chat/completions proxy (Aider,
                ZeroClaw, and anything that accepts a custom OpenAI base URL). Zero extra deps.

Both expose the same core: `Engine.pick(request)` → a focused, untrusted-data-boundaried
skill bundle the calling agent injects into its own context.
"""
