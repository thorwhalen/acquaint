"""acquaint: people, and what they are involved in, for AI agents.

Who someone is, how to reach them, how to read them, how to write to them, kept as
hand-editable Markdown with a source on every preference, outside any code repository.

The verbs are the same in Python, on the command line (``acquaint who ada -f aka``) and
over MCP::

    >>> from acquaint import new, remember, who, brief   # doctest: +SKIP
    >>> new("person", "Ada Lovelace")                     # doctest: +SKIP
    >>> remember("ada-lovelace", "prefers email for anything with attachments",
    ...          source="https://example.org/thread/1")   # doctest: +SKIP
    >>> who("ada", field="aka")["value"]                  # doctest: +SKIP
    ['Ada', 'Lovelace']

For library use, :class:`Store` is a ``MutableMapping`` of entities over any mapping of
files (a ``dol`` files store by default).
"""

from acquaint.store import AcquaintError, Entity, Store, data_dir
from acquaint.tools import (
    SIDE_EFFECTS,
    TOOLS,
    brief,
    check,
    disclosure,
    forget,
    lint,
    new,
    reach,
    remember,
    rename,
    resolve,
    style_lint,
    sync_init,
    sync_pull,
    sync_push,
    sync_status,
    who,
)

__all__ = [
    "AcquaintError",
    "Entity",
    "SIDE_EFFECTS",
    "Store",
    "TOOLS",
    "brief",
    "check",
    "data_dir",
    "disclosure",
    "forget",
    "lint",
    "new",
    "reach",
    "remember",
    "rename",
    "resolve",
    "style_lint",
    "sync_init",
    "sync_pull",
    "sync_push",
    "sync_status",
    "who",
]
