"""MCP over stdio: the same tools, for Claude Desktop and other local MCP clients.

Run ``acquaint-mcp`` (install the extra first: ``pip install "acquaint[mcp]"``). Tools
are registered by ``acquaint.tools:<name>`` string reference, so the core never imports
an MCP library. By default only tools that read, append or create are exposed;
renaming, forgetting and syncing are operator actions and stay at the terminal.

Claude Desktop configuration::

    {"mcpServers": {"acquaint": {"command": "acquaint-mcp"}}}
"""

from __future__ import annotations

from collections.abc import Iterable

from acquaint.tools import SIDE_EFFECTS, TOOLS

__all__ = ["DEFAULT_EFFECTS", "INSTRUCTIONS", "refs", "mk_server", "main"]

DEFAULT_EFFECTS = ("read", "append", "create")
INSTRUCTIONS = (
    "Local profiles of the people (and projects, orgs, groups) the user works with. "
    "Use `who` for one fact about someone, `brief` before writing to someone, `check` on prose "
    "that names people before it is published, `style_lint` on a draft, and `remember` to "
    "record something learned, always with its source. Never record health, religion, "
    "politics, ethnicity, sexuality, credentials, or personality labels."
)


def refs(*, effects: Iterable[str] = DEFAULT_EFFECTS) -> list[str]:
    """``acquaint.tools:<name>`` references for the tools whose side effects are in ``effects``.

    >>> "acquaint.tools:brief" in refs(), "acquaint.tools:forget" in refs()
    (True, False)
    """
    allowed = set(effects)
    return [f"acquaint.tools:{t.__name__}" for t in TOOLS if SIDE_EFFECTS[t.__name__] in allowed]


def mk_server(*, effects: Iterable[str] = DEFAULT_EFFECTS):
    """A FastMCP server over the selected tools (not started)."""
    from py2mcp import mk_mcp_from_refs

    return mk_mcp_from_refs(refs(effects=effects), name="acquaint", instructions=INSTRUCTIONS)


def main() -> None:
    """Serve the default tools over stdio."""
    try:
        from py2mcp import serve_stdio
    except ImportError as error:
        raise SystemExit('acquaint-mcp needs the mcp extra: pip install "acquaint[mcp]"') from error
    serve_stdio(refs(), name="acquaint", instructions=INSTRUCTIONS)


if __name__ == "__main__":
    main()
