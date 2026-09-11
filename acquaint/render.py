"""Turning a tool's result into terminal output: ``(stdout, stderr, exit code)``.

Used by the CLI only. The rules, in order: a one-field lookup prints just the value
(one line per item, so it pipes); otherwise the long ``text`` if there is one; otherwise
the ``summary``. A result with ``ok: False`` exits 1 and puts its summary on stderr.

>>> render({"ok": True, "value": ["Ada", "Lovelace"], "summary": "…"})
('Ada\\nLovelace', '', 0)
>>> render({"ok": False, "summary": "no match for 'x'"})
('', "no match for 'x'", 1)
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["render"]


def _scalar(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def render(result: Any) -> tuple[str, str, int]:
    """``(stdout, stderr, exit_code)`` for one tool result."""
    if not isinstance(result, dict):
        return ("" if result is None else str(result), "", 0)
    ok = bool(result.get("ok", True))
    warnings = [f"warning: {w}" for w in result.get("warnings") or [] if isinstance(w, str)]
    if ok and "value" in result:
        value = result["value"]
        out = "\n".join(_scalar(v) for v in value) if isinstance(value, list) else _scalar(value)
    elif ok:
        out = result.get("text") or result.get("summary") or json.dumps(result, indent=2, ensure_ascii=False)
    else:
        summary = result.get("summary", "failed")
        out = (result.get("text") or "").rstrip("\n")
        out = out.removesuffix(summary).rstrip("\n") if out != summary else ""
        candidates = result.get("candidates") or []
        out = out or "\n".join(f"{c['id']}  {c['name']}" for c in candidates)
        warnings = [summary, *warnings]
    return (out.rstrip("\n"), "\n".join(warnings), 0 if ok else 1)
