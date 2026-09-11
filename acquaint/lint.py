"""Checks that keep records honest: preferences carry sources, forbidden categories stay out, files parse, entry files stay small.

Errors fail ``acquaint lint``; warnings ask a person to look. The rules:

- every item under ``Reach``, ``Write to them``, ``Read them``, ``Don't``, ``Norms`` and
  ``Now`` in an entry file, and every item in ``style.md`` and ``views.md``, carries a
  ``[source: …]`` tag. An item is one bullet at any depth (a nested bullet needs its own
  source) with its wrapped lines, or a paragraph. A date alone, or a placeholder such as
  ``unknown``, is not a source (**error**). Headings match however they are decorated
  (``Don’t:``, ``## Reach ##``, an indented ``## Now``);
- a logged ``preference``, ``view`` or ``rule`` has a source (**error**); a logged
  observation without one is a **warning**, and so is a repeated entry id;
- ``rules.yaml`` rules have ``do``, channel names that are text, and a ``source``;
  identities have a platform and a value; a writing card's ``ai_tolerance`` is tolerant,
  neutral or averse (**error**);
- a file that does not parse, or is not valid UTF-8, an entry file the store cannot
  address (a capitalised or linked folder, ``profile.md``), and a broken
  ``_tombstones.yaml`` are **errors**, reported and skipped, never a crash;
- POLICY.md tripwires, instruction-like text, expired ``Now`` items, a passed
  ``review_due``, non-text aliases, links to unknown entities, an oversized entry file,
  and a data root that is or sits inside a code repository are **warnings**.

Links are checked against an index of the store built once, so linting grows with the
number of records, not with its square.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Any

from acquaint.records import blank_frontmatter, load_yaml, parse_log, sectioned_items, source_problem, split_frontmatter
from acquaint.resources import data_yaml
from acquaint.store import ENTRY_FILE, UNREADABLE, AcquaintError, Entity, Store, kind_dir

__all__ = ["AI_TOLERANCES", "PREFERENCE_SECTIONS", "SOURCED_FILES", "lint_store", "policy_hits"]

PREFERENCE_SECTIONS = {"reach", "write to them", "read them", "don't", "dont", "norms", "now"}
SOURCED_FILES = ("style.md", "views.md")
AI_TOLERANCES = ("tolerant", "neutral", "averse")
_NEEDS_SOURCE = {"preference", "view", "rule"}
_UNTIL_RE = re.compile(r"\(until:\s*(\d{4}-\d{2}-\d{2})\)")
_TOMBSTONES = "_tombstones.yaml"


def policy_hits(text: str) -> list[tuple[str, str]]:
    """``(category, message)`` for each POLICY.md tripwire the text trips (keyword heuristics, not a verdict)."""
    policy = data_yaml("policy.yaml")
    groups = dict(policy["never_record"], instruction_like=policy["instruction_like"])
    return [
        (category, spec["message"])
        for category, spec in groups.items()
        if any(re.search(pattern, text, re.I) for pattern in spec["patterns"])
    ]


def _finding(severity: str, key: str, file: str, line: int | None, rule: str, message: str) -> dict:
    return {"severity": severity, "entity": key, "file": file, "line": line, "rule": rule, "message": message}


def _link_exists(ref: Any, keys: set[str], ids: set[str]) -> bool:
    ref = str(ref).strip().lower()
    if "/" in ref:
        return ref in keys
    if ":" in ref:
        kind, _, slug = ref.partition(":")
        try:
            return f"{kind_dir(kind)}/{slug}" in keys
        except AcquaintError:
            return False
    return ref in ids


def _lint_entity(store: Store, key: str, today: str, keys: set[str], ids: set[str]) -> list[dict]:
    entity = Entity(store, key)
    found: list[dict] = []

    def add(severity: str, file: str, line: int | None, rule: str, message: str) -> None:
        found.append(_finding(severity, key, file, line, rule, message))

    for error in entity.errors:
        file, _, message = error.partition(": ")
        add("error", file, None, "unparseable", message)
    text_files = [name for name in entity if name.endswith((".md", ".yaml", ".yml"))]
    for name in text_files:
        if name != ENTRY_FILE and UNREADABLE in entity[name]:
            add("error", name, None, "unparseable", f"not valid UTF-8 (undecodable bytes shown as {UNREADABLE})")

    meta = entity.meta
    if meta and meta.get("id") not in (None, entity.slug):
        add("warning", ENTRY_FILE, None, "id-mismatch", f"frontmatter id {meta.get('id')!r} differs from the folder {entity.slug!r}")
    if meta.get("review_due") and str(meta["review_due"]) < today:
        add("warning", ENTRY_FILE, None, "review-due", f"review was due {meta['review_due']}")
    raw_aka = meta.get("aka")
    if any(not isinstance(a, str) for a in (raw_aka if isinstance(raw_aka, list) else [])):
        add("warning", ENTRY_FILE, None, "aka-not-text", "aliases should be text; quote numbers and dates")

    budgets = data_yaml("policy.yaml")["budgets"]
    profile = entity.text(ENTRY_FILE)
    lines = profile.count("\n") + (0 if profile.endswith("\n") or not profile else 1)
    if lines > budgets["profile_lines_error"]:
        add("error", ENTRY_FILE, None, "too-long", f"{lines} lines; the entry file is capped at {budgets['profile_lines_error']}")
    elif lines > budgets["profile_lines_warn"]:
        add("warning", ENTRY_FILE, None, "long", f"{lines} lines; keep the entry file under {budgets['profile_lines_warn']} and link the rest from More")

    for section, number, item in sectioned_items(blank_frontmatter(profile)):
        title = (section or "").lower()
        if title not in PREFERENCE_SECTIONS:
            continue
        if problem := source_problem(item):
            add("error", ENTRY_FILE, number, "unsourced", f"'{section}' item: {problem}")
        if title == "now":
            until = _UNTIL_RE.search(item)
            if not until:
                add("warning", ENTRY_FILE, number, "now-without-expiry", "Now items carry (until: YYYY-MM-DD)")
            elif until.group(1) < today:
                add("warning", ENTRY_FILE, number, "now-expired", f"expired {until.group(1)}")

    for file in SOURCED_FILES:
        for _, number, item in sectioned_items(blank_frontmatter(entity.text(file))):
            if problem := source_problem(item):
                add("error", file, number, "unsourced", problem)
    if "style.md" in entity:
        tolerance = split_frontmatter(entity["style.md"])[0].get("ai_tolerance")
        if tolerance not in (None, "", "unknown") and str(tolerance).strip().lower() not in AI_TOLERANCES:
            add("error", "style.md", None, "bad-ai-tolerance", f"ai_tolerance is {tolerance!r}; use tolerant, neutral or averse")

    for log_name in (name for name in entity if name.startswith("log/")):
        entries = parse_log(entity[log_name])
        for entry_id, count in Counter(e["id"] for e in entries).items():
            if count > 1:
                add("warning", log_name, None, "duplicate-entry-id", f"{entry_id} appears {count} times")
        for entry in entries:
            where = f"{log_name}#{entry['id']}"
            source = entry.get("source", "")
            unsourced = not source or source == "none given" or source_problem(f"[source: {source}]")
            if unsourced and entry["kind"] in _NEEDS_SOURCE:
                add("error", where, None, "unsourced", f"a logged {entry['kind']} needs a source")
            elif unsourced:
                add("warning", where, None, "unsourced-observation", "observation has no source yet")

    for rule in entity.rules:
        label = f"rule {rule.get('id') or rule.get('when')}"
        do = rule.get("do")
        if do is None:
            add("error", "rules.yaml", None, "rule-without-do", f"{label} says when but not what to do")
        elif isinstance(do, dict):
            fallback = do.get("fallback")
            for value in [do.get("channel"), *(fallback if isinstance(fallback, list) else [fallback])]:
                if value is not None and not (isinstance(value, str) and value.strip()):
                    add("error", "rules.yaml", None, "bad-channel", f"{label}: {value!r} is not a channel name")
        if not rule.get("source") or source_problem(f"[source: {rule.get('source')}]"):
            add("error", "rules.yaml", None, "unsourced", f"{label} has no source")
    for identity in entity.identities:
        if not identity.get("platform") or not identity.get("value"):
            add("error", "identities.yaml", None, "identity-incomplete", f"identity {identity} needs platform and value")
    for link in entity.links:
        if not _link_exists(link.get("to", ""), keys, ids):
            add("warning", "links.yaml", None, "unknown-link", f"link to {link.get('to')!r} names no entity in the store")

    for file in (name for name in text_files if not name.startswith("research/")):
        for number, line in enumerate(entity[file].splitlines(), start=1):
            for category, message in policy_hits(line):
                add("warning", file, number, category, message)
    return found


def _tombstone_problem(store: Store) -> str | None:
    if _TOMBSTONES not in store.files:
        return None
    text = store.files[_TOMBSTONES]
    data, errors = load_yaml(text)
    if errors or UNREADABLE in text:
        return f"does not parse ({(errors or ['not valid UTF-8'])[0]}); until fixed, forgotten people can be re-created"
    if data is not None and (not isinstance(data, dict) or (data.get("tombstones") and not data.get("salt"))):
        return "has tombstones but no salt (or is not a mapping); none of them can be matched"
    return None


def lint_store(store: Store, key: str | None = None, *, today: str | None = None) -> dict[str, Any]:
    """Lint one entity (by store key) or the whole store: ``{"errors": [...], "warnings": [...], "checked": n}``."""
    today = today or date.today().isoformat()
    all_keys = list(store)
    keys, ids = set(all_keys), {k.split("/", 1)[1] for k in all_keys}
    targets = [key] if key else all_keys
    findings: list[dict] = []
    for k in targets:
        try:
            findings += _lint_entity(store, k, today, keys, ids)
        except Exception as error:  # one unreadable record is reported, never the end of the run
            findings.append(_finding("error", k, "", None, "unreadable", f"could not be checked: {type(error).__name__}: {error}"))
    if key is None:
        for path in store.misnamed():
            findings.append(_finding("error", "", path, None, "misnamed", "the store cannot address this entry file: use a lowercase kind/id folder and PROFILE.md, not a link"))
        if problem := _tombstone_problem(store):
            findings.append(_finding("error", "", _TOMBSTONES, None, "unparseable", problem))
        if targets and "POLICY.md" not in store.files:
            findings.append(_finding("warning", "", "POLICY.md", None, "no-policy", "the store has no POLICY.md; `acquaint new` seeds one"))
        if warning := store.location_warning():
            findings.append(_finding("warning", "", "", None, "data-root-in-repository", warning))
    return {
        "errors": [f for f in findings if f["severity"] == "error"],
        "warnings": [f for f in findings if f["severity"] == "warning"],
        "checked": len(targets),
    }
