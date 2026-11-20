"""divide's own MCP server: the IDE's design-time services for AI coding agents.

It belongs to the IDE: what it exposes is what divide does while a generator
is developed (the project's Div setup, the editor's checks of a template, a
render and the render trace through the real Div engine). It is not a
generator's MCP: a generator that serves one implements it in its own
project.

- :mod:`.tools`: the seven tools, on the IDE's own code (no transport);
- :mod:`.protocol`: MCP's JSON-RPC, both eras (2026-07-28, and 2024-11-05
  to 2025-11-25 with ``initialize``);
- :mod:`.http`: Streamable HTTP on ``/mcp``, started and stopped from the
  IDE (Options > MCP server), the main way in;
- :mod:`.stdio`: ``divide --mcp PROJECT``, for clients that start servers
  as processes.

Standard library only: no MCP SDK, no web framework.
"""
