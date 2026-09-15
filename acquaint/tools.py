"""The single source of truth for every surface: plain functions, flat arguments in, JSON-ready dicts out.

The CLI is ``cw`` over :data:`TOOLS`; the MCP server exposes the same functions (by
``acquaint.tools:<name>`` reference); the shipped skills describe these verbs. Nothing
in this module knows about any of those surfaces.

Every tool takes ``data_dir`` (default: ``$ACQUAINT_DATA_DIR``, else ``data_dir`` in
``~/.config/acquaint/config.toml``, else ``~/.local/share/acquaint``). Every result carries
``ok`` and a one-line ``summary``; long human-readable content is in ``text``.

Tools never act on a guess. A name, alias, handle or email counts only when exactly one
entity has it exactly; a partial match is returned as a suggestion. ``rename`` and
``forget`` need the exact id. Library callers with their own store use the core
functions (:func:`acquaint.lookup.find_entity`, :func:`acquaint.brief.compose_brief`, …)
with a :class:`~acquaint.store.Store`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from acquaint import sync as _sync
from acquaint.brief import compose_brief
from acquaint.deslop import lint_text, recipient_card
from acquaint.disclosure import disclose as _disclose
from acquaint.edit import append_observation, forget_entity, new_entity, rename_entity
from acquaint.lint import lint_store
from acquaint.lookup import (
    NO_CHANNEL_NAMED,
    check_text,
    find_entity,
    match,
    reach_channels,
    resolve_handle,
)
from acquaint.review import review_person
from acquaint.store import ENTRY_FILE, AcquaintError, Entity, Store, data_dir as _data_dir
from acquaint.trust import effective_tier, entity_label

__all__ = [
    "AcquaintError",
    "SIDE_EFFECTS",
    "TOOLS",
    "brief",
    "check",
    "disclosure",
    "forget",
    "lint",
    "new",
    "reach",
    "remember",
    "rename",
    "resolve",
    "review",
    "style_lint",
    "sync_init",
    "sync_pull",
    "sync_push",
    "sync_status",
    "who",
]


def _store(data_dir: str | None) -> Store:
    return Store(data_dir)


def _field(store: Store, entity: Entity, field: str) -> Any:
    field = field.strip().lower()

    def by_platform(platform: str) -> list:
        return [
            i.get("value")
            for i in entity.identities
            if str(i.get("platform", "")).lower() == platform
            and str(i.get("status") or "active").lower() == "active"
        ]

    if field == "aka":
        return entity.aka
    if field == "label":
        return entity_label(entity.meta, entity.kind)
    if field == "tier":
        return effective_tier(entity.trust, today=date.today().isoformat())[0]
    if field in entity.meta:
        return entity.meta[field]
    if field in {"email", "emails"}:
        return by_platform("email")
    if field in {"identities", "rules", "links", "trust"}:
        return getattr(entity, field)
    if field == "path":
        return store.path_of(entity.key)
    if field == "files":
        return list(entity)
    return by_platform(field) or None


def _unreadable_warnings(found: dict) -> list[str]:
    return [
        f"{row['key']} could not be read: {row['error']}"
        for row in found.get("unreadable", [])
    ]


# --------------------------------------------------------------------- read tools


def who(
    name: str,
    *,
    field: str | None = None,
    brief: bool = False,
    data_dir: str | None = None,
) -> dict:
    """Look up one person, project, org or group by exact id, name, alias, handle or email.

    Costs scale with what you ask: ``field`` returns one value (``aka``, ``email``,
    ``github``, ``label``, ``tier``, any frontmatter key), ``brief`` the identity block, and the default the
    whole entry file. It never guesses: no exact match, or several, returns the
    candidates and ``ok: false``.
    """
    store = _store(data_dir)
    try:
        key = find_entity(store, name)
    except AcquaintError as error:
        found = match(store, name)
        candidates = [
            {"id": store[k].slug, "key": k, "name": store[k].name}
            for k in found["exact"] + found["partial"]
        ]
        known = [] if candidates else [k.split("/", 1)[1] for k in list(store)[:20]]
        summary = str(error) + (
            f"; known: {', '.join(known) or '(store is empty)'}" if not candidates else ""
        )
        return {
            "ok": False,
            "query": name,
            "candidates": candidates,
            "known": known,
            "summary": summary,
            "warnings": _unreadable_warnings(found),
        }

    entity = store[key]
    base = {"ok": True, "id": entity.slug, "key": entity.key, "name": entity.name}
    if entity.errors:
        base["warnings"] = [f"{entity.key}: {e}" for e in entity.errors]
    if field:
        value = _field(store, entity, field)
        if (
            field.strip().lower() == "tier"
            and effective_tier(entity.trust, today=date.today().isoformat())[1]
        ):
            base["warnings"] = [
                *base.get("warnings", []),
                f"{entity.slug}'s recorded tier has lapsed (its review_by has passed or is missing); "
                "it counts as need-to-know until the operator reviews it",
            ]
        if value in (None, [], ""):
            return {
                **base,
                "ok": False,
                "field": field,
                "summary": f"{entity.slug} has no recorded {field!r}",
            }
        shown = ", ".join(map(str, value)) if isinstance(value, list) else value
        return {
            **base,
            "field": field,
            "value": value,
            "summary": f"{entity.slug} {field}: {shown}",
        }
    identity = entity.summary()
    if brief:
        lines = [f"{entity.name} ({entity.ref})"] + [
            f"{k}: {v}"
            for k, v in identity.items()
            if k not in {"id", "key", "kind", "name", "schema"}
            and v not in (None, "", [])
        ]
        return {
            **base,
            "identity": identity,
            "summary": lines[0],
            "text": "\n".join(lines),
        }
    return {
        **base,
        "identity": identity,
        "path": store.path_of(entity.key),
        "files": list(entity),
        "summary": f"{entity.name} ({entity.ref})",
        "text": entity.text(ENTRY_FILE),
    }


def resolve(handle: str, *, data_dir: str | None = None) -> dict:
    """Map a channel handle (``github:octocat``, ``email:ada@example.org``) to the entity it belongs to, with the evidence.

    ``ok`` is true only when an active identity on the named platform belongs to exactly
    one entity. A handle without a platform (``@octocat``), a match by name only, an
    inactive identity, or several owners all return ``ok: false`` with what was found.
    """
    result = resolve_handle(_store(data_dir), handle)
    matches, platform = result["matches"], result["platform"]
    ids = sorted({m["id"] for m in matches})
    if len(ids) == 1 and platform:
        ok, summary = True, f"{handle} → {ids[0]} (evidence: {matches[0]['evidence']})"
    elif len(ids) == 1:
        platforms = sorted({str(m["platform"]) for m in matches})
        ok, summary = (
            False,
            f"{handle} matches {ids[0]} on {', '.join(platforms)}; name the platform (e.g. {platforms[0]}:{handle.lstrip('@')}) before acting on it",
        )
    elif ids:
        ok, summary = False, f"{handle} matches {', '.join(ids)}: do not pick one"
    elif result["inactive"]:
        ok, summary = (
            False,
            f"{handle} matches only inactive identities ({', '.join(sorted({m['id'] + ' ' + m['status'] for m in result['inactive']}))})",
        )
    elif result["by_name"]:
        ok, summary = (
            False,
            f"no identity has {handle}; by name only: {', '.join(m['id'] for m in result['by_name'])}, which is not enough to act on",
        )
    else:
        ok, summary = False, f"{handle} matches no recorded identity"
    rows = matches + result["inactive"] + result["by_name"]
    text = "\n".join(
        f"{m['id']}  {m.get('platform') or 'name'}:{m.get('value', m['name'])}  {m.get('status', '')}  evidence: {m['evidence']}".replace(
            "  evidence", " evidence"
        )
        for m in rows
    )
    return {
        "ok": ok,
        "handle": handle,
        **result,
        "summary": summary,
        "text": text or summary,
        "warnings": _unreadable_warnings(result),
    }


def check(text: str, *, data_dir: str | None = None) -> dict:
    """Scan prose that names people before publishing it: conflations (one person written as two), ambiguous names, unknown names."""
    result = check_text(_store(data_dir), text)
    lines = [
        f"CONFLATION  {c['name']} is ONE entity, written as {' / '.join(repr(f) for f in c['forms'])}: …{c['excerpt']}…"
        for c in result["conflations"]
    ]
    lines += [
        f"AMBIGUOUS   {a['form']!r} could be {', '.join(a['ids'])}"
        for a in result["ambiguous"]
    ]
    if result["unknown_candidates"]:
        lines.append(
            f"UNKNOWN     name-like phrases in no record: {', '.join(result['unknown_candidates'])}"
        )
    if result["mentioned"]:
        lines.append(f"mentioned   {', '.join(result['mentioned'])}")
    ok = not result["conflations"]
    summary = "no conflations" if ok else f"{len(result['conflations'])} conflation(s)"
    return {
        "ok": ok,
        **result,
        "summary": summary,
        "text": "\n".join(lines) or summary,
        "warnings": _unreadable_warnings(result),
    }


def reach(
    person: str,
    *,
    purpose: str | None = None,
    urgency: str | None = None,
    project: str | None = None,
    message_type: str | None = None,
    topic: str | None = None,
    data_dir: str | None = None,
) -> dict:
    """Ordered channels for reaching someone in a context. Only active addresses; returns them, sends nothing. ``outcome`` is ``reachable``, ``no_address`` (a rule matched, but neither states an address nor finds a usable one recorded for its channels) or ``no_channel``. Each channel's ``address_kind`` is ``stated``, ``identity`` (the person's handle, which a conversation-addressed channel does not take) or ``None``."""
    store = _store(data_dir)
    key = find_entity(store, person)
    defaults = (
        store.files["_defaults/rules.yaml"]
        if "_defaults/rules.yaml" in store.files
        else ""
    )
    result = reach_channels(
        store,
        key,
        defaults_text=defaults,
        purpose=purpose,
        urgency=urgency,
        project=project,
        message_type=message_type,
        topic=topic,
    )
    entity = store[key]
    channels, slug = result["channels"], entity.slug
    lines = [
        f"{n}. {c['channel'] or c['instruction'] or NO_CHANNEL_NAMED}"
        + (f" → {c['address']}" if c["address"] else "")
        + f"  [{c['tier']}]"
        + (f"  ({c['note']})" if c.get("note") else "")
        for n, c in enumerate(channels, start=1)
    ]
    usable = [c for c in channels if c["address"] or c["instruction"]]
    # A listed channel is usable, or it came from a matched rule and names a channel with no usable address.
    unaddressed = [c["channel"] for c in channels if c["channel"] and not c["address"]]
    if usable:
        outcome, summary = "reachable", f"{len(usable)} usable channel(s) for {slug}"
    elif unaddressed:
        outcome = "no_address"
        summary = (
            f"{result['rules_matched']} rule(s) matched for {slug}, but no usable address is recorded"
            f" for {', '.join(unaddressed)}; record a current one with"
            f' `acquaint remember {entity.ref} "{unaddressed[0]}:<address>" --kind identity --source <source>`'
            f" — or, when {unaddressed[0]} is addressed by conversation rather than by person,"
            f" state it on the rule instead: `do: {{channel: {unaddressed[0]}, address: <reference>}}`"
        )
    else:
        # No channel anywhere: either nothing matched, or what matched named no channel
        # (a malformed rule, whose note says so). Never an index into an empty list.
        outcome = "no_channel"
        summary = f"no matching rule names a channel for {slug}, and no active identity is recorded"
        problems = [c["note"] for c in channels if c.get("note")]
        if problems:
            summary += f"; {'; '.join(problems)}"
    return {
        "ok": bool(usable),
        "outcome": outcome,
        "id": slug,
        **result,
        "summary": summary,
        "text": "\n".join(lines) or summary,
    }


def brief(
    person: str,
    *,
    purpose: str | None = None,
    project: str | None = None,
    data_dir: str | None = None,
) -> dict:
    """Everything to know before writing to someone: card, writing style, reach, project norms, recent observations, gaps."""
    store = _store(data_dir)
    result = compose_brief(
        store, find_entity(store, person), purpose=purpose, project=project
    )
    return {
        "ok": True,
        **result,
        "summary": f"brief for {result['name']}" + (f" ({purpose})" if purpose else ""),
    }


def lint(entity: str | None = None, *, data_dir: str | None = None) -> dict:
    """Check records: every preference, view and rule sourced; tiers, labels and seals set by the operator; nothing POLICY.md forbids; files parse; entry files within budget."""
    store = _store(data_dir)
    if store.root is not None and not store.root.is_dir():
        summary = f"no store at {store.root}"
        return {
            "ok": False,
            "errors": [],
            "warnings": [],
            "checked": 0,
            "summary": summary,
            "text": summary,
        }
    result = lint_store(store, find_entity(store, entity) if entity else None)
    lines = [
        f"{f['severity']:7} {'/'.join(filter(None, [f['entity'], f['file']]))}"
        + (f":{f['line']}" if f["line"] else "")
        + f"  {f['rule']}: {f['message']}"
        for f in result["errors"] + result["warnings"]
    ]
    ok = not result["errors"]
    summary = f"{result['checked']} checked, {len(result['errors'])} error(s), {len(result['warnings'])} warning(s)"
    return {"ok": ok, **result, "summary": summary, "text": "\n".join(lines + [summary])}


def disclosure(
    people: list[str],
    *,
    projects: list[str] | None = None,
    audience: str | None = None,
    today: str | None = None,
    data_dir: str | None = None,
) -> dict:
    """Who may be told what, before writing to a set of readers (ids or channel identities, plus an optional correspond ``audience`` record as JSON): the tier and clearance in force for each, the least clearance, which records each is cleared for, the seals, the vocabulary a gate must scan for, what each was already told, and the gaps. ``projects`` limits the records to those plus people. Reads only."""
    result = _disclose(
        _store(data_dir),
        people,
        projects=projects or (),
        audience=audience,
        today=today,
    )
    lines = []
    for slug, person in result["people"].items():
        involved = (
            f"; involved in {', '.join(person['involved_in'])}"
            if person["involved_in"]
            else ""
        )
        lapsed = (
            f" (recorded {person['recorded_tier']}, lapsed)" if person["lapsed"] else ""
        )
        source = person["source"] or "nothing recorded"
        told = ", ".join(f"{t['entity']} ({t['date']})" for t in person["already_told"])
        lines.append(
            f"{slug}: {person['tier']}{lapsed} → clearance {person['clearance']} [{source}]{involved}"
            + (f"; already told {told}" if told else "")
        )
    if result["audience"]:
        audience_line = result["audience"]
        lines.append(
            f"audience: {audience_line['scope']}"
            + ("" if audience_line["complete"] else ", not every reader listed")
            + (
                f", unlisted readers at {audience_line['ceiling']}"
                if audience_line["ceiling"]
                else ""
            )
            + (
                f" ({audience_line['organisation']})"
                if audience_line["organisation"]
                else ""
            )
        )
    lines.append(f"least clearance: {result['least_clearance']}")
    lines += [f"sealed: {s['entity']} from {s['from']}" for s in result["seals"]]
    records: dict[str, list[dict]] = {}
    for term in result["vocabulary"]:
        records.setdefault(term["entity"], []).append(term)
    if records:
        lines.append(f"do not identify ({len(result['vocabulary'])} term(s)):")
        lines += [
            f"  {ref} [{terms[0]['label']}]: " + ", ".join(t["term"] for t in terms)
            for ref, terms in sorted(records.items())
        ]
    lines += [
        f"gap: {name}: {', '.join(values)}"
        for name, values in result["gaps"].items()
        if values
    ]
    summary = (
        f"least clearance {result['least_clearance']}; {len(records)} record(s) not to identify, "
        f"{len(result['seals'])} seal(s), {sum(map(len, result['gaps'].values()))} gap(s)"
    )
    return {
        "ok": True,
        **result,
        "summary": summary,
        "text": "\n".join(lines + [summary]),
    }


def review(person: str, *, today: str | None = None, data_dir: str | None = None) -> dict:
    """Everything the store says about one person's disclosure standing, with sources and dates, to confirm when a collaboration ends, when someone changes role, or before a tier changes: tier entries, links, the default tiers and clearances reached through links, seals on records and on fact lines, and the rules that name them. Not ok when an affiliation has ended while a permissive tier is still in force. Reads only."""
    store = _store(data_dir)
    result = review_person(store, find_entity(store, person), today=today)
    slug, in_force = result["id"], result["tier_in_force"]

    def dated(entry: dict, *fields: str) -> str:
        return ", ".join(f"{f} {entry[f]}" for f in fields if entry.get(f) not in (None, ""))

    def rule_line(rule: dict) -> str:
        return f"when {rule.get('when')} do {rule.get('do')}  [source: {rule.get('source')}]"

    sections = [
        ("tiers (trust.yaml)", [
            f"{t.get('tier')}  {dated(t, 'valid_from', 'valid_to', 'review_by', 'recorded')}  [source: {t.get('source')}]"
            + ("  <- in force" if t["in_force"] else "")
            for t in result["tiers"]
        ]),
        ("links (links.yaml)", [
            f"{link.get('record') or link.get('to')}  {link['state']}"
            + (f"  role {link['role']}" if link.get("role") else "")
            + (f"  {dated(link, 'since', 'until')}" if dated(link, "since", "until") else "")
            + f"  [source: {link.get('source')}]"
            for link in result["links"]
        ]),
        ("default tiers of linked records (apply when no tier entry is in force)", [
            f"{d['entity']}: {d['default_tier']}  [label_source: {d['label_source']}]" for d in result["default_tiers"]
        ]),
        ("clearances of linked orgs and groups", [
            f"{c['entity']}: {c['clearance']}  [label_source: {c['label_source']}]" for c in result["clearances"]
        ]),
        (f"records sealed from {slug}", [
            s["entity"] + (f"  via {s['via']}" if s["via"] else "") + f"  [label_source: {s['label_source']}]"
            for s in result["seals"]
        ]),
        (f"fact lines sealed from {slug}", [
            f"{f['entity']}  {f['file']}" + (f":{f['line']}" if f["line"] else "") for f in result["fact_seals"]
        ]),
        ("rules (rules.yaml)", [rule_line(r) for r in result["rules"]]),
        (f"rules elsewhere naming {slug}", [f"{r['entity']}: {rule_line(r['rule'])}" for r in result["rules_elsewhere"]]),
    ]
    lines = [f"{slug} as of {result['as_of']}: tier in force {in_force['tier']}" + (" (lapsed)" if in_force["lapsed"] else "")]
    for title, items in sections:
        if items:
            lines += [f"{title}:", *(f"  {item}" for item in items)]
    problems = [
        f"affiliation ended: the link to {e['to']} ended on {e['until']}, but the {e['tier']} tier"
        + (f" recorded {e['tier_recorded']}" if e["tier_recorded"] else "")
        + " is still in force; confirm or change the tier"
        for e in result["ended_affiliations"]
    ]
    summary = "; ".join(problems) or (
        f"{slug}: tier {in_force['tier']}; {len(result['links'])} link(s), "
        f"{len(result['seals']) + len(result['fact_seals'])} seal(s), "
        f"{len(result['rules']) + len(result['rules_elsewhere'])} rule(s) to confirm"
    )
    return {"ok": not problems, **result, "summary": summary, "text": "\n".join(lines + problems)}


def style_lint(
    text: str,
    *,
    recipient: str | None = None,
    tolerance: str | None = None,
    data_dir: str | None = None,
) -> dict:
    """The deterministic half of deslop: machine-writing tells in a draft, at the recipient's tolerance and against their blocklist."""
    card: dict[str, Any] = {"tolerance": "unknown", "blocklist": [], "warnings": []}
    if recipient:
        store = _store(data_dir)
        card = recipient_card(store[find_entity(store, recipient)])
    level = tolerance or card["tolerance"]
    result = lint_text(text, tolerance=level, blocklist=card["blocklist"])
    route = (
        result["relational_message"]
        if result["relational"]
        else "operator approves; an explicit disclosure decision is required"
        if level == "averse"
        else "no special handling"
        if level == "tolerant"
        else "operator approves before sending"
    )
    enforced = [f for f in result["findings"] if f["enforced"]]
    lines = [
        f"{f['tier']} {f['rule']}: {f['message']}"
        + (f"  …{f['excerpt']}…" if f["excerpt"] else "")
        for f in enforced
    ]
    summary = f"{len(enforced)} finding(s) to fix at tolerance {level}; route: {route}"
    return {
        **result,
        "recipient": recipient,
        "route": route,
        "summary": summary,
        "text": "\n".join(lines + [summary]),
        "warnings": card["warnings"],
    }


# -------------------------------------------------------------------- write tools


def remember(
    entity: str,
    text: str,
    *,
    source: str | None = None,
    kind: str = "observation",
    disclosed: list[str] | None = None,
    reactivate: bool = False,
    data_dir: str | None = None,
) -> dict:
    """Append a dated observation (``observation``, ``interaction``, ``identity``, ``preference``, ``view``, ``rule``) to an entity's log, with its source. An ``interaction`` may list the records the message identified (``disclosed``: exact ids, never the text). An identity equal to an inactive one (``stale``, ``retracted``, …) is refused, naming that entry and the command with which the operator can make it active again."""
    store = _store(data_dir)
    result = append_observation(
        store,
        find_entity(store, entity),
        text,
        source=source,
        kind=kind,
        reactivate=reactivate,
        disclosed=disclosed or (),
    )
    identity = result.get("identity") or {}
    if identity.get("change") == "reactivated":
        summary = f"reactivated identity {identity['handle']} (was {identity['previous_status']}) for {result['id']}; logged {result['ref']}"
    elif identity.get("change") == "already_usable":
        summary = f"{identity['handle']} is already a usable identity for {result['id']}; logged {result['ref']}"
    else:
        summary = f"recorded {result['kind']} {result['ref']} for {result['id']}"
    return {"ok": True, **result, "summary": summary}


def new(
    kind: str,
    name: str,
    *,
    qualifier: str | None = None,
    description: str | None = None,
    force: bool = False,
    data_dir: str | None = None,
) -> dict:
    """Create a person, project, org or group from its template (a readable slug id; ``qualifier`` separates two of the same name)."""
    result = new_entity(
        _store(data_dir),
        kind,
        name,
        qualifier=qualifier,
        description=description,
        force=force,
    )
    return {
        "ok": True,
        **result,
        "summary": f"created {result['key']} at {result['path']}",
    }


def rename(entity: str, to: str, *, data_dir: str | None = None) -> dict:
    """Change an entity's id (``to`` is a slug) or name and id (``to`` is a name), rewriting links to it. Needs the exact id."""
    store = _store(data_dir)
    result = rename_entity(store, find_entity(store, entity, names=False), to)
    return {
        "ok": True,
        **result,
        "summary": f"renamed {result['from']} → {result['to']}; relinked {len(result['relinked'])} file(s)",
    }


def forget(entity: str, *, confirm: bool = False, data_dir: str | None = None) -> dict:
    """Remove an entity's folder and leave a salted tombstone. Needs the exact id; without ``confirm``, only reports what would be removed."""
    result = forget_entity(_store(data_dir), entity, confirm=confirm)
    mentions = [
        f"still mentioned in {r['file']} ({', '.join(r['mentions'])})"
        for r in result["references"]
    ]
    if not result["done"]:
        summary = f"would remove {len(result['files'])} file(s) of {result['key']}; pass --confirm to do it"
        return {
            "ok": True,
            **result,
            "summary": summary,
            "text": "\n".join([*result["files"], *mentions, summary]),
        }
    note = (
        ["Other records still mention them; forget does not edit them:", *mentions]
        if mentions
        else []
    )
    return {
        "ok": True,
        **result,
        "summary": f"forgot {result['key']}",
        "text": "\n".join([f"forgot {result['key']}", *result["history_rewrite"], *note]),
    }


# ------------------------------------------------------------------------- sync


def sync_init(
    *,
    repo: str,
    remote_url: str | None = None,
    existing_only: bool = False,
    dry_run: bool = False,
    data_dir: str | None = None,
) -> dict:
    """Make the data root a checkout of a PRIVATE GitHub repository (created private through ``gh`` unless ``existing_only``), with a pre-push guard."""
    result = _sync.init(
        _data_dir(data_dir),
        repo,
        remote_url=remote_url,
        create=not existing_only,
        dry_run=dry_run,
    )
    if dry_run:
        return {
            "ok": True,
            **result,
            "summary": f"dry run: would sync the store to {repo}",
            "text": "\n".join(result["plan"]),
        }
    return {
        "ok": True,
        **result,
        "summary": f"store synced to {repo} ({result['visibility']}); pre-push guard installed",
    }


def sync_push(
    *, message: str | None = None, dry_run: bool = False, data_dir: str | None = None
) -> dict:
    """Commit, rebase onto the remote and push the store, after re-checking the remote, the guard and the visibility."""
    result = _sync.push(_data_dir(data_dir), message=message, dry_run=dry_run)
    summary = (
        f"would commit {result['would_commit']} change(s)"
        if dry_run
        else f"pushed to {result['repo']}"
        if result.get("pushed")
        else result.get("note", "nothing pushed")
    )
    return {"ok": True, **result, "summary": summary}


def sync_pull(*, dry_run: bool = False, data_dir: str | None = None) -> dict:
    """Pull the store from its private remote, rebasing local work on top."""
    result = _sync.pull(_data_dir(data_dir), dry_run=dry_run)
    return {
        "ok": True,
        **result,
        "summary": "dry run: " + "; ".join(result["plan"])
        if dry_run
        else f"pulled {result['repo']} at {result['head']}",
    }


def sync_status(*, check_visibility: bool = True, data_dir: str | None = None) -> dict:
    """Whether the store is synced, to which repository, uncommitted changes, ahead/behind, the guard, and live visibility."""
    result = _sync.status(_data_dir(data_dir), check_visibility=check_visibility)
    if not result["synced"]:
        return {"ok": True, **result, "summary": result["note"]}
    problems = [
        p
        for p, bad in (
            (
                "visibility is not PRIVATE",
                result.get("visibility", "PRIVATE") != "PRIVATE",
            ),
            (
                "pre-push guard missing, changed or not active",
                not result["hook_installed"],
            ),
        )
        if bad
    ]
    lines = [f"{k}: {v}" for k, v in result.items() if k != "synced"]
    return {
        "ok": not problems,
        **result,
        "problems": problems,
        "summary": "; ".join(problems) or f"synced to {result['repo']}",
        "text": "\n".join(lines + problems),
    }


#: Every tool, in the order surfaces list them.
TOOLS = [
    who,
    resolve,
    check,
    reach,
    brief,
    remember,
    lint,
    new,
    rename,
    forget,
    sync_init,
    sync_push,
    sync_pull,
    sync_status,
    style_lint,
    disclosure,
    review,
]

#: What each tool changes, for surfaces that must decide what to expose or confirm.
#: ``read`` changes nothing and stays local; ``append`` adds to a log; ``create`` adds a
#: record; ``rewrite`` changes existing records; ``destructive`` removes data;
#: ``external-read`` queries a remote service; ``external`` acts on one.
SIDE_EFFECTS = {
    "who": "read",
    "resolve": "read",
    "check": "read",
    "reach": "read",
    "brief": "read",
    "lint": "read",
    "style_lint": "read",
    "disclosure": "read",
    "review": "read",
    "remember": "append",
    "new": "create",
    "rename": "rewrite",
    "sync_pull": "rewrite",
    "forget": "destructive",
    "sync_status": "external-read",
    "sync_init": "external",
    "sync_push": "external",
}
