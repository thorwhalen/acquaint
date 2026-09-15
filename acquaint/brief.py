"""The brief: everything an agent should know before writing to someone, assembled in one call.

A brief is the reuse point for communication intelligence. It gathers the entry file's
card sections, the writing card (``style.md``), positions and standing objections
(``views.md``), how to reach them for this purpose, the norms of the project the message
belongs to, recent observations (marked as evidence, not facts), reminders for the
purpose, the disclosure stance, and an explicit list of what is **not** known, so gaps
get asked about instead of filled in.

**At write time**, given the conversation it is for (``ref``: correspond is asked who can
read it) or an audience record (``audience``), the brief also carries, before the writing
card, from :func:`acquaint.disclosure.disclose`:

- **Ceiling**: the audience in words and the least clearance among its readers;
- **Do not identify**: the records above that ceiling, with the terms that name them (the
  recipient's own record is not listed: the message goes to them);
- **Withheld**: per record, how many lines were left out of the brief, never their text. A
  line is left out when its ``[label: …]`` is above the least clearance, when its
  ``[sealed-from: …]`` names a reader, nobody, or anyone at all on a channel whose readers
  cannot all be listed, or when its tag is malformed;
- **Already told**: the records ``interaction`` log entries say were disclosed to them.

Without correspond, or when it fails, the audience is unknown and treated as public.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from acquaint.deslop import recipient_card
from acquaint.disclosure import disclose, may_see, parse_audience, person_key
from acquaint.lint import lint_store
from acquaint.lookup import NO_CHANNEL_NAMED, reach_channels
from acquaint.records import fact_tags, item_blocks, parse_log, split_frontmatter
from acquaint.resources import data_yaml
from acquaint.store import AcquaintError, Store
from acquaint.trust import LABELS

__all__ = ["CARD_SECTIONS", "compose_brief"]

#: Entry-file sections a brief carries, in the order it shows them.
CARD_SECTIONS = ("Who", "Write to them", "Read them", "Don't", "Now")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_UNTIL_RE = re.compile(r"\(until:\s*(\d{4}-\d{2}-\d{2})\)")
#: An audience scope in words, when the audience record comes without them.
_SCOPE_WORDS = {
    "public": "world-readable",
    "org": "readable across an organisation",
    "group": "readable by a group's members",
    "named": "readable by its named recipients",
    "operator": "seen by the operator only",
}
#: What to write for, at each least clearance.
_CEILING_ADVICE = {
    "clear": "write for a stranger",
    "green": "leave out anything labelled amber or red",
    "amber": "leave out anything labelled red",
    "red": "no label ceiling",
}
#: Disclosure gaps that mean a reader could not be pinned to one person.
_STRANGER_GAPS = ("unrecorded", "ambiguous", "not_a_person")
_UNKNOWN_AUDIENCE_WARNING = "audience unknown; treated as public"


def _visible(text: str) -> str:
    """Section text with HTML comments and blank runs removed; empty when only guidance comments remain."""
    text = _COMMENT_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _minimise(text: str, keep: Callable[[str], bool]) -> tuple[str, int]:
    """The text without the items ``keep`` refuses, and how many went; an item spanning several lines goes whole."""
    drop: set[int] = set()
    count = 0
    for _, first, last, item in item_blocks(text):
        if not keep(item):
            drop.update(range(first, last + 1))
            count += 1
    kept = "\n".join(
        line
        for number, line in enumerate(text.split("\n"), start=1)
        if number not in drop
    )
    return kept.strip(), count


def _drop_expired(text: str, today: str) -> str:
    """The text without items whose ``(until: …)`` has passed; an item spanning several lines goes whole."""

    def current(item: str) -> bool:
        until = _UNTIL_RE.search(item)
        return not until or until.group(1) >= today

    return _minimise(text, current)[0]


def _by_title(section_map: dict[str, str]) -> dict[str, str]:
    return {title.lower(): text for title, text in section_map.items()}


def _recent_observations(entity, limit: int) -> list[dict]:
    entries = [
        {**entry, "ref": f"{name}#{entry['id']}"}
        for name in sorted(n for n in entity if n.startswith("log/"))
        for entry in parse_log(entity[name])
    ]
    return entries[-limit:] if limit else entries


# ------------------------------------------------------------------ the audience


def _ask_correspond(ref: str) -> Any:
    """The default audience reader: ``correspond.audience(ref)``."""
    import correspond

    return correspond.audience(ref)


def _as_record(found: Any) -> tuple[dict, str | None]:
    """An audience (a correspond ``Audience``, its dict, or ``correspond.tools.audience``'s result) as ``(record, words)``."""
    if hasattr(found, "to_dict"):
        words = found.in_words() if hasattr(found, "in_words") else None
        return dict(found.to_dict()), words
    if isinstance(found, Mapping):
        if isinstance(found.get("audience"), Mapping):
            return dict(found["audience"]), found.get("words")
        return dict(found), None
    raise AcquaintError(
        f"an audience is a correspond Audience record, not {type(found).__name__}"
    )


def _audience_record(
    ref: str | None, audience: Any, reader: Callable[[str], Any] | None
) -> tuple[dict, str | None, list[str]]:
    """``(record, words, warnings)`` for the audience given, or the one ``reader`` finds for ``ref``; unknown is public."""
    if ref is not None and audience is not None:
        raise AcquaintError(
            "give a conversation reference or an audience record, not both"
        )
    if audience is not None:
        if isinstance(audience, str):
            try:
                audience = json.loads(audience)
            except json.JSONDecodeError as error:
                raise AcquaintError(f"the audience is not valid JSON: {error}") from error
        return (*_as_record(audience), [])
    try:
        return (*_as_record((reader or _ask_correspond)(ref)), [])
    except Exception as error:  # correspond missing or failing: an audience nobody could compute is public
        reason = (
            "correspond is not installed"
            if isinstance(error, ImportError)
            else f"{type(error).__name__}: {error}"
        )
        unknown = {"ref": str(ref), "scope": "public", "complete": False, "readers": [], "defaulted": True}
        return unknown, None, [f"{_UNKNOWN_AUDIENCE_WARNING} ({reason})"]


def _words(record: Mapping) -> str:
    """The audience in words, from its scope, when the record came without them."""
    parsed = parse_audience(record)
    words = _SCOPE_WORDS[parsed["scope"]]
    if record.get("defaulted") not in (None, False):
        return f"{words} (assumed: the audience could not be determined)"
    if not parsed["complete"] and parsed["scope"] in ("named", "group", "org"):
        return f"{words}; not every reader is listed"
    return words


def _ceiling(
    store: Store,
    entity,
    *,
    ref: str | None,
    audience: Any,
    project_key: str | None,
    today: str,
    audience_reader: Callable[[str], Any] | None,
) -> dict[str, Any]:
    """The write-time additions to a brief, and ``keep``: whether one line of the record may stay in it."""
    record, words, warnings = _audience_record(ref, audience, audience_reader)
    answer = disclose(
        store,
        [entity.ref],
        projects=[project_key] if project_key else (),
        audience=record,
        today=today,
    )
    least = answer["least_clearance"]
    unlisted = (answer["audience"] or {}).get("ceiling") is not None or any(
        answer["gaps"][gap] for gap in _STRANGER_GAPS
    )
    readers = {key for slug in answer["people"] if (key := person_key(store, slug))}

    def keep(text: str) -> bool:
        tags = fact_tags(text)
        if tags["problems"] or (tags["label"] is not None and tags["label"] not in LABELS):
            return False
        if tags["label"] is not None and not may_see(least, tags["label"]):
            return False
        if tags["sealed_from"]:
            sealed = {person_key(store, r, handle_prefix=True) for r in tags["sealed_from"]}
            if unlisted or None in sealed or sealed & readers:
                return False
        return True

    grouped: dict[str, dict[str, Any]] = {}
    for term in answer["vocabulary"]:
        if term["entity"] == entity.ref:
            continue
        row = grouped.setdefault(
            term["entity"],
            {"entity": term["entity"], "label": term["label"], "sealed_from": term["sealed_from"], "terms": []},
        )
        row["terms"].append(term["term"])
    if answer["gaps"]["unreadable"] or answer["gaps"]["unresolved_seals"]:
        warnings.append(
            "some records could not be read, or a seal names nobody; ask the operator before relying on this ceiling"
        )
    words = words or _words(record)
    return {
        "audience": record,
        "ceiling": {
            "audience": words,
            "least_clearance": least,
            "line": f"{words}; {_CEILING_ADVICE[least]}",
        },
        "do_not_identify": list(grouped.values()),
        "already_told": answer["people"].get(entity.slug, {}).get("already_told", []),
        "warnings": [*warnings, *answer["warnings"]],
        "keep": keep,
    }


def compose_brief(
    store: Store,
    key: str,
    *,
    purpose: str | None = None,
    project: str | None = None,
    ref: str | None = None,
    audience: Mapping | str | None = None,
    today: str | None = None,
    audience_reader: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Assemble the brief for writing to one entity, as data plus a Markdown ``text`` rendering.

    With ``ref`` (a conversation reference) or ``audience`` (an audience record, or its
    JSON), the brief is held to that audience's ceiling (see the module docstring).
    ``audience_reader`` finds the audience for a ``ref``: ``correspond.audience`` by default.
    """
    today = today or date.today().isoformat()
    entity = store[key]
    purposes = data_yaml("purposes.yaml")
    budgets = data_yaml("policy.yaml")["budgets"]

    profile = _by_title(entity.sections)
    card = {title: _visible(profile.get(title.lower(), "")) for title in CARD_SECTIONS}
    card["Now"] = _drop_expired(card["Now"], today)
    style_text = (
        _visible(split_frontmatter(entity.text("style.md"))[1])
        if "style.md" in entity
        else ""
    )
    views_text = _visible(entity.text("views.md"))
    writing = recipient_card(entity)
    tolerance = writing["tolerance"]
    disclosure = writing["disclosure"] or purposes["disclosure"].get(
        tolerance, purposes["disclosure"]["unknown"]
    )
    spec = purposes["purposes"].get(str(purpose).lower(), {}) if purpose else {}
    reminders = list(purposes["default"]["reminders"]) + list(spec.get("reminders", []))

    reach = reach_channels(
        store,
        key,
        defaults_text=store.files["_defaults/rules.yaml"]
        if "_defaults/rules.yaml" in store.files
        else "",
        purpose=purpose,
        project=project,
    )["channels"]

    norms, project_key = "", None
    if project:
        try:
            project_key = store.find(
                project if ":" in project or "/" in project else f"project:{project}"
            )
            project_sections = _by_title(store[project_key].sections)
            norms = "\n\n".join(
                filter(
                    None,
                    (_visible(project_sections.get(t, "")) for t in ("norms", "now")),
                )
            )
        except (KeyError, AcquaintError):
            project_key = None

    affiliations = [
        " · ".join(str(link[k]) for k in ("to", "relation", "role") if link.get(k))
        for link in entity.links
    ]
    observations = _recent_observations(entity, budgets["brief_observations"])
    lint = lint_store(store, key, today=today)

    gaps = [
        f"nothing recorded under '{title}'"
        for title in ("Write to them", "Read them", "Don't")
        if not card[title]
    ]
    if not style_text:
        gaps.append(
            "no writing card (style.md): register, length and AI tolerance are unknown"
        )
    if not entity.identities:
        gaps.append("no identities (handles or addresses) recorded")
    if not any(ch["tier"] != "none" for ch in reach):
        gaps.append("no channel rules match this context")
    if project and not project_key:
        gaps.append(f"no project {project!r} in the store, so no project norms")

    at_write_time: dict[str, Any] = {}
    warnings = list(writing["warnings"])
    if ref is not None or audience is not None:
        at_write_time = _ceiling(
            store,
            entity,
            ref=ref,
            audience=audience,
            project_key=project_key,
            today=today,
            audience_reader=audience_reader,
        )
        keep = at_write_time.pop("keep")
        warnings += at_write_time.pop("warnings")
        counts: dict[str, int] = {}

        def minimised(text: str, record_ref: str) -> str:
            kept, dropped = _minimise(text, keep)
            if dropped:
                counts[record_ref] = counts.get(record_ref, 0) + dropped
            return kept

        card = {title: minimised(text, entity.ref) for title, text in card.items()}
        style_text = minimised(style_text, entity.ref)
        views_text = minimised(views_text, entity.ref)
        if norms:
            project_ref = store[project_key].ref
            hidden = {row["entity"] for row in at_write_time["do_not_identify"]}
            if project_ref in hidden:  # a project above the ceiling: none of its norms reach the drafter
                counts[project_ref] = len(item_blocks(norms))
                norms = ""
            else:
                norms = minimised(norms, project_ref)
        shown = [entry for entry in observations if keep(entry["text"])]
        if len(shown) < len(observations):
            counts[entity.ref] = counts.get(entity.ref, 0) + len(observations) - len(shown)
        observations = shown
        at_write_time["withheld"] = [{"entity": r, "count": n} for r, n in counts.items()]

    result = {
        "id": entity.slug,
        "key": key,
        "name": entity.name,
        "purpose": purpose,
        "project": project,
        "relational": bool(spec.get("relational")),
        "ai_tolerance": tolerance,
        "disclosure": " ".join(str(disclosure).split()),
        "reach": reach,
        "card": card,
        "style": style_text,
        "views": views_text,
        "project_norms": norms,
        "affiliations": affiliations,
        "observations": observations,
        "reminders": reminders,
        "gaps": gaps,
        "lint": {"errors": len(lint["errors"]), "warnings": len(lint["warnings"])},
        "warnings": warnings,
        **at_write_time,
    }
    result["text"] = _render(entity, result)
    return result


def _render_ceiling(brief: dict[str, Any]) -> list[str]:
    ceiling = brief["ceiling"]
    out = ["## Ceiling", f"{ceiling['line']} (least clearance: {ceiling['least_clearance']}).", ""]
    out.append("## Do not identify")
    out += [
        f"- {row['entity']} [{row['label']}]: {', '.join(row['terms'])}"
        + (f" (sealed from {', '.join(row['sealed_from'])})" if row["sealed_from"] else "")
        for row in brief["do_not_identify"]
    ] or ["Nothing above the ceiling."]
    out += ["", "## Withheld"]
    out += [
        f"- {row['entity']}: {row['count']} fact{'' if row['count'] == 1 else 's'} above the ceiling, left out of this brief"
        for row in brief["withheld"]
    ] or ["Nothing."]
    out += ["", "## Already told"]
    out += [
        f"- {row['entity']} ({row['date']}, {row['entry']})" for row in brief["already_told"]
    ] or ["Nothing recorded."]
    return out + [""]


def _render(entity, brief: dict[str, Any]) -> str:
    title = f"# Brief: {brief['name']} ({entity.ref})"
    scope = " · ".join(
        filter(
            None,
            [
                brief["purpose"] and f"purpose: {brief['purpose']}",
                brief["project"] and f"project: {brief['project']}",
            ],
        )
    )
    out = [title + (f", {scope}" if scope else ""), ""]
    if description := entity.meta.get("description"):
        out += [str(description), ""]
    if brief["relational"]:
        out += [
            f"**This is a relational message ({brief['purpose']}). The operator writes it; do not draft the text.**",
            "",
        ]
    if "ceiling" in brief:
        out += _render_ceiling(brief)

    out.append("## How to reach them")
    if brief["reach"]:
        for n, ch in enumerate(brief["reach"], start=1):
            what = ch["channel"] or ch["instruction"] or NO_CHANNEL_NAMED
            # An address built from an identity is who the person *is*, not necessarily
            # somewhere to send: a channel addressed by conversation does not take one.
            # Say which it is in the prose, since that is what a writing agent reads.
            derived = (
                " (from their identities)" if ch.get("address_kind") == "identity" else ""
            )
            where = f" → {ch['address']}{derived}" if ch["address"] else ""
            why = f"{ch['tier']} rule" if ch["tier"] != "none" else ch["instruction"]
            source = f"; source: {ch['source']}" if ch.get("source") else ""
            note = f"; {ch['note']}" if ch.get("note") else ""
            out.append(f"{n}. {what}{where} ({why}{source}{note})")
    else:
        out.append("No active identities or channel rules recorded.")
    out.append("")

    for heading in CARD_SECTIONS:
        if brief["card"][heading]:
            out += [f"## {heading}", brief["card"][heading], ""]
    if brief["affiliations"]:
        out += ["## Affiliations", *(f"- {a}" for a in brief["affiliations"]), ""]
    out += [
        "## Writing card",
        f"AI tolerance: {brief['ai_tolerance']}"
        + (" (treated as neutral)" if brief["ai_tolerance"] == "unknown" else "")
        + f". Disclosure: {brief['disclosure']}",
    ]
    if brief["style"]:
        out += ["", brief["style"]]
    out.append("")
    if brief["views"]:
        out += ["## Positions and standing objections", brief["views"], ""]
    if brief["project_norms"]:
        out += [f"## Norms of {brief['project']}", brief["project_norms"], ""]
    if brief["observations"]:
        out.append("## Recent observations (evidence, not yet profile facts)")
        for entry in brief["observations"]:
            out.append(
                f"- {entry['date']} · {entry['kind']}: {entry['text']} (source: {entry.get('source', 'none given')}; {entry['ref']})"
            )
        out.append("")
    out += [
        f"## For this message{' (' + brief['purpose'] + ')' if brief['purpose'] else ''}",
        *(f"- {r}" for r in brief["reminders"]),
        "",
    ]
    if brief["gaps"]:
        out += ["## Not known (ask, don't guess)", *(f"- {g}" for g in brief["gaps"]), ""]
    if brief["lint"]["errors"]:
        out += [
            f"**This record has {brief['lint']['errors']} lint error(s); run `acquaint lint {entity.slug}` before relying on it.**",
            "",
        ]
    out.append(
        f'Before sending: `acquaint style-lint --recipient {entity.slug} "<draft>"` and `acquaint check "<draft>"`.'
    )
    return "\n".join(out).rstrip() + "\n"
