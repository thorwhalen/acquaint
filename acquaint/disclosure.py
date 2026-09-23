"""Who may be told what, for a set of readers: the clearance lattice over tiers, links, labels, seals and an audience.

One read-only answer (:func:`disclose`), computed from what the operator recorded
(:mod:`acquaint.trust`) and nothing else:

- Labels order ``red > amber > green > clear``. A reader's **clearance** is the most
  restrictive label they may see: ``open → amber``, ``involved → green``,
  ``need-to-know → clear``, ``reviewed → clear``. Inside a project the reader holds a
  current, operator-sourced link to, their clearance for that project is ``red``, whatever
  the tier. A reader is always cleared for their own record. A seal (``sealed_from``)
  beats all of it; a seal naming an org, group or project seals everyone currently linked
  to it.
- The tier in force comes from ``trust.yaml``; when no entry covers today, the most
  restrictive ``default_tier`` of the orgs and projects the person is currently linked to
  applies; failing that, ``need-to-know``, reported as a gap.
- An **audience** (a correspond ``Audience`` record, as JSON or a mapping) adds the readers
  it lists and, when it cannot list them all, an unlisted class at a ceiling: ``public`` →
  ``clear``; ``org`` or ``group`` → the ``clearance`` of the org or group the conversation
  belongs to, else ``clear``; ``operator`` → no ceiling; ``named`` (an email to listed
  people, a DM) → no ceiling, complete or not, as long as it lists at least one reader: a
  named audience is judged by the readers it names, so an email is not capped merely
  because forwarding makes it incomplete (liaise discussion 32, §4.4). An incomplete
  ``named`` audience that lists nobody (a Bcc-only email, recipients correspond could not
  list) → ``clear``. An unknown scope, or a ``defaulted`` record, reads as ``public``.
- ``least_clearance`` is the most restrictive clearance among all readers (tier-based,
  before project involvement); an unresolved reader counts as ``clear``. With no reader to
  hold anything back from, it is ``red``.
- ``vocabulary`` holds the terms (name, ``aka``, ``vocabulary``, id, recorded handles) of
  every record in the store that at least one reader, listed or not, is not cleared for,
  or that is sealed from a reader. ``projects`` narrows the ``entities`` report, never the
  vocabulary: a draft about one project can still name another.

Everything fails closed, and every doubt is listed under ``gaps``, never guessed:

- a tier entry, ``default_tier`` or ``clearance`` not set by the operator may restrict,
  never widen; a permissive ``default_tier`` has no ``review_by``, so it reads as lapsed
  (``need-to-know``); a link not sourced to the operator, or with a date not written
  ``YYYY-MM-DD``, gives no involvement;
- an unknown tier reads ``reviewed``, an unknown label ``red``, an unknown clearance ``clear``;
- a reader whose ``trust.yaml``, ``links.yaml`` or tier dates cannot be read is ``reviewed``;
- a record whose entry file cannot be read, or whose seal names nobody, is withheld from
  every reader (its names are then read from the raw text, as far as they can be); an
  ambiguous reader is a stranger who also counts as each candidate for seals; a seal on an
  org, group or project covers every person whose links cannot all be followed.

A caller deciding whether content may flow should not act on an answer whose
``gaps.unreadable`` or ``gaps.unresolved_seals`` is not empty without the operator: the
vocabulary of a record that cannot be read is a best effort.

>>> may_see("amber", "green"), may_see("green", "amber"), most_restrictive_reader(["amber", "clear", "green"])
(True, False, 'clear')
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any

from acquaint.lookup import find_entity, resolve_handle
from acquaint.records import disclosed_refs, normalize_newlines, parse_log, source_kind
from acquaint.store import ENTRY_FILE, AcquaintError, Entity, Store
from acquaint.trust import (
    CLEARANCE_KINDS,
    DEFAULT_TIER,
    DEFAULT_TIER_KINDS,
    LABELS,
    PERMISSIVE_TIERS,
    TIERS,
    TRUST_FILE,
    TRUST_SOURCES,
    effective_tier,
    entity_label,
    is_iso_date,
    link_state,
    tier_in_force,
)

__all__ = [
    "INVOLVED_CLEARANCE",
    "SCOPES",
    "TIER_CLEARANCE",
    "already_told",
    "disclose",
    "id_list",
    "may_see",
    "most_restrictive_reader",
    "parse_audience",
    "person_key",
]

#: What each tier may see outside the reader's own projects.
TIER_CLEARANCE = {
    "open": "amber",
    "involved": "green",
    "need-to-know": "clear",
    "reviewed": "clear",
}
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
_MOST_RESTRICTIVE_TIER = TIERS[-1]
_MOST_RESTRICTIVE_LABEL = LABELS[0]
_PERSON_KIND = "person"
_INTERACTION = "interaction"
_LINKS_FILE = "links.yaml"
_IDENTITIES_FILE = "identities.yaml"
_RAW_FIELD_RE = re.compile(r"^\s*(name|aka|vocabulary)\s*:\s*(.*)$")
_RAW_ITEM_RE = re.compile(r"^\s*-\s+(.*)$")
_BLOCK_INDICATORS = {"", "|", ">", "|-", ">-", "|+", ">+"}
#: A YAML comment: ``#`` after whitespace, to the end of the line (quotes are not tracked; a shorter term is still scanned).
_RAW_COMMENT_RE = re.compile(r"\s+#.*$")
_TIER_DATES = ("valid_from", "valid_to", "review_by")
_GAPS = (
    "unrecorded",
    "ambiguous",
    "not_a_person",
    "no_tier",
    "organisation",
    "unreadable",
    "unresolved_seals",
)


def may_see(clearance: str, label: str) -> bool:
    """Whether a reader with ``clearance`` may be told about a record labelled ``label``."""
    return LABELS.index(clearance) <= LABELS.index(label)


def most_restrictive_reader(
    clearances: Iterable[str], *, default: str = _NO_CEILING
) -> str:
    """The least clearance among readers (the one that sees least); ``default`` when there are none."""
    return max(clearances, key=LABELS.index, default=default)


# ------------------------------------------------------------------------ helpers


def _blank(value: Any) -> bool:
    return value is None or value == ""


def _dates_ok(mapping: Mapping, fields: Sequence[str]) -> bool:
    return all(_blank(mapping.get(f)) or is_iso_date(mapping.get(f)) for f in fields)


def _tier_rank(tier: str) -> int:
    return TIERS.index(tier)


def _stricter_tier(*tiers: str) -> str:
    return max(tiers, key=_tier_rank)


def _operator_sourced(value: Any) -> bool:
    return source_kind(str(value or "")) == "operator"


def _listed(value: Any) -> list:
    if _blank(value):
        return []
    return list(value) if isinstance(value, list) else [value]


def id_list(value: Any) -> list[str]:
    """Ids in a list, or in one comma-separated string (how ``sealed_from`` may be written).

    >>> id_list("ada, person:bram"), id_list(["ada"]), id_list(None)
    (['ada', 'person:bram'], ['ada'], [])
    """
    return [
        part.strip()
        for item in _listed(value)
        for part in str(item).split(",")
        if part.strip()
    ]


def _broken(entity: Entity, *files: str) -> list[str]:
    """The parse problems of these files of the entity, as ``<key>/<file>: <problem>``."""
    return [
        f"{entity.key}/{error}"
        for error in entity.errors
        if error.split(":", 1)[0] in files
    ]


def _find_key(store: Store, ref: Any) -> str | None:
    try:
        return store.find(str(ref))
    except (KeyError, AcquaintError):
        return None


def person_key(store: Store, ref: str, *, handle_prefix: bool = False) -> str | None:
    """A reference as a record key, a bare id preferring the person with that id (seals and readers name people).

    ``handle_prefix`` reads ``@bram`` as the id ``bram``: right for a seal, which only
    restricts, and wrong for a reader, where ``@bram`` on an unnamed platform need not be Bram.
    """
    ref = ref.strip()
    if handle_prefix:
        ref = ref.lstrip("@")
    elif ref.startswith("@"):
        return None
    if ":" not in ref and "/" not in ref:
        people = [k for k in store.find_id(ref) if store[k].kind == _PERSON_KIND]
        if len(people) == 1:
            return people[0]
    return _find_key(store, ref)


# --------------------------------------------------------------------- one person


def _links(store: Store, entity: Entity, today: str) -> list[tuple[Entity, bool]]:
    """``(record, trusted)`` for every link that is current or whose dates cannot be read; ``trusted`` is operator-sourced with readable dates."""
    found: dict[str, bool] = {}
    for link in entity.links:
        state = link_state(link, today=today)
        key = _find_key(store, link.get("to", ""))
        if key and state in ("current", "unreadable"):
            trusted = state == "current" and _operator_sourced(link.get("source"))
            found[key] = found.get(key, False) or trusted
    return [(store[key], trusted) for key, trusted in found.items()]


def _tier(
    entity: Entity, links: list[tuple[Entity, bool]], today: str
) -> tuple[dict[str, Any], list[str]]:
    """The tier in force today, failing closed, and what could not be read."""
    unreadable = _broken(entity, TRUST_FILE, _LINKS_FILE)
    unreadable += [
        f"{entity.key}/{TRUST_FILE}: a tier entry has a date not written YYYY-MM-DD"
        for entry in entity.trust
        if not _dates_ok(entry, _TIER_DATES)
    ][:1]
    if unreadable:
        tier = {
            "tier": _MOST_RESTRICTIVE_TIER,
            "recorded_tier": None,
            "lapsed": False,
            "review_by": None,
            "source": "unreadable records, read as reviewed",
        }
        return tier, unreadable

    sourced = [
        e
        for e in entity.trust
        if source_kind(str(e.get("source") or "")) in TRUST_SOURCES
    ]
    entry = tier_in_force(sourced, today=today)
    if entry is not None:
        value, lapsed = effective_tier(sourced, today=today)
        tier = {
            "tier": value,
            "recorded_tier": entry.get("tier"),
            "lapsed": lapsed,
            "review_by": entry.get("review_by"),
            "source": entry.get("source"),
        }
    else:
        tier = _default_tier(links)

    unsourced = tier_in_force([e for e in entity.trust if e not in sourced], today=today)
    if unsourced is not None:
        value = (
            unsourced.get("tier")
            if unsourced.get("tier") in TIERS
            else _MOST_RESTRICTIVE_TIER
        )
        if _tier_rank(value) > _tier_rank(tier["tier"]):
            tier = {
                **tier,
                "tier": value,
                "source": f"an entry not sourced to the operator ({unsourced.get('source')!r}), which can only restrict",
            }
    return tier, []


def _default_tier(links: list[tuple[Entity, bool]]) -> dict[str, Any]:
    """The most restrictive ``default_tier`` of the linked orgs and projects; a permissive one reads as lapsed."""
    defaults = []
    for other, _ in links:
        if other.kind not in DEFAULT_TIER_KINDS:
            continue
        if _broken(other, ENTRY_FILE):
            defaults.append(
                (
                    _MOST_RESTRICTIVE_TIER,
                    None,
                    False,
                    f"the unreadable entry file of {other.ref}",
                )
            )
            continue
        value = other.meta.get("default_tier")
        if _blank(value):
            continue
        value = value if value in TIERS else _MOST_RESTRICTIVE_TIER
        lapsed = value in PERMISSIVE_TIERS
        effective = _stricter_tier(value, DEFAULT_TIER) if lapsed else value
        defaults.append(
            (effective, value if lapsed else None, lapsed, f"default_tier of {other.ref}")
        )
    if not defaults:
        return {
            "tier": DEFAULT_TIER,
            "recorded_tier": None,
            "lapsed": False,
            "review_by": None,
            "source": None,
        }
    value, recorded, lapsed, source = max(
        defaults, key=lambda row: (_tier_rank(row[0]), row[3])
    )
    return {
        "tier": value,
        "recorded_tier": recorded,
        "lapsed": lapsed,
        "review_by": None,
        "source": source,
    }


def already_told(entity: Entity, *, store: Store | None = None) -> list[dict[str, str]]:
    """``{entity, date, entry}`` for every record an ``interaction`` log entry says was disclosed to this person, oldest first.

    With ``store``, each reference is written the way records link (``project:heron``) when it names a record.
    """

    def as_ref(ref: str) -> str:
        key = _find_key(store, ref) if store is not None else None
        return store[key].ref if key else ref

    told = [
        {
            "entity": as_ref(ref),
            "date": entry["date"],
            "entry": f"{log_name}#{entry['id']}",
        }
        for log_name in sorted(name for name in entity if name.startswith("log/"))
        for entry in parse_log(entity[log_name])
        if entry["kind"] == _INTERACTION
        for ref in disclosed_refs(entry.get("disclosed", ""))
    ]
    return sorted(told, key=lambda row: (row["date"], row["entry"]))


# ------------------------------------------------------------------------ readers


def _resolve_reader(store: Store, text: str) -> tuple[str | None, str | None, list[str]]:
    """``(key, None, [])`` for an exact id, reference or channel identity with a named platform; else ``(None, problem, candidate keys)``."""
    text = str(text).strip()
    key = (
        person_key(store, text)
        if ":" not in text or text.split(":", 1)[0] in {"person", "people"}
        else None
    )
    if key is None and ":" not in text and "/" not in text and not text.startswith("@"):
        candidates = store.find_id(text)
        if len(candidates) > 1:
            return None, "ambiguous", candidates
        if candidates:
            key = candidates[0]
    if key is not None:
        return key, None, []
    found = resolve_handle(store, text)
    owners = sorted({m["key"] for m in found["matches"]})
    if len(owners) == 1 and found["platform"]:
        return owners[0], None, []
    # Who it could still be: inactive and name-only owners, and anyone whose identities cannot be read.
    candidates = {
        m["key"] for m in found["matches"] + found["inactive"] + found["by_name"]
    }
    candidates |= {
        k
        for k in store
        if store[k].kind == _PERSON_KIND and _broken(store[k], _IDENTITIES_FILE)
    }
    return None, "ambiguous" if owners else "unrecorded", sorted(candidates)


def parse_audience(audience: str | Mapping | None) -> dict[str, Any] | None:
    """An audience record (a mapping, or its JSON) as ``{ref, scope, complete, readers, warnings}``, failing closed.

    ``readers`` are channel addresses (``github:octocat``), the operator's own (``is_self``)
    left out, and ``None`` for one that cannot be read (it counts as a stranger). A scope
    that is missing or unknown, and a record whose ``defaulted`` is anything but ``false``,
    read as ``public``; ``complete`` is true only when it is literally ``true``.

    >>> parse_audience('{"ref": "email:ada@example.org", "scope": "named", "complete": true, "readers": [{"channel": "email", "native_id": "ada@example.org"}]}')["readers"]
    ['email:ada@example.org']
    >>> parse_audience({"scope": "everyone", "readers": "github:octocat"})["scope"], parse_audience({"scope": "named", "readers": "x"})["readers"]
    ('public', [None])
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
        warnings.append(
            f"audience scope {scope!r} is not one of {', '.join(SCOPES)}; read as public"
        )
        scope = _UNKNOWN_SCOPE
    if audience.get("defaulted") not in (None, False):
        scope = _UNKNOWN_SCOPE
    raw = audience.get("readers")
    if not isinstance(raw, (list, tuple)):
        if not _blank(raw):
            warnings.append(
                f"audience readers should be a list, not {raw!r}; read as one unknown reader"
            )
        raw = [None] if not _blank(raw) else []
    readers: list[str | None] = []
    for reader in raw:
        if isinstance(reader, str) and reader.strip():
            readers.append(reader.strip())
        elif isinstance(reader, Mapping) and reader.get("is_self") is True:
            continue
        elif (
            isinstance(reader, Mapping)
            and reader.get("channel")
            and (reader.get("handle") or reader.get("native_id"))
        ):
            readers.append(
                f"{reader['channel']}:{reader.get('handle') or reader.get('native_id')}"
            )
        else:
            warnings.append(
                f"an audience reader that cannot be resolved counts as a stranger: {reader!r}"
            )
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
    for handle in dict.fromkeys(
        [f"{channel}:{place}", f"{channel}:{place.split('/', 1)[0]}"]
    ):
        found = resolve_handle(store, handle)
        owners = sorted(
            {
                m["key"]
                for m in found["matches"]
                if store[m["key"]].kind in CLEARANCE_KINDS
            }
        )
        if len(owners) == 1:
            return store[owners[0]]
    return None


def _ceiling(
    store: Store, audience: dict | None, gaps: dict
) -> tuple[str | None, dict | None]:
    """The clearance of the readers an audience cannot list (``None``: every reader is listed, or no audience), and what it says about the audience."""
    if audience is None:
        return None, None
    scope, complete = audience["scope"], audience["complete"]
    about: dict[str, Any] = {
        "scope": scope,
        "complete": complete,
        "ref": audience["ref"],
        "organisation": None,
    }
    ceiling: str | None = _STRANGER
    judged_by_its_readers = scope == "named" and bool(audience["readers"])
    if scope == "operator" or judged_by_its_readers or (complete and scope != "public"):
        ceiling = None
    elif scope in CLEARANCE_KINDS:
        found = _organisation(store, audience["ref"])
        if found is None:
            gaps["organisation"].append(audience["ref"] or "(no ref)")
        else:
            about["organisation"] = found.ref
            clearance = found.meta.get("clearance")
            if clearance in LABELS and _operator_sourced(found.meta.get("label_source")):
                ceiling = clearance
    about["ceiling"] = ceiling
    return ceiling, about


# ------------------------------------------------------------------------ records


def _label(entity: Entity) -> str:
    """The record's label; one not set by the operator may restrict, never widen, the kind's default."""
    label, default = entity_label(entity.meta, entity.kind), entity_label({}, entity.kind)
    if _operator_sourced(entity.meta.get("label_source")) or LABELS.index(
        label
    ) <= LABELS.index(default):
        return label
    return default


def _raw_terms(text: str) -> list[str]:
    """``name``, ``aka`` and ``vocabulary`` values read line by line from an entry file whose frontmatter does not parse.

    >>> _raw_terms('---\\nname: [Osprey\\naka: [Grey, "the fish hawk"]\\nvocabulary:\\n  - O.\\nlabel: red\\n---\\n')
    ['Osprey', 'Grey', 'the fish hawk', 'O.']
    >>> _raw_terms('---\\nname: >-\\n  Heron Initiative\\nvocabulary: ["the bird project",\\n  "H."]\\nlabel: [red\\n---\\n')
    ['Heron Initiative', 'the bird project', 'H.']
    >>> _raw_terms('---\\nname: Heron Initiative  # public name\\naka:\\n- Grey Wing\\nvocabulary: [the bird project, H.]  # codenames\\nlabel: [red\\n---\\n')
    ['Heron Initiative', 'Grey Wing', 'the bird project', 'H.']
    """
    lines = normalize_newlines(text).split("\n")
    if lines and lines[0].strip() == "---":
        lines = lines[1:]
    terms, field = [], None
    for line in lines:
        if line.strip() == "---":
            break
        line = _RAW_COMMENT_RE.sub("", line)
        found = _RAW_FIELD_RE.match(line)
        if found:
            field, value = found.group(1), found.group(2)
        elif field and (
            line[:1] in (" ", "\t") or _RAW_ITEM_RE.match(line)
        ):  # a continuation, a list item or a folded scalar's text
            value = line
        else:
            field = field if not line[:1].strip() else None
            continue
        value = _RAW_ITEM_RE.sub(r"\1", value).strip()
        if value in _BLOCK_INDICATORS:
            continue
        parts = [value] if field == "name" else value.split(",")
        terms += [part.strip().strip("[]'\" ") for part in parts]
    return [term for term in terms if term]


def _terms(entity: Entity) -> list[str]:
    """Name, aliases, vocabulary, id and recorded handles, each once (compared without case); read leniently when the entry file does not parse."""
    raw = _raw_terms(entity.text(ENTRY_FILE)) if _broken(entity, ENTRY_FILE) else []
    raw += [
        entity.name,
        *entity.aka,
        *_listed(entity.meta.get("vocabulary")),
        entity.slug,
        entity.slug.replace("-", " "),
    ]
    raw += [identity.get("value") for identity in entity.identities]
    seen: dict[str, str] = {}
    for term in raw:
        text = " ".join(str(term).split()) if term is not None else ""
        if text:
            seen.setdefault(text.lower(), text)
    return list(seen.values())


def _uncertain_links(store: Store, entity: Entity, today: str) -> bool:
    """Whether some of the person's links cannot be followed: ``links.yaml`` does not parse, or a link that may be current names no record, or several."""
    if _broken(entity, _LINKS_FILE):
        return True
    return any(
        link_state(link, today=today) != "ended"
        and _find_key(store, link.get("to", "")) is None
        for link in entity.links
    )


def _sealed(
    store: Store,
    entity: Entity,
    links_of: Mapping[str, list[tuple[Entity, bool]]],
    uncertain: set[str],
) -> tuple[set[str], list[str]]:
    """Person keys the record is sealed from, and the seal entries that name no record.

    A seal naming an org, group or project seals every person currently linked to it
    (a link's source and dates do not matter here: a seal only restricts), and every
    person in ``uncertain``, whose links cannot all be followed.
    """
    keys, unresolved = set(), []
    for ref in id_list(entity.meta.get("sealed_from")):
        key = person_key(store, ref, handle_prefix=True)
        if key is None:
            unresolved.append(ref)
        elif store[key].kind == _PERSON_KIND:
            keys.add(key)
        else:
            keys |= {
                person
                for person, links in links_of.items()
                if any(other.key == key for other, _ in links) or person in uncertain
            }
    return keys, unresolved


# ------------------------------------------------------------------------ the answer


def disclose(
    store: Store,
    people: Sequence[str] | str = (),
    *,
    projects: Sequence[str] = (),
    audience: str | Mapping | None = None,
    today: str | date | None = None,
) -> dict[str, Any]:
    """The disclosure answer for ``people`` (ids or channel identities) and an optional ``audience``.

    ``projects`` (exact ids, never people) limits the ``entities`` report to those records
    plus every person. See the module docstring for the rules.
    """
    today = str(today) if today else date.today().isoformat()
    people = [people] if isinstance(people, str) else list(people)
    parsed = parse_audience(audience)
    if not people and parsed is None:
        raise AcquaintError("name at least one reader, or give an audience")
    report_keys = []
    for project in projects:
        key = find_entity(store, project, names=False)
        if store[key].kind == _PERSON_KIND:
            raise AcquaintError(
                f"{project!r} is a person, not a project: name readers before --project"
            )
        report_keys.append(key)

    gaps: dict[str, list[str]] = {name: [] for name in _GAPS}
    all_keys = list(store)
    person_keys = [k for k in all_keys if store[k].kind == _PERSON_KIND]
    links_of = {k: _links(store, store[k], today) for k in person_keys}
    uncertain = {k for k in person_keys if _uncertain_links(store, store[k], today)}
    readers: dict[str, dict[str, Any]] = {}  # store key -> the person's answer
    strangers: list[
        list[str]
    ] = []  # readers with no single person record: their candidate keys

    def add_reader(text: str | None, via: str) -> None:
        key, problem, candidates = (
            _resolve_reader(store, text) if text is not None else (None, None, [])
        )
        if key is None:
            if problem:
                gaps[problem].append(text)
            strangers.append(candidates)
            return
        entity = store[key]
        if entity.kind != _PERSON_KIND:
            gaps["not_a_person"].append(f"{text} ({entity.ref})")
            strangers.append([key])
            return
        if key in readers:
            return
        tier, unreadable = _tier(entity, links_of[key], today)
        gaps["unreadable"] += unreadable
        if tier["source"] is None:
            gaps["no_tier"].append(entity.slug)
        readers[key] = {
            **tier,
            "clearance": TIER_CLEARANCE[tier["tier"]],
            "involved_in": []
            if unreadable
            else [
                o.ref for o, trusted in links_of[key] if trusted and o.kind == "project"
            ],
            "already_told": already_told(entity, store=store),
            "via": via,
        }

    for person in people:
        add_reader(person, "named")
    for address in (parsed or {}).get("readers", []):
        add_reader(address, "audience")
    ceiling, about = _ceiling(store, parsed, gaps)

    unlisted = [_STRANGER] * len(strangers) + ([ceiling] if ceiling else [])
    least = most_restrictive_reader([r["clearance"] for r in readers.values()] + unlisted)
    stranger_candidates = {k for candidates in strangers for k in candidates}

    report = set(report_keys + person_keys) if projects else set(all_keys)
    entities, seals, vocabulary = {}, [], []
    for key in all_keys:
        entity = store[key]
        unreadable = _broken(entity, ENTRY_FILE)
        gaps["unreadable"] += unreadable
        sealed_keys, unresolved = _sealed(store, entity, links_of, uncertain)
        gaps["unresolved_seals"] += [f"{entity.ref}: {ref}" for ref in unresolved]
        withheld = bool(unreadable or unresolved)  # nobody can be shown to be cleared
        label = _MOST_RESTRICTIVE_LABEL if unreadable else _label(entity)
        cleared, not_cleared, sealed = [], [], []
        for reader_key, reader in readers.items():
            slug = store[reader_key].slug
            if reader_key in sealed_keys:
                sealed.append(slug)
                not_cleared.append(slug)
            elif not withheld and (
                reader_key == key
                or entity.ref in reader["involved_in"]
                or may_see(reader["clearance"], label)
            ):
                cleared.append(slug)
            else:
                not_cleared.append(slug)
        above_unlisted = (
            withheld
            or bool(sealed_keys & stranger_candidates)
            or any(not may_see(c, label) for c in unlisted)
        )
        seals += [{"entity": entity.ref, "from": slug} for slug in sealed]
        if key in report:
            entities[entity.ref] = {
                "label": label,
                "cleared": cleared,
                "not_cleared": not_cleared,
                "sealed_from": sorted(store[k].slug for k in sealed_keys),
                "above_unlisted_readers": above_unlisted,
            }
        if not_cleared or above_unlisted:
            vocabulary += [
                {
                    "term": term,
                    "entity": entity.ref,
                    "label": label,
                    "sealed_from": sealed,
                }
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
        "gaps": {name: list(dict.fromkeys(values)) for name, values in gaps.items()},
        "warnings": (parsed or {}).get("warnings", []),
    }
