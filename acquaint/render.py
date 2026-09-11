"""Turning a tool's result into terminal output: ``(stdout, stderr, exit code)``.

Used by the CLI only. The rules, in order: a one-field lookup prints just the value
(one line per item, so it pipes); otherwise the long ``text`` if there is one; otherwise
the ``summary``. A result with ``ok: False`` exits 1 and puts its summary on stderr.
A result whose ``outcome`` is in :data:`EXIT_CODES` exits with that code instead, so a
script can tell it apart from both success and failure (2 stays the usage error). An
outcome name means the same thing in every tool that uses it.

>>> render({"ok": True, "value": ["Ada", "Lovelace"], "summary": "…"})
('Ada\\nLovelace', '', 0)
>>> render({"ok": False, "summary": "no match for 'x'"})
('', "no match for 'x'", 1)
>>> render({"ok": False, "outcome": "no_address", "text": "1. pager  [self]", "summary": "no pager address"})
('1. pager  [self]', 'no pager address', 3)
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["EXIT_CODES", "exit_code", "render"]

EXIT_CODES = {
    "no_address": 3,  # reach: a rule matched, but no usable address is recorded for its channels
}


def _scalar(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def exit_code(result: Any) -> int:
    """The exit code for one tool result: its ``outcome``'s code if it has one, else 0 if ``ok``, else 1."""
    if not isinstance(result, dict):
        return 0
    return EXIT_CODES.get(result.get("outcome"), 0 if result.get("ok", True) else 1)


def render(result: Any) -> tuple[str, str, int]:
    """``(stdout, stderr, exit_code)`` for one tool result."""
    if not isinstance(result, dict):
        return ("" if result is None else str(result), "", 0)
    ok = bool(result.get("ok", True))
    warnings = [
        f"warning: {w}" for w in result.get("warnings") or [] if isinstance(w, str)
    ]
    if ok and "value" in result:
        value = result["value"]
        out = (
            "\n".join(_scalar(v) for v in value)
            if isinstance(value, list)
            else _scalar(value)
        )
    elif ok:
        out = (
            result.get("text")
            or result.get("summary")
            or json.dumps(result, indent=2, ensure_ascii=False)
        )
    else:
        summary = result.get("summary", "failed")
        out = (result.get("text") or "").rstrip("\n")
        out = out.removesuffix(summary).rstrip("\n") if out != summary else ""
        candidates = result.get("candidates") or []
        out = out or "\n".join(f"{c['id']}  {c['name']}" for c in candidates)
        warnings = [summary, *warnings]
    return (out.rstrip("\n"), "\n".join(warnings), exit_code(result))
