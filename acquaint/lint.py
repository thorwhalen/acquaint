"""Checks that keep records honest: preferences carry sources, forbidden categories stay out, files parse, entry files stay small.

Errors fail ``acquaint lint``; warnings ask a person to look. The rules:

- every bullet under ``Reach``, ``Write to them``, ``Read them``, ``Don't``, ``Norms``
  and ``Now`` in an entry file, and every bullet in ``style.md`` and ``views.md``,
  ends with a ``[source: …]`` tag, and a date alone is not a source (**error**);
- a logged ``preference``, ``view`` or ``rule`` has a source (**error**), a logged
  observation without one is a **warning**;
- ``rules.yaml`` rules have ``do`` and a ``source``; identities have a platform and a value (**error**);
- a record that does not parse is an **error**, reported and skipped, never a crash;
- POLICY.md tripwires, instruction-like text, expired ``Now`` lines, a passed
  ``review_due``, links to unknown entities and an oversized entry file are **warnings**.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from acquaint.records import parse_log, source_problem
from acquaint.resources import data_yaml
from acquaint.store import ENTRY_FILE, AcquaintError, Store

__all__ = ["lint_store", "policy_hits", "PREFERENCE_SECTIONS", "SOURCED_FILES"]

PREFERENCE_SECTIONS = {"reach", "write to them", "read them", "don't", "dont", "norms", "now"}
SOURCED_FILES = ("style.md", "views.md")
_NEEDS_SOURCE = {"preference", "view", "rule"}
_UNTIL_RE = re.compile(r"\(until:\s*(\d{4}-\d{2}-\d{2})\)")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(\S.*)$")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def policy_hits(text: str) -> list[tuple[str, str]]:
    """``(category, message)`` for each POLICY.md tripwire the text trips (keyword heuristics, not a verdict)."""
    policy = data_yaml("policy.yaml")
    groups = dict(policy["never_record"], instruction_like=policy["instruction_like"])
    return [
        (category, spec["message"])
        for category, spec in groups.items()
        if any(re.search(pattern, text, re.I) for pattern in spec["patterns"])
    ]


def _lines(text: str) -> list[str]:
    return _COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text).splitlines()


def _finding(severity: str, key: str, file: str, line: int | None, rule: str, message: str) -> dict:
    return {"severity": severity, "entity": key, "file": file, "line": line, "rule": rule, "message": message}


def _lint_entity(store: Store, key: str, today: str) -> list[dict]:
    entity = store[key]
    found: list[dict] = []
    add = lambda sev, file, line, rule, msg: found.append(_finding(sev, key, file, line, rule, msg))  # noqa: E731

    for error in entity.errors:
        file, _, message = error.partition(": ")
        add("error", file, None, "unparseable", message)
    meta = entity.meta
    if meta and meta.get("id") not in (None, entity.slug):
        add("warning", ENTRY_FILE, None, "id-mismatch", f"frontmatter id {meta.get('id')!r} differs from the folder {entity.slug!r}")
    if meta.get("review_due") and str(meta["review_due"]) < today:
        add("warning", ENTRY_FILE, None, "review-due", f"review was due {meta['review_due']}")

    budgets = data_yaml("policy.yaml")["budgets"]
    profile_lines = entity.text(ENTRY_FILE).splitlines()
    if len(profile_lines) > budgets["profile_lines_error"]:
        add("error", ENTRY_FILE, None, "too-long", f"{len(profile_lines)} lines; the entry file is capped at {budgets['profile_lines_error']}")
    elif len(profile_lines) > budgets["profile_lines_warn"]:
        add("warning", ENTRY_FILE, None, "long", f"{len(profile_lines)} lines; keep the entry file under {budgets['profile_lines_warn']} and link the rest from More")

    section = None
    for number, line in enumerate(_lines(entity.text(ENTRY_FILE)), start=1):
        heading = _HEADING_RE.match(line)
        if heading and line.startswith("## "):
            section = heading.group(1).strip().lower()
            continue
        bullet = _BULLET_RE.match(line)
        if not bullet or section not in PREFERENCE_SECTIONS:
            continue
        problem = source_problem(line)
        if problem:
            add("error", ENTRY_FILE, number, "unsourced", f"'{section}' line: {problem}")
        if section == "now":
            until = _UNTIL_RE.search(line)
            if not until:
                add("warning", ENTRY_FILE, number, "now-without-expiry", "Now lines carry (until: YYYY-MM-DD)")
            elif until.group(1) < today:
                add("warning", ENTRY_FILE, number, "now-expired", f"expired {until.group(1)}")

    for file in SOURCED_FILES:
        for number, line in enumerate(_lines(entity.text(file)), start=1):
            if _BULLET_RE.match(line) and (problem := source_problem(line)):
                add("error", file, number, "unsourced", problem)

    for log_name in (name for name in entity if name.startswith("log/")):
        for entry in parse_log(entity[log_name]):
            where = f"{log_name}#{entry['id']}"
            source = entry.get("source", "")
            unsourced = not source or source == "none given" or source_problem(f"[source: {source}]")
            if unsourced and entry["kind"] in _NEEDS_SOURCE:
                add("error", where, None, "unsourced", f"a logged {entry['kind']} needs a source")
            elif unsourced:
                add("warning", where, None, "unsourced-observation", "observation has no source yet")

    for rule in entity.rules:
        label = f"rule {rule.get('id') or rule.get('when')}"
        if "do" not in rule:
            add("error", "rules.yaml", None, "rule-without-do", f"{label} says when but not what to do")
        if not rule.get("source") or source_problem(f"[source: {rule.get('source')}]"):
            add("error", "rules.yaml", None, "unsourced", f"{label} has no source")
    for identity in entity.identities:
        if not identity.get("platform") or not identity.get("value"):
            add("error", "identities.yaml", None, "identity-incomplete", f"identity {identity} needs platform and value")
    for link in entity.links:
        try:
            store.find(str(link.get("to", "")))
        except (KeyError, AcquaintError):
            add("warning", "links.yaml", None, "unknown-link", f"link to {link.get('to')!r} names no entity in the store")

    for file in (name for name in entity if name.endswith((".md", ".yaml")) and not name.startswith("research/")):
        for number, line in enumerate(entity[file].splitlines(), start=1):
            for category, message in policy_hits(line):
                add("warning", file, number, category, message)
    return found


def lint_store(store: Store, key: str | None = None, *, today: str | None = None) -> dict[str, Any]:
    """Lint one entity (by store key) or the whole store: ``{"errors": [...], "warnings": [...], "checked": n}``."""
    today = today or date.today().isoformat()
    keys = [key] if key else list(store)
    findings = [finding for k in keys for finding in _lint_entity(store, k, today)]
    if key is None and keys and "POLICY.md" not in store.files:
        findings.append(_finding("warning", "", "POLICY.md", None, "no-policy", "the store has no POLICY.md; `acquaint new` seeds one"))
    return {
        "errors": [f for f in findings if f["severity"] == "error"],
        "warnings": [f for f in findings if f["severity"] == "warning"],
        "checked": len(keys),
    }
