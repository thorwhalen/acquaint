"""MCP over stdio: the same tools, for Claude Desktop and other local MCP clients.

Run ``acquaint-mcp`` (install the extra first: ``pip install "acquaint[mcp]"``). The
exposed tools are named by ``acquaint.tools:<name>`` reference, so the core never imports
an MCP library. By default only tools that read locally, append or create are exposed;
renaming, forgetting and syncing are operator actions and stay at the terminal.

The data root is the server's, never the model's: ``data_dir`` is removed from every
tool's schema, so a model cannot write profiles into whatever directory it is working
in. ``remember``'s ``reactivate`` is removed too: making an inactive identity active
again changes a recorded status, which is the operator's call. Point the server
elsewhere with ``ACQUAINT_DATA_DIR`` in the client configuration::

    {"mcpServers": {"acquaint": {"command": "acquaint-mcp"}}}
"""

from __future__ import annotations

import functools
import importlib
import inspect
from collections.abc import Callable, Iterable

from acquaint.tools import SIDE_EFFECTS, TOOLS

__all__ = [
    "DEFAULT_EFFECTS",
    "HIDDEN_PARAMETERS",
    "INSTRUCTIONS",
    "main",
    "mk_server",
    "refs",
]

DEFAULT_EFFECTS = ("read", "append", "create")
HIDDEN_PARAMETERS = ("data_dir", "reactivate")
INSTRUCTIONS = (
    "Local profiles of the people (and projects, orgs, groups) the user works with. "
    "Use `who` for one fact about someone, `brief` before writing to someone, `check` on prose "
    "that names people before it is published, `style_lint` on a draft, and `remember` to "
    "record something learned, always with its source. Tools never guess: pass exact names or "
    "ids. Never record health, religion, politics, ethnicity, sexuality, credentials, or "
    "personality labels."
)


def refs(*, effects: Iterable[str] = DEFAULT_EFFECTS) -> list[str]:
    """``acquaint.tools:<name>`` references for the tools whose side effects are in ``effects``.

    >>> "acquaint.tools:brief" in refs(), "acquaint.tools:forget" in refs(), "acquaint.tools:sync_status" in refs()
    (True, False, False)
    """
    allowed = set(effects)
    return [
        f"acquaint.tools:{t.__name__}"
        for t in TOOLS
        if SIDE_EFFECTS[t.__name__] in allowed
    ]


def _resolve(ref: str) -> Callable:
    module, _, name = ref.partition(":")
    return getattr(importlib.import_module(module), name)


def _without(func: Callable, hidden: Iterable[str] = HIDDEN_PARAMETERS) -> Callable:
    """The same tool with ``hidden`` parameters removed from its signature (and so from its MCP schema)."""
    hidden = set(hidden)
    signature = inspect.signature(func)

    @functools.wraps(func)
    def tool(*args, **kwargs):
        return func(*args, **kwargs)

    tool.__signature__ = signature.replace(
        parameters=[p for p in signature.parameters.values() if p.name not in hidden]
    )
    return tool


def mk_server(*, effects: Iterable[str] = DEFAULT_EFFECTS):
    """A FastMCP server over the selected tools, with :data:`HIDDEN_PARAMETERS` hidden (not started)."""
    from py2mcp import mk_mcp_server

    return mk_mcp_server(
        [_without(_resolve(ref)) for ref in refs(effects=effects)],
        name="acquaint",
        instructions=INSTRUCTIONS,
    )


def main() -> None:
    """Serve the default tools over stdio."""
    try:
        server = mk_server()
    except ImportError as error:
        raise SystemExit(
            'acquaint-mcp needs the mcp extra: pip install "acquaint[mcp]"'
        ) from error
    server.run()


if __name__ == "__main__":
    main()
