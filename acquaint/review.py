"""What the store says about one person's disclosure standing, for the operator to confirm when a relationship changes.

``acquaint review <person>`` is for when a collaboration ends, when someone changes role,
and before a tier is changed. It lists, with sources and dates:

- every tier entry in ``trust.yaml``, and which one is in force;
- every link, current or not;
- the ``default_tier`` of each currently linked org or project (what applies when no tier
  entry is in force) and the ``clearance`` of each linked org or group;
- every record sealed from the person, directly or through a record they are linked to,
  and every fact line whose ``[sealed-from: …]`` names them;
- every rule in their ``rules.yaml``, and every rule elsewhere that names them.

An **ended affiliation** is a link whose ``until`` has passed while a permissive tier
recorded before that date is still in force (:func:`acquaint.trust.ended_affiliations`):
``review`` reports it as not ok, and ``acquaint lint`` warns about it. Nothing here
changes the store.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

from acquaint.disclosure import id_list, person_key
from acquaint.records import blank_frontmatter, fact_tags, parse_log, sectioned_items
from acquaint.store import ENTRY_FILE, AcquaintError, Entity, Store
from acquaint.trust import (
    CLEARANCE_KINDS,
    DEFAULT_TIER_KINDS,
    effective_tier,
    ended_affiliations,
    link_state,
    tier_in_force,
)

__all__ = ["review_person"]

_PERSON_KIND = "person"
#: Link states under which a linked record still bears on the person (an unreadable date is not proof a link ended).
_BEARING_STATES = ("current", "unreadable")
_FACT_FILES = (ENTRY_FILE, "style.md", "views.md")


def _find_key(store: Store, ref: Any) -> str | None:
    try:
        return store.find(str(ref))
    except (KeyError, AcquaintError):
        return None


def _mentions(value: Any, names: set[str]) -> bool:
    """Whether any string inside a rule is exactly one of ``names`` (never a substring)."""
    if isinstance(value, dict):
        return any(_mentions(v, names) for v in value.values())
    if isinstance(value, list):
        return any(_mentions(v, names) for v in value)
    return isinstance(value, str) and value.strip().lower() in names


def _fact_lines(entity: Entity) -> Iterator[tuple[str, int | None, str]]:
    """``(file, line, text)`` for every item that can carry a fact tag: entry file, writing card, views, log entries."""
    for file in _FACT_FILES:
        for _, number, item in sectioned_items(blank_frontmatter(entity.text(file))):
            yield file, number, item
    for log_name in sorted(name for name in entity if name.startswith("log/")):
        for entry in parse_log(entity[log_name]):
            yield f"{log_name}#{entry['id']}", None, entry["text"]


def _seals(
    store: Store, person: Entity, linked: set[str]
) -> tuple[list[dict], list[dict]]:
    """Records sealed from the person, directly or through a linked record; and fact lines sealed from them."""
    records, facts = [], []
    for key in store:
        other = store[key]
        for ref in id_list(other.meta.get("sealed_from")):
            target = person_key(store, ref, handle_prefix=True)
            if target == person.key or target in linked:
                records.append(
                    {
                        "entity": other.ref,
                        "sealed_from": ref,
                        "via": None if target == person.key else store[target].ref,
                        "label_source": other.meta.get("label_source"),
                    }
                )
        for file, line, text in _fact_lines(other):
            if any(
                person_key(store, ref, handle_prefix=True) == person.key
                for ref in fact_tags(text)["sealed_from"]
            ):
                facts.append({"entity": other.ref, "file": file, "line": line})
    return records, facts


def _linked_fields(
    store: Store, keys: list[str], field: str, kinds: tuple[str, ...]
) -> list[dict]:
    return [
        {
            "entity": store[k].ref,
            field: store[k].meta[field],
            "label_source": store[k].meta.get("label_source"),
        }
        for k in keys
        if store[k].kind in kinds and store[k].meta.get(field) not in (None, "")
    ]


def review_person(
    store: Store, key: str, *, today: str | date | None = None
) -> dict[str, Any]:
    """The review list for one person (by store key). See the module docstring; reads only."""
    today = str(today) if today else date.today().isoformat()
    person = store[key]
    if person.kind != _PERSON_KIND:
        raise AcquaintError(
            f"{person.ref} is not a person: review lists a person's tiers, links, seals and rules"
        )
    trust, links = person.trust, person.links
    in_force = tier_in_force(trust, today=today)
    tier, lapsed = effective_tier(trust, today=today)

    listed_links, linked = [], []
    for link in links:
        state = link_state(link, today=today)
        target = _find_key(store, link.get("to", ""))
        listed_links.append(
            {**link, "state": state, "record": store[target].ref if target else None}
        )
        if target and state in _BEARING_STATES:
            linked.append(target)
    linked = list(dict.fromkeys(linked))

    names = {person.slug, person.ref, person.key}
    seals, fact_seals = _seals(store, person, set(linked))
    return {
        "id": person.slug,
        "key": person.key,
        "as_of": today,
        "tier_in_force": {"tier": tier, "lapsed": lapsed},
        "tiers": [{**entry, "in_force": entry is in_force} for entry in trust],
        "links": listed_links,
        "default_tiers": _linked_fields(
            store, linked, "default_tier", DEFAULT_TIER_KINDS
        ),
        "clearances": _linked_fields(store, linked, "clearance", CLEARANCE_KINDS),
        "seals": seals,
        "fact_seals": fact_seals,
        "rules": person.rules,
        "rules_elsewhere": [
            {"entity": store[k].ref, "rule": rule}
            for k in store
            if k != key
            for rule in store[k].rules
            if _mentions(rule, names)
        ],
        "ended_affiliations": ended_affiliations(trust, links, today=today),
        "errors": person.errors,
    }
