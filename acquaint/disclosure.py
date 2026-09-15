"""Who may be told what, for a set of readers: the clearance lattice over tiers, links, labels, seals and an audience.

One read-only answer (:func:`disclose`), computed from what the operator recorded
(:mod:`acquaint.trust`) and nothing else:

- Labels order ``red > amber > green > clear``. A reader's **clearance** is the most
  restrictive label they may see: ``open → amber``, ``involved → green``,
  ``need-to-know → clear``, ``reviewed → clear``. Inside a project the reader holds a
  current link to, their clearance for that project is ``red``, whatever the tier. A
  record is always cleared for its own person. A seal (``sealed_from``) beats all of it.
- The tier in force comes from ``trust.yaml``; when no entry covers today, the most
  restrictive ``default_tier`` of the orgs and projects the person is currently linked to
  applies; failing that, ``need-to-know``, reported as a gap.
- An **audience** (a correspond ``Audience`` record, as JSON) adds the readers it lists
  and, when it cannot list them all, an unlisted class at a ceiling: ``public`` → ``clear``;
  ``org`` or ``group`` → the ``clearance`` of the org or group the conversation belongs to,
  else ``clear``; an incomplete ``named`` audience → ``clear``; ``operator`` → no ceiling.
  An unknown scope reads as ``public``.
- ``least_clearance`` is the most restrictive clearance among all readers (tier-based,
  before project involvement); an unresolved reader counts as ``clear``.
- ``vocabulary`` holds the terms (name, ``aka``, ``vocabulary``) of every record that at
  least one reader, listed or not, is not cleared for, or that is sealed from a reader.

Everything fails closed. A tier, label, default tier or clearance not sourced to the
operator can restrict but never widen; an unknown tier reads ``reviewed``, an unknown label
``red``, an unknown clearance ``clear``. What cannot be resolved is listed under ``gaps``,
never guessed.

>>> may_see("amber", "green"), may_see("green", "amber"), most_restrictive_reader(["amber", "clear", "green"])
(True, False, 'clear')
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any

from acquaint.lookup import find_entity, resolve_handle
from acquaint.records import disclosed_refs, parse_log, source_kind
from acquaint.store import AcquaintError, Entity, Store
from acquaint.trust import (
    CLEARANCE_KINDS,
    DEFAULT_TIER,
    DEFAULT_TIER_KINDS,
    LABELS,
    TIERS,
    TRUST_SOURCES,
    effective_tier,
    entity_label,
    tier_in_force,
)

__all__ = [
    "INVOLVED_CLEARANCE",
    "SCOPES",
    "TIER_CLEARANCE",
    "already_told",
    "disclose",
    "may_see",
    "most_restrictive_reader",
    "parse_audience",
]

#: What each tier may see outside the reader's own projects.
TIER_CLEARANCE = {"open": "amber", "involved": "green", "need-to-know": "clear", "reviewed": "clear"}
#: A reader's clearance for a project they hold a current link to.
INVOLVED_CLEARANCE = "red"
#: correspond's audience scopes, narrowest first.
SCOPES = ("operator", "named", "group", "org", "public")
#: The scope an unknown or missing one reads as.
_UNKNOWN_SCOPE = "public"
#: What an unlisted reader, or one with no record, may see.
_STRANGER = "clear"
#: ``least_clearance`` when there is no reader to hold anything back from.
_NO_CEILING = "red"
_PERSON_KIND = "person"
_INTERACTION = "interaction"


def may_see(clearance: str, label: str) -> bool:
    """Whether a reader with ``clearance`` may be told about a record labelled ``label``."""
    return LABELS.index(clearance) <= LABELS.index(label)


def most_restrictive_reader(clearances: Iterable[str], *, default: str = _NO_CEILING) -> str:
    """The least clearance among readers (the one that sees least); ``default`` when there are none."""
    return max(clearances, key=LABELS.index, default=default)


def _tier_rank(tier: str) -> int:
    return TIERS.index(tier)


def _operator_set(meta: Mapping) -> bool:
    return source_kind(str(meta.get("label_source") or "")) == "operator"


def _listed(value: Any) -> list:
    if value in (None, ""):
        return []
    return list(value) if isinstance(value, list) else [value]


def _label(entity: Entity) -> str:
    """The record's label; one not set by the operator may restrict, never widen, the kind's default."""
    label, default = entity_label(entity.meta, entity.kind), entity_label({}, entity.kind)
    if _operator_set(entity.meta) or LABELS.index(label) <= LABELS.index(default):
        return label
    return default


def _find_key(store: Store, ref: Any) -> str | None:
    try:
        return store.find(str(ref))
    except (KeyError, AcquaintError):
        return None


def _current(link: Mapping, today: str) -> bool:
    since, until = link.get("since"), link.get("until")
    return (since in (None, "") or str(since) <= today) and (until in (None, "") or today < str(until))


def _linked(store: Store, entity: Entity, today: str) -> list[Entity]:
    """The records the entity holds a current link to (links naming no record are skipped; lint reports them)."""
    keys = [_find_key(store, link.get("to", "")) for link in entity.links if _current(link, today)]
    return [store[key] for key in dict.fromkeys(k for k in keys if k)]


def _tier(store: Store, entity: Entity, today: str) -> dict[str, Any]:
    """``{tier, recorded_tier, lapsed, review_by, source}`` in force today, failing closed; ``source`` is ``None`` when nothing is recorded."""
    entry = tier_in_force(entity.trust, today=today)
    if entry is not None:
        tier, lapsed = effective_tier(entity.trust, today=today)
        sourced = source_kind(str(entry.get("source") or "")) in TRUST_SOURCES
        if not sourced and _tier_rank(tier) < _tier_rank(DEFAULT_TIER):
            tier = DEFAULT_TIER
        return {
            "tier": tier,
            "recorded_tier": entry.get("tier"),
            "lapsed": lapsed,
            "review_by": entry.get("review_by"),
            "source": entry.get("source") if sourced else f"unsourced ({entry.get('source')!r}), read as {tier}",
        }
    defaults = []
    for other in _linked(store, entity, today):
        value = other.meta.get("default_tier")
        if other.kind not in DEFAULT_TIER_KINDS or value in (None, ""):
            continue
        value = value if value in TIERS else TIERS[-1]
        if not _operator_set(other.meta) and _tier_rank(value) < _tier_rank(DEFAULT_TIER):
            value = DEFAULT_TIER
        defaults.append((_tier_rank(value), value, other.ref))
    if defaults:
        _, tier, ref = max(defaults)
        return {"tier": tier, "recorded_tier": None, "lapsed": False, "review_by": None, "source": f"default_tier of {ref}"}
    return {"tier": DEFAULT_TIER, "recorded_tier": None, "lapsed": False, "review_by": None, "source": None}


def already_told(entity: Entity) -> list[dict[str, str]]:
    """``{entity, date, entry}`` for every record an ``interaction`` log entry says was disclosed to this person, oldest first."""
    told = [
        {"entity": ref, "date": entry["date"], "entry": f"{log_name}#{entry['id']}"}
        for log_name in sorted(name for name in entity if name.startswith("log/"))
        for entry in parse_log(entity[log_name])
        if entry["kind"] == _INTERACTION
        for ref in disclosed_refs(entry.get("disclosed", ""))
    ]
    return sorted(told, key=lambda row: (row["date"], row["entry"]))


# ------------------------------------------------------------------------ readers


def _resolve_reader(store: Store, text: str) -> tuple[str | None, str | None]:
    """``(store key, None)`` for an exact id, ref or channel identity with a named platform; else ``(None, "unrecorded" | "ambiguous")``."""
    text = text.strip()
    if ":" not in text and "/" not in text and len(store.find_id(text)) > 1:
        return None, "ambiguous"
    try:
        return find_entity(store, text, names=False), None
    except AcquaintError:
        pass
    found = resolve_handle(store, text)
    owners = sorted({m["key"] for m in found["matches"]})
    if len(owners) == 1 and found["platform"]:
        return owners[0], None
    return None, "ambiguous" if owners else "unrecorded"


def parse_audience(audience: str | Mapping | None) -> dict[str, Any] | None:
    """An audience record (a mapping, or its JSON) as ``{ref, scope, complete, readers, warnings}``, failing closed.

    ``readers`` are channel addresses (``github:octocat``), the operator's own (``is_self``)
    left out. A scope that is missing or unknown, and a ``defaulted`` record, read as
    ``public``; ``complete`` is true only when it is literally ``true``.

    >>> parse_audience('{"ref": "email:ada@example.org", "scope": "named", "complete": true, "readers": [{"channel": "email", "native_id": "ada@example.org"}]}')["readers"]
    ['email:ada@example.org']
    >>> parse_audience({"scope": "everyone"})["scope"]
    'public'
    """
    if audience is None:
        return None
    if isinstance(audience, str):
        try:
            audience = json.loads(audience)
        except json.JSONDecodeError as error:
            raise AcquaintError(f"the audience is not valid JSON: {error}") from error
    if not isinstance(audience, Mapping):
        raise AcquaintError("the audience is a JSON object: a correspond Audience record")
    warnings = []
    scope = audience.get("scope")
    if scope not in SCOPES:
        warnings.append(f"audience scope {scope!r} is not one of {', '.join(SCOPES)}; read as public")
        scope = _UNKNOWN_SCOPE
    if audience.get("defaulted") is True:
        scope = _UNKNOWN_SCOPE
    readers = []
    for reader in audience.get("readers") or []:
        if not isinstance(reader, Mapping) or reader.get("is_self") is True:
            continue
        handle = reader.get("handle") or reader.get("native_id")
        if reader.get("channel") and handle:
            readers.append(f"{reader['channel']}:{handle}")
        else:
            warnings.append(f"an audience reader without channel and id cannot be resolved: {dict(reader)!r}")
            readers.append(None)
    return {
        "ref": str(audience.get("ref") or ""),
        "scope": scope,
        "complete": audience.get("complete") is True,
        "readers": readers,
        "warnings": warnings,
    }


def _organisation(store: Store, ref: str) -> Entity | None:
    """The one org or group whose active identity is the conversation's place (``github:example/app``) or its owner (``github:example``)."""
    channel, sep, place = ref.partition(":")
    if not sep or not place:
        return None
    place = place.split("#", 1)[0].strip("/")
    for handle in dict.fromkeys([f"{channel}:{place}", f"{channel}:{place.split('/', 1)[0]}"]):
        found = resolve_handle(store, handle)
        owners = sorted({m["key"] for m in found["matches"] if store[m["key"]].kind in CLEARANCE_KINDS})
        if len(owners) == 1:
            return store[owners[0]]
    return None


def _ceiling(store: Store, audience: dict | None, gaps: dict) -> tuple[str | None, dict | None]:
    """The clearance of the readers an audience cannot list (``None``: every reader is listed, or no audience), and what it says about the audience."""
    if audience is None:
        return None, None
    scope, complete = audience["scope"], audience["complete"]
    about: dict[str, Any] = {"scope": scope, "complete": complete, "ref": audience["ref"], "organisation": None}
    if scope == "operator" or (complete and scope != "public"):
        ceiling = None
    elif scope in CLEARANCE_KINDS:
        found = _organisation(store, audience["ref"])
        ceiling = _STRANGER
        if found is None:
            gaps["organisation"].append(audience["ref"] or "(no ref)")
        else:
            about["organisation"] = found.ref
            clearance = found.meta.get("clearance")
            if clearance in LABELS and _operator_set(found.meta):
                ceiling = clearance
    else:
        ceiling = _STRANGER
    about["ceiling"] = ceiling
    return ceiling, about


# ------------------------------------------------------------------------ the answer


def _terms(entity: Entity) -> list[str]:
    """Name, aliases and vocabulary, each once (compared without case); a non-text term is kept as text."""
    seen: dict[str, str] = {}
    for term in [entity.name, *entity.aka, *_listed(entity.meta.get("vocabulary"))]:
        text = " ".join(str(term).split()) if term is not None else ""
        seen.setdefault(text.lower(), text) if text else None
    return list(seen.values())


def disclose(
    store: Store,
    people: Sequence[str] = (),
    *,
    projects: Sequence[str] = (),
    audience: str | Mapping | None = None,
    today: str | None = None,
) -> dict[str, Any]:
    """The disclosure answer for ``people`` (ids or channel identities) and an optional ``audience``.

    ``projects`` limits ``entities`` and ``vocabulary`` to those records plus every person
    record; a project that is not an exact id raises. See the module docstring for the rules.
    """
    today = today or date.today().isoformat()
    parsed = parse_audience(audience)
    if not people and parsed is None:
        raise AcquaintError("name at least one reader, or give an audience")
    scope_keys = [find_entity(store, project, names=False) for project in projects]

    gaps: dict[str, list[str]] = {"unrecorded": [], "ambiguous": [], "not_a_person": [], "no_tier": [], "organisation": []}
    readers: dict[str, dict[str, Any]] = {}  # store key -> the person's answer
    strangers: list[str] = []  # clearances of readers who have no person record

    def add_reader(text: str | None, via: str) -> None:
        if text is None:
            strangers.append(_STRANGER)
            return
        key, problem = _resolve_reader(store, text)
        if key is None:
            gaps[problem].append(text)
            strangers.append(_STRANGER)
            return
        entity = store[key]
        if entity.kind != _PERSON_KIND:
            gaps["not_a_person"].append(f"{text} ({entity.ref})")
            strangers.append(_STRANGER)
            return
        if key in readers:
            return
        tier = _tier(store, entity, today)
        if tier["source"] is None:
            gaps["no_tier"].append(entity.slug)
        readers[key] = {
            **tier,
            "clearance": TIER_CLEARANCE[tier["tier"]],
            "involved_in": [other.ref for other in _linked(store, entity, today) if other.kind == "project"],
            "already_told": already_told(entity),
            "via": via,
        }

    for person in people:
        add_reader(person, "named")
    for address in (parsed or {}).get("readers", []):
        add_reader(address, "audience")
    ceiling, about = _ceiling(store, parsed, gaps)

    unlisted = strangers + ([ceiling] if ceiling else [])
    least = most_restrictive_reader([r["clearance"] for r in readers.values()] + unlisted)

    if projects:
        people_keys = [k for k in store if store[k].kind == _PERSON_KIND]
        considered = list(dict.fromkeys(scope_keys + people_keys))
    else:
        considered = list(store)
    entities, seals, vocabulary = {}, [], []
    for key in considered:
        entity = store[key]
        label = _label(entity)
        sealed_keys = {k for ref in _listed(entity.meta.get("sealed_from")) if (k := _find_key(store, ref))}
        cleared, not_cleared, sealed = [], [], []
        for reader_key, reader in readers.items():
            slug = store[reader_key].slug
            if reader_key in sealed_keys:
                sealed.append(slug)
                not_cleared.append(slug)
            elif reader_key == key or entity.ref in reader["involved_in"] or may_see(reader["clearance"], label):
                cleared.append(slug)
            else:
                not_cleared.append(slug)
        hidden_from_unlisted = any(not may_see(clearance, label) for clearance in unlisted)
        entities[entity.ref] = {
            "label": label,
            "cleared": cleared,
            "not_cleared": not_cleared,
            "sealed_from": sorted(store[k].slug for k in sealed_keys),
            "above_unlisted_readers": hidden_from_unlisted,
        }
        seals += [{"entity": entity.ref, "from": slug} for slug in sealed]
        if not_cleared or hidden_from_unlisted:
            vocabulary += [
                {"term": term, "entity": entity.ref, "label": label, "sealed_from": sealed}
                for term in _terms(entity)
            ]

    return {
        "as_of": today,
        "people": {store[key].slug: reader for key, reader in readers.items()},
        "least_clearance": least,
        "audience": about,
        "entities": entities,
        "seals": seals,
        "vocabulary": vocabulary,
        "gaps": gaps,
        "warnings": (parsed or {}).get("warnings", []),
    }
