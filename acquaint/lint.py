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
- ``rules.yaml`` rules have ``do``, channel names that are text (in ``do.channel`` and
  in each ``fallback`` entry), an ``address`` that is text and sits beside a channel when
  one is stated, and a ``source``; a ``do`` that is one bare word is a **warning**, since
  it is read as a free-text instruction and no address is resolved for it;
  identities have a platform and a value; a writing card's ``ai_tolerance`` is tolerant,
  neutral or averse (**error**);
- the disclosure schema (:mod:`acquaint.trust`): a tier whose source is neither
  ``operator`` nor ``self``; a ``label``, ``sealed_from``, ``clearance`` or ``default_tier``
  without ``label_source: operator``; an unknown tier, label or clearance; an ``open`` or
  ``involved`` tier without ``review_by``; a tier date not written ``YYYY-MM-DD``; a seal
  naming no record; a malformed ``[label: …]`` or ``[sealed-from: …]`` tag; an
  ``interaction`` log entry whose ``disclosed:`` names no record (**error**). A
  permissive tier past its ``review_by``, a project whose ``Where things live`` names a
  public repository while its label is not ``clear``, a seal on someone with a current
  link to the sealed record, a field on a kind that does not read it, and non-text
  vocabulary are **warnings**;
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

from acquaint.records import (
    blank_frontmatter,
    disclosed_refs,
    fact_tags,
    item_blocks,
    load_yaml,
    parse_log,
    sectioned_items,
    source_kind,
    source_problem,
    split_frontmatter,
)
from acquaint.resources import data_yaml
from acquaint.store import ENTRY_FILE, UNREADABLE, AcquaintError, Entity, Store, kind_dir
from acquaint.trust import (
    CLEARANCE_KINDS,
    DEFAULT_TIER,
    DEFAULT_TIER_KINDS,
    LABELS,
    OPERATOR_SET_FIELDS,
    PERMISSIVE_TIERS,
    TIERS,
    TRUST_FILE,
    TRUST_SOURCES,
    entity_label,
    is_lapsed,
    tier_in_force,
)

__all__ = [
    "AI_TOLERANCES",
    "PREFERENCE_SECTIONS",
    "SOURCED_FILES",
    "lint_store",
    "policy_hits",
]

PREFERENCE_SECTIONS = {
    "reach",
    "write to them",
    "read them",
    "don't",
    "dont",
    "norms",
    "now",
}
SOURCED_FILES = ("style.md", "views.md")
AI_TOLERANCES = ("tolerant", "neutral", "averse")
_NEEDS_SOURCE = {"preference", "view", "rule"}
_UNTIL_RE = re.compile(r"\(until:\s*(\d{4}-\d{2}-\d{2})\)")
_TOMBSTONES = "_tombstones.yaml"
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIER_DATES = ("valid_from", "valid_to", "review_by", "recorded")
_WHERE_THINGS_LIVE = "where things live"
_PUBLIC_RE = re.compile(r"\bpublic\b", re.I)
_REPOSITORY_RE = re.compile(
    r"\b(?:github\.com|gitlab\.com|codeberg\.org|bitbucket\.org|repos?|repositor(?:y|ies))\b",
    re.I,
)


def policy_hits(text: str) -> list[tuple[str, str]]:
    """``(category, message)`` for each POLICY.md tripwire the text trips (keyword heuristics, not a verdict)."""
    policy = data_yaml("policy.yaml")
    groups = dict(policy["never_record"], instruction_like=policy["instruction_like"])
    return [
        (category, spec["message"])
        for category, spec in groups.items()
        if any(re.search(pattern, text, re.I) for pattern in spec["patterns"])
    ]


def _finding(
    severity: str, key: str, file: str, line: int | None, rule: str, message: str
) -> dict:
    return {
        "severity": severity,
        "entity": key,
        "file": file,
        "line": line,
        "rule": rule,
        "message": message,
    }


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


def _keys_named(ref: str, keys: set[str]) -> list[str]:
    ref = ref.strip().lower()
    if "/" in ref:
        return [ref] if ref in keys else []
    if ":" in ref:
        kind, _, slug = ref.partition(":")
        try:
            key = f"{kind_dir(kind)}/{slug}"
        except AcquaintError:
            return []
        return [key] if key in keys else []
    return sorted(k for k in keys if k.split("/", 1)[1] == ref)


def _links_to(person: Entity, target: Entity, today: str) -> bool:
    """Whether ``person`` holds a current link (``until`` unset or in the future) to ``target``."""
    names = {target.ref, target.key, target.slug}
    return any(
        str(link.get("to", "")).strip().lower() in names
        and (link.get("until") in (None, "") or str(link.get("until")) > today)
        for link in person.links
    )


def _is_iso_date(value: Any) -> bool:
    if not _ISO_DATE_RE.fullmatch(str(value)):
        return False
    try:
        date.fromisoformat(str(value))
    except ValueError:
        return False
    return True


def _listed(value: Any) -> list:
    if value in (None, ""):
        return []
    return list(value) if isinstance(value, list) else [value]


def _lint_disclosure(
    store: Store, entity: Entity, today: str, keys: set[str], ids: set[str], add
) -> None:
    """The disclosure schema: who set each tier, label and seal; whether its values exist; what has lapsed."""
    meta, kind = entity.meta, entity.kind

    operator_set = [f for f in OPERATOR_SET_FIELDS if meta.get(f) not in (None, "", [])]
    if operator_set and source_kind(str(meta.get("label_source") or "")) != "operator":
        add(
            "error",
            ENTRY_FILE,
            None,
            "label-unsourced",
            f"{', '.join(operator_set)} set without label_source: operator; only the operator labels, seals and grants trust",
        )
    for field, allowed, rule in (
        ("label", LABELS, "unknown-label"),
        ("clearance", LABELS, "unknown-clearance"),
        ("default_tier", TIERS, "unknown-tier"),
    ):
        value = meta.get(field)
        if value not in (None, "") and value not in allowed:
            add(
                "error",
                ENTRY_FILE,
                None,
                rule,
                f"{field} is {value!r}; use one of {', '.join(allowed)}",
            )
    for field, kinds in (
        ("clearance", CLEARANCE_KINDS),
        ("default_tier", DEFAULT_TIER_KINDS),
    ):
        if meta.get(field) not in (None, "") and kind not in kinds:
            add(
                "warning",
                ENTRY_FILE,
                None,
                "misplaced-field",
                f"{field} is read on {' and '.join(kinds)} records only; on a {kind} it has no effect",
            )
    for ref in _listed(meta.get("sealed_from")):
        if not isinstance(ref, str) or not _link_exists(ref, keys, ids):
            add(
                "error",
                ENTRY_FILE,
                None,
                "unknown-sealed-from",
                f"sealed_from names {ref!r}, which is no record in the store",
            )
            continue
        for key in _keys_named(ref, keys):
            if key != entity.key and _links_to(Entity(store, key), entity, today):
                add(
                    "warning",
                    ENTRY_FILE,
                    None,
                    "sealed-but-linked",
                    f"sealed from {ref}, who holds a current link to {entity.ref} in links.yaml",
                )
    if any(
        not isinstance(term, str) or not term.strip()
        for term in _listed(meta.get("vocabulary"))
    ):
        add(
            "warning",
            ENTRY_FILE,
            None,
            "vocabulary-not-text",
            "vocabulary terms should be text; quote numbers and dates",
        )

    label = entity_label(meta, kind)
    if kind == "project" and label != "clear":
        profile = blank_frontmatter(entity.text(ENTRY_FILE))
        lines = profile.split("\n")
        public = next(
            (
                number
                for section, first, last, _ in item_blocks(profile)
                if (section or "").lower() == _WHERE_THINGS_LIVE
                for number in range(first, last + 1)
                if _PUBLIC_RE.search(lines[number - 1])
                and _REPOSITORY_RE.search(lines[number - 1])
            ),
            None,
        )
        if public:
            add(
                "warning",
                ENTRY_FILE,
                public,
                "public-repository-not-clear",
                f"'Where things live' names a public repository while the label is {label}: what is written there is world-readable",
            )

    if TRUST_FILE in entity and kind != "person":
        add(
            "warning",
            TRUST_FILE,
            None,
            "misplaced-field",
            f"trust.yaml is read on people only; on a {kind} it has no effect",
        )
    tiers = entity.trust
    for number, entry in enumerate(tiers, start=1):
        tier, where = entry.get("tier"), f"tier entry {number}"
        if tier not in TIERS:
            add(
                "error",
                TRUST_FILE,
                None,
                "unknown-tier",
                f"{where}: tier is {tier!r}; use one of {', '.join(TIERS)}",
            )
        if source_kind(str(entry.get("source") or "")) not in TRUST_SOURCES:
            add(
                "error",
                TRUST_FILE,
                None,
                "tier-unsourced",
                f"{where}: source is {entry.get('source')!r}; a tier comes from the operator (operator) "
                'or from the person\'s own quoted words (self: "…"), nothing else',
            )
        if tier in PERMISSIVE_TIERS and entry.get("review_by") in (None, ""):
            add(
                "error",
                TRUST_FILE,
                None,
                "tier-without-review",
                f"{where}: an {tier} tier needs review_by",
            )
        for field in _TIER_DATES:
            if entry.get(field) not in (None, "") and not _is_iso_date(entry[field]):
                add(
                    "error",
                    TRUST_FILE,
                    None,
                    "bad-date",
                    f"{where}: {field} is {entry[field]!r}; write YYYY-MM-DD",
                )
    in_force = tier_in_force(tiers, today=today)
    if (
        in_force
        and is_lapsed(in_force, today=today)
        and _is_iso_date(in_force.get("review_by"))
    ):
        add(
            "warning",
            TRUST_FILE,
            None,
            "tier-lapsed",
            f"the {in_force['tier']} tier was due for review on {in_force['review_by']}; "
            f"until the operator reviews it, it counts as {DEFAULT_TIER}",
        )

    def check_fact(file: str, line: int | None, text: str) -> None:
        found = fact_tags(text)
        for problem in found["problems"]:
            add("error", file, line, "bad-fact-tag", problem)
        if found["label"] is not None and found["label"] not in LABELS:
            add(
                "error",
                file,
                line,
                "unknown-label",
                f"[label: {found['label']}] is not a label; use one of {', '.join(LABELS)}",
            )
        for ref in found["sealed_from"]:
            if not _link_exists(ref, keys, ids):
                add(
                    "error",
                    file,
                    line,
                    "unknown-sealed-from",
                    f"[sealed-from: {ref}] names no record in the store",
                )

    for file in (ENTRY_FILE, *SOURCED_FILES):
        for _, number, item in sectioned_items(blank_frontmatter(entity.text(file))):
            check_fact(file, number, item)
    for log_name in (name for name in entity if name.startswith("log/")):
        for entry in parse_log(entity[log_name]):
            where = f"{log_name}#{entry['id']}"
            check_fact(where, None, entry["text"])
            for ref in disclosed_refs(entry.get("disclosed", "")):
                if not _link_exists(ref, keys, ids):
                    add(
                        "error",
                        where,
                        None,
                        "unknown-disclosed",
                        f"disclosed: {ref} names no record in the store",
                    )
            if entry.get("disclosed") and entry["kind"] != "interaction":
                add(
                    "warning",
                    where,
                    None,
                    "misplaced-field",
                    f"disclosed: is read on interaction entries only; this is a {entry['kind']}",
                )


def _lint_entity(
    store: Store, key: str, today: str, keys: set[str], ids: set[str]
) -> list[dict]:
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
            add(
                "error",
                name,
                None,
                "unparseable",
                f"not valid UTF-8 (undecodable bytes shown as {UNREADABLE})",
            )

    meta = entity.meta
    if meta and meta.get("id") not in (None, entity.slug):
        add(
            "warning",
            ENTRY_FILE,
            None,
            "id-mismatch",
            f"frontmatter id {meta.get('id')!r} differs from the folder {entity.slug!r}",
        )
    if meta.get("review_due") and str(meta["review_due"]) < today:
        add(
            "warning",
            ENTRY_FILE,
            None,
            "review-due",
            f"review was due {meta['review_due']}",
        )
    raw_aka = meta.get("aka")
    if any(
        not isinstance(a, str) for a in (raw_aka if isinstance(raw_aka, list) else [])
    ):
        add(
            "warning",
            ENTRY_FILE,
            None,
            "aka-not-text",
            "aliases should be text; quote numbers and dates",
        )

    budgets = data_yaml("policy.yaml")["budgets"]
    profile = entity.text(ENTRY_FILE)
    lines = profile.count("\n") + (0 if profile.endswith("\n") or not profile else 1)
    if lines > budgets["profile_lines_error"]:
        add(
            "error",
            ENTRY_FILE,
            None,
            "too-long",
            f"{lines} lines; the entry file is capped at {budgets['profile_lines_error']}",
        )
    elif lines > budgets["profile_lines_warn"]:
        add(
            "warning",
            ENTRY_FILE,
            None,
            "long",
            f"{lines} lines; keep the entry file under {budgets['profile_lines_warn']} and link the rest from More",
        )

    for section, number, item in sectioned_items(blank_frontmatter(profile)):
        title = (section or "").lower()
        if title not in PREFERENCE_SECTIONS:
            continue
        if problem := source_problem(item):
            add("error", ENTRY_FILE, number, "unsourced", f"'{section}' item: {problem}")
        if title == "now":
            until = _UNTIL_RE.search(item)
            if not until:
                add(
                    "warning",
                    ENTRY_FILE,
                    number,
                    "now-without-expiry",
                    "Now items carry (until: YYYY-MM-DD)",
                )
            elif until.group(1) < today:
                add(
                    "warning",
                    ENTRY_FILE,
                    number,
                    "now-expired",
                    f"expired {until.group(1)}",
                )

    for file in SOURCED_FILES:
        for _, number, item in sectioned_items(blank_frontmatter(entity.text(file))):
            if problem := source_problem(item):
                add("error", file, number, "unsourced", problem)
    if "style.md" in entity:
        tolerance = split_frontmatter(entity["style.md"])[0].get("ai_tolerance")
        if (
            tolerance not in (None, "", "unknown")
            and str(tolerance).strip().lower() not in AI_TOLERANCES
        ):
            add(
                "error",
                "style.md",
                None,
                "bad-ai-tolerance",
                f"ai_tolerance is {tolerance!r}; use tolerant, neutral or averse",
            )

    for log_name in (name for name in entity if name.startswith("log/")):
        entries = parse_log(entity[log_name])
        for entry_id, count in Counter(e["id"] for e in entries).items():
            if count > 1:
                add(
                    "warning",
                    log_name,
                    None,
                    "duplicate-entry-id",
                    f"{entry_id} appears {count} times",
                )
        for entry in entries:
            where = f"{log_name}#{entry['id']}"
            source = entry.get("source", "")
            unsourced = (
                not source
                or source == "none given"
                or source_problem(f"[source: {source}]")
            )
            if unsourced and entry["kind"] in _NEEDS_SOURCE:
                add(
                    "error",
                    where,
                    None,
                    "unsourced",
                    f"a logged {entry['kind']} needs a source",
                )
            elif unsourced:
                add(
                    "warning",
                    where,
                    None,
                    "unsourced-observation",
                    "observation has no source yet",
                )

    for rule in entity.rules:
        label = f"rule {rule.get('id') or rule.get('when')}"
        do = rule.get("do")
        if do is None:
            add(
                "error",
                "rules.yaml",
                None,
                "rule-without-do",
                f"{label} says when but not what to do",
            )
        elif isinstance(do, str) and do.strip() and not do.split()[1:]:
            # `do: pager` is read as a free-text instruction, so no address is resolved
            # for it. The writer almost always meant a channel.
            word = do.strip()
            add(
                "warning",
                "rules.yaml",
                None,
                "do-is-a-bare-channel",
                f"{label}: do is the single word {word!r}; write "
                f"`do: {{channel: {word}}}` if that is a channel, since a bare string is "
                f"read as a free-text instruction and no address is resolved for it",
            )
        elif isinstance(do, dict):
            channel = do.get("channel")
            if channel is not None and not _is_text(channel):
                # A channel is a name. An address goes in `address`, beside it.
                add(
                    "error",
                    "rules.yaml",
                    None,
                    "bad-channel",
                    f"{label}: {channel!r} is not a channel name",
                )
            if do.get("address") is not None:
                if not _is_text(do.get("address")):
                    add(
                        "error",
                        "rules.yaml",
                        None,
                        "bad-address",
                        f"{label}: {do.get('address')!r} is not an address",
                    )
                elif channel is None:
                    # A malformed channel is already reported above; saying "add
                    # `channel:`" over it would send the writer after the wrong key.
                    add(
                        "error",
                        "rules.yaml",
                        None,
                        "address-without-channel",
                        f"{label}: do states an address but names no channel, so nothing "
                        f"reaches it; add `channel:`",
                    )
            fallback = do.get("fallback")
            for value in fallback if isinstance(fallback, list) else [fallback]:
                if value is None:
                    continue
                if isinstance(value, dict):
                    if not _is_text(value.get("channel")):
                        add(
                            "error",
                            "rules.yaml",
                            None,
                            "bad-channel",
                            f"{label}: {value!r} needs a channel name",
                        )
                    if value.get("address") is not None and not _is_text(
                        value.get("address")
                    ):
                        add(
                            "error",
                            "rules.yaml",
                            None,
                            "bad-address",
                            f"{label}: {value.get('address')!r} is not an address",
                        )
                elif not _is_text(value):
                    add(
                        "error",
                        "rules.yaml",
                        None,
                        "bad-channel",
                        f"{label}: {value!r} is not a channel name",
                    )
        if not rule.get("source") or source_problem(f"[source: {rule.get('source')}]"):
            add("error", "rules.yaml", None, "unsourced", f"{label} has no source")
    for identity in entity.identities:
        if not identity.get("platform") or not identity.get("value"):
            add(
                "error",
                "identities.yaml",
                None,
                "identity-incomplete",
                f"identity {identity} needs platform and value",
            )
    for link in entity.links:
        if not _link_exists(link.get("to", ""), keys, ids):
            add(
                "warning",
                "links.yaml",
                None,
                "unknown-link",
                f"link to {link.get('to')!r} names no entity in the store",
            )

    _lint_disclosure(store, entity, today, keys, ids, add)

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
    if data is not None and (
        not isinstance(data, dict) or (data.get("tombstones") and not data.get("salt"))
    ):
        return "has tombstones but no salt (or is not a mapping); none of them can be matched"
    return None


def _is_text(value) -> bool:
    """Whether ``value`` is a non-empty string: what a channel name and an address must be."""
    return isinstance(value, str) and bool(value.strip())


def lint_store(
    store: Store, key: str | None = None, *, today: str | None = None
) -> dict[str, Any]:
    """Lint one entity (by store key) or the whole store: ``{"errors": [...], "warnings": [...], "checked": n}``."""
    today = today or date.today().isoformat()
    all_keys = list(store)
    keys, ids = set(all_keys), {k.split("/", 1)[1] for k in all_keys}
    targets = [key] if key else all_keys
    findings: list[dict] = []
    for k in targets:
        try:
            findings += _lint_entity(store, k, today, keys, ids)
        except (
            Exception
        ) as error:  # one unreadable record is reported, never the end of the run
            findings.append(
                _finding(
                    "error",
                    k,
                    "",
                    None,
                    "unreadable",
                    f"could not be checked: {type(error).__name__}: {error}",
                )
            )
    if key is None:
        for path in store.misnamed():
            findings.append(
                _finding(
                    "error",
                    "",
                    path,
                    None,
                    "misnamed",
                    "the store cannot address this entry file: use a lowercase kind/id folder and PROFILE.md, not a link",
                )
            )
        if problem := _tombstone_problem(store):
            findings.append(
                _finding("error", "", _TOMBSTONES, None, "unparseable", problem)
            )
        if targets and "POLICY.md" not in store.files:
            findings.append(
                _finding(
                    "warning",
                    "",
                    "POLICY.md",
                    None,
                    "no-policy",
                    "the store has no POLICY.md; `acquaint new` seeds one",
                )
            )
        if warning := store.location_warning():
            findings.append(
                _finding("warning", "", "", None, "data-root-in-repository", warning)
            )
    return {
        "errors": [f for f in findings if f["severity"] == "error"],
        "warnings": [f for f in findings if f["severity"] == "warning"],
        "checked": len(targets),
    }
