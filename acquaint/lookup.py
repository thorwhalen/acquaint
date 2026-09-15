"""Finding the right record: exact references, handle resolution, the conflation check, and channel choice.

All functions take a :class:`~acquaint.store.Store` and return plain data. Matching is
deterministic normalisation (case, punctuation and accents ignored). Nothing here acts
on a partial match or picks between candidates: an id and another record's exact alias
compete on equal terms, partials are offered as suggestions, and :func:`find_entity`
refuses when more than one record fits. One unreadable record is reported and skipped;
it never takes a lookup down.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from acquaint.records import load_yaml
from acquaint.store import AcquaintError, Entity, Store

__all__ = [
    "INACTIVE_RULES",
    "TIERS",
    "USABLE_STATUSES",
    "check_text",
    "find_entity",
    "match",
    "normalise_handle",
    "normalize",
    "reach_channels",
    "resolve_handle",
]

#: Who set a rule, most authoritative first. The operator's instruction for the message
#: at hand outranks all of these; it belongs to the caller, not the store.
TIERS = ("self", "operator", "affiliation", "observed", "default")
#: An identity is usable only with one of these statuses (none recorded means active).
#: Anything else (stale, former, unverified, retracted, dead, …) is reported, never acted on.
USABLE_STATUSES = {"active", "relay"}
#: A rule is out of use with one of these statuses.
INACTIVE_RULES = {"superseded", "retracted", "expired", "dead", "draft"}
_SPLIT_HINT = re.compile(r"^\W*(or|and|aka|a\.k\.a\.?|vs\.?|/|,|&|\+)\W*$", re.I)
_NAME_LIKE = re.compile(r"\b[A-Z][a-z]+(?:[ '-][A-Z][a-z]+)+\b")
_SENTENCE_STARTERS = {
    "The",
    "This",
    "That",
    "These",
    "Those",
    "When",
    "Where",
    "What",
    "Why",
    "How",
    "If",
    "In",
    "On",
    "At",
    "For",
    "And",
    "But",
    "So",
    "Dear",
    "Hi",
    "Hello",
    "Thanks",
    "As",
    "See",
}


def normalize(text: str) -> str:
    """Lowercase ASCII letters and digits only, for comparing names and handles.

    >>> normalize("Zoë O'Example")
    'zoeoexample'
    """
    folded = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", folded.lower())


def _status(item: dict) -> str:
    return str(item.get("status") or "active").strip().lower()


def _forms(entity: Entity) -> set[str]:
    forms = {normalize(f) for f in entity.surface_forms}
    for identity in entity.identities:
        if identity.get("platform") == "email" and identity.get("value"):
            email = str(identity["value"])
            forms |= {normalize(email), normalize(email.split("@")[0])}
    return {f for f in forms if f}


def _readable(store: Store) -> tuple[dict[str, Entity], list[dict]]:
    """Entities whose identity can be read, and ``{key, error}`` for those that cannot."""
    good, broken = {}, []
    for key in store:
        try:
            entity = Entity(store, key)
            _forms(entity)
            good[key] = entity
        except (
            Exception
        ) as error:  # one bad record must not take down every lookup; it is reported
            broken.append({"key": key, "error": f"{type(error).__name__}: {error}"})
    return good, broken


# -------------------------------------------------------------------------- match


def match(store: Store, query: str) -> dict[str, list]:
    """Store keys matching a name, alias, handle, email or id: ``{"exact": [...], "partial": [...], "unreadable": [...]}``.

    ``partial`` holds entities where the query is part of a longer form (three characters
    or more): suggestions for a person, never something to act on.
    """
    q = normalize(query)
    entities, broken = _readable(store)
    exact, partial = [], []
    if q:
        for key, entity in entities.items():
            forms = _forms(entity)
            if q in forms or q == normalize(entity.slug):
                exact.append(key)
            elif len(q) >= 3 and any(q in form for form in forms):
                partial.append(key)
    return {"exact": exact, "partial": partial, "unreadable": broken}


def find_entity(store: Store, ref: str, *, names: bool = True) -> str:
    """The one store key a reference names, or an :class:`AcquaintError` saying why not.

    ``person:ada-lovelace`` and ``people/ada-lovelace`` are exact and decide on their own.
    A bare word is looked up as an id (in any kind, any case) and, with ``names``, as an
    exact name, alias, handle or email; it resolves only when exactly one record fits all
    of these together. A partial match never counts; it is offered as a suggestion.
    Operations that rewrite or remove records pass ``names=False`` and need the id.
    """
    text = ref.strip()
    if ":" in text or "/" in text:
        try:
            return store.find(text)
        except KeyError:
            raise AcquaintError(f"no entity {ref!r}") from None
    by_id = store.find_id(text)
    found = match(store, text)
    candidates = list(dict.fromkeys(by_id + (found["exact"] if names else [])))
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        raise AcquaintError(
            f"{ref!r} could be {', '.join(candidates)}; say which with its kind and id, e.g. {Entity(store, candidates[0]).ref}"
        )
    suggestions = [
        k.split("/", 1)[1] for k in dict.fromkeys(found["exact"] + found["partial"])
    ]
    hint = f"; did you mean {', '.join(suggestions)}?" if suggestions else ""
    if names:
        raise AcquaintError(f"no entity named {ref!r}{hint}")
    raise AcquaintError(f"no entity with the id {ref!r} (this needs the exact id){hint}")


# ------------------------------------------------------------------------ handles


def normalise_handle(platform: str | None, value: str) -> str:
    """A handle's comparable form: an email lowercased, with Gmail dots and ``+tags`` folded; any other value lowercased, without a leading ``@``."""
    value = value.strip()
    if platform == "email" or (
        platform is None and re.fullmatch(r"[^@\s]+@[^@\s]+", value)
    ):
        local, _, domain = value.lower().partition("@")
        if domain in {"gmail.com", "googlemail.com"}:
            local = local.split("+", 1)[0].replace(".", "")
        return f"{local}@{domain}"
    return value.lstrip("@").lower()


def _split_handle(handle: str) -> tuple[str | None, str]:
    handle = handle.strip()
    if re.fullmatch(r"[a-z][a-z0-9_-]*:[^/].*", handle) and not handle.startswith(
        ("http:", "https:")
    ):
        platform, _, value = handle.partition(":")
        return platform.lower(), value
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", handle):
        return "email", handle
    return None, handle


def resolve_handle(store: Store, handle: str) -> dict[str, Any]:
    """Who a channel handle belongs to, with the evidence: ``{"platform", "matches", "inactive", "by_name", "unreadable"}``.

    ``github:octocat``, ``email:ada@example.org`` and ``ada@example.org`` name a platform;
    ``@octocat`` does not, so it matches that handle on any platform. Only identities with
    a usable status (see :data:`USABLE_STATUSES`) are matches; the rest are reported under
    ``inactive`` with their status. A handle found in no identity file is matched against
    names under ``by_name``, which is never enough to act on.
    """
    platform, value = _split_handle(handle)
    wanted = normalise_handle(platform, value)
    entities, broken = _readable(store)
    matches, inactive = [], []
    for key, entity in entities.items():
        for identity in entity.identities:
            if platform and str(identity.get("platform", "")).lower() != platform:
                continue
            if (
                normalise_handle(identity.get("platform"), str(identity.get("value", "")))
                != wanted
            ):
                continue
            row = {
                "id": entity.slug,
                "key": key,
                "name": entity.name,
                "platform": identity.get("platform"),
                "value": identity.get("value"),
                "evidence": identity.get("evidence")
                or identity.get("source")
                or "unrecorded",
                "status": _status(identity),
            }
            (matches if row["status"] in USABLE_STATUSES else inactive).append(row)
    by_name = []
    if not matches and not inactive and platform is None:
        names = match(store, value)
        by_name = [
            {
                "id": entities[k].slug,
                "key": k,
                "name": entities[k].name,
                "evidence": "name only",
            }
            for k in names["exact"]
            if k in entities
        ]
    return {
        "platform": platform,
        "matches": matches,
        "inactive": inactive,
        "by_name": by_name,
        "unreadable": broken,
    }


# -------------------------------------------------------------------- conflations


def _is_citation(entity: Entity, first: str, second: str, between: str) -> bool:
    """``Lovelace, Ada``: family name, comma, given name, which is one person in citation order."""
    parts = entity.name.split()
    return (
        between.strip() == ","
        and len(parts) > 1
        and normalize(first) == normalize(parts[-1])
        and normalize(second) == normalize(parts[0])
    )


def check_text(store: Store, text: str) -> dict[str, Any]:
    """Scan prose for people errors before it is published.

    Reports the entities mentioned; **conflations** (one entity written as if it were two:
    two different names for it joined by "or", "and", "/", "," …, citation order such as
    "Lovelace, Ada" excepted); **ambiguous** forms shared by several entities; and
    **unknown** name-like phrases that match nobody.
    """
    entities, broken = _readable(store)
    hits: dict[str, list[tuple[int, str]]] = {}
    owners: dict[str, set[str]] = {}
    for key, entity in entities.items():
        for form in entity.surface_forms:
            if len(form) < 3:
                continue
            for found in re.finditer(rf"(?<![\w@]){re.escape(form)}(?!\w)", text, re.I):
                hits.setdefault(key, []).append((found.start(), found.group(0)))
                owners.setdefault(normalize(found.group(0)), set()).add(key)

    conflations = []
    for key, spans in hits.items():
        entity = entities[key]
        spans = sorted(set(spans))
        for (p1, s1), (p2, s2) in zip(spans, spans[1:]):
            if normalize(s1) == normalize(s2) or p2 < p1 + len(s1):
                continue
            between = text[p1 + len(s1) : p2]
            if (
                len(between) <= 12
                and _SPLIT_HINT.match(between)
                and not _is_citation(entity, s1, s2, between)
            ):
                conflations.append(
                    {
                        "id": entity.slug,
                        "name": entity.name,
                        "forms": [s1, s2],
                        "excerpt": text[max(0, p1 - 30) : p2 + len(s2) + 30].strip(),
                    }
                )

    ambiguous = [
        {"form": form, "ids": sorted(entities[k].slug for k in keys)}
        for form, keys in sorted(owners.items())
        if len(keys) > 1
    ]
    known = {f for entity in entities.values() for f in _forms(entity)}
    unknown = sorted(
        {
            phrase
            for phrase in _NAME_LIKE.findall(text)
            if phrase.split()[0] not in _SENTENCE_STARTERS
            and not any(normalize(word) in known for word in re.split(r"[ '-]", phrase))
        }
    )
    return {
        "mentioned": sorted(entities[key].slug for key in hits),
        "conflations": conflations,
        "ambiguous": ambiguous,
        "unknown_candidates": unknown,
        "unreadable": broken,
    }


# -------------------------------------------------------------------------- reach


def _matches(when: Any, context: dict[str, str]) -> int | None:
    """How specific a matching ``when`` is (number of conditions), or ``None`` if it does not match."""
    if not when:
        return 0
    if not isinstance(when, dict):
        return None
    for condition, expected in when.items():
        if condition == "affiliation":
            kind, _, slug = str(expected).partition(":")
            actual = context.get(kind) if slug else None
            expected = slug or expected
        else:
            actual = context.get(str(condition))
        if actual is None:
            return None
        allowed = expected if isinstance(expected, list) else [expected]
        if str(actual).lower() not in {str(a).lower() for a in allowed}:
            return None
    return len(when)


def _tier_of(rule: dict, default: str) -> str:
    setter = str(rule.get("set_by") or rule.get("authority") or default).lower()
    return {"self-stated": "self", "person": "self"}.get(
        setter, setter if setter in TIERS else default
    )


def _usable_identities(entity: Entity) -> list[dict]:
    return [
        i
        for i in entity.identities
        if _status(i) in USABLE_STATUSES
        and i.get("platform")
        and i.get("value") is not None
    ]


def _address(entity: Entity, channel: str) -> tuple[str | None, str | None]:
    """A usable address for a channel, or ``None`` and why."""
    recorded = [
        i
        for i in entity.identities
        if str(i.get("platform", "")).lower() == channel.lower()
    ]
    usable = [i for i in recorded if _status(i) in USABLE_STATUSES]
    if usable:
        return f"{usable[0]['platform']}:{usable[0].get('value')}", None
    if recorded:
        return (
            None,
            f"no usable {channel} address (the recorded one is {_status(recorded[0])})",
        )
    return None, f"no {channel} address recorded"


#: What a channel entry is called when its rule named none, so no repr stands in for one.
NO_CHANNEL_NAMED = "(no channel named)"


def _fallback_entry(value: Any) -> tuple[str | None, str | None]:
    """One ``fallback`` entry, as ``(channel, stated address)``.

    A plain string names a channel and states no address. A mapping states one:
    ``{"channel": "webinbox", "address": "webinbox:heron"}``. Anything else is neither.
    """
    if isinstance(value, str) and value.strip():
        return value.strip(), None
    if isinstance(value, dict):
        channel, address = value.get("channel"), value.get("address")
        if isinstance(channel, str) and channel.strip():
            return channel.strip(), _text(address)
    return None, None


def _text(value: Any) -> str | None:
    """``value`` stripped when it is a non-empty string, else ``None``."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def _channels_of(do: Any) -> tuple[list[tuple[str, str | None]], list[str]]:
    """The channels a rule's ``do`` asks for, in order, each with the address it states, and notes about values that are not channels.

    ``do.channel`` is a channel *name* and ``do.address`` states where that channel goes;
    a ``fallback`` entry is a name, or a mapping stating its own address. A stated address
    is returned as written, so it may be any reference the channel takes, not only one
    built from an identity. There is one way to write each of those, so a mapping given as
    ``do.channel`` is not a channel and is reported as such.
    """
    if not isinstance(do, dict):
        return [], []
    entries, notes = [], []
    primary = _text(do.get("channel"))
    if primary is not None:
        entries.append((primary, _text(do.get("address"))))
    elif do.get("channel") is not None:
        notes.append(f"ignored {do.get('channel')!r}: a channel is a name such as email")
    for value in _as_list(do.get("fallback")):
        if value is None:
            continue
        channel, stated = _fallback_entry(value)
        if channel is None:
            notes.append(f"ignored {value!r}: a channel is a name such as email")
            continue
        entries.append((channel, stated))
    return entries, notes


def reach_channels(
    store: Store, key: str, *, defaults_text: str = "", **context: str | None
) -> dict[str, Any]:
    """Ordered channels for reaching one entity in a context (``purpose``, ``urgency``, ``project``, ``message_type``, ``topic``).

    Precedence: the person's own stated rules > the operator's rules about them > norms of
    a project or affiliation > observed habits > global defaults. Within a tier the most
    specific matching rule wins. Only usable addresses are offered; a rule value that is
    not a channel name is skipped with a note. It returns addresses; it sends nothing.

    Each channel carries ``address_kind``: ``stated`` when a rule gave the address,
    ``identity`` when it was built from one of the entity's identities, ``None`` when
    there is no address. The distinction matters because an identity-built address is a
    *handle* (``github:ada``), and a channel addressed by conversation rather than by
    person (GitHub, a web inbox, a chat channel) does not take one. Such a channel's rule
    states its address.

    A channel's **position** is decided by the best-placed rule that names it; its
    **address** by the best-placed rule that states one, which may be a different rule. A
    rule that names a channel without stating an address expresses no opinion about where
    that channel goes, so it does not bury an address a lower-placed rule states; the note
    says which rule file the address came from when the two differ.
    """
    context = {k: str(v) for k, v in context.items() if v}
    entity = store[key]
    candidates: list[tuple[str, dict, str]] = [
        (_tier_of(rule, "operator"), rule, f"{key}/rules.yaml") for rule in entity.rules
    ]
    # The project the caller named comes before the entity's other affiliations: its rules
    # are about the message at hand, and every affiliation shares one tier, so whichever is
    # consulted first wins a tie. Without this, asking about one project can answer with
    # another project's rule.
    affiliations = [f"project:{context['project']}"] if context.get("project") else []
    affiliations += [str(link.get("to", "")) for link in entity.links]
    for ref in dict.fromkeys(affiliations):
        try:
            other = store[store.find(ref)]
        except (KeyError, AcquaintError):
            continue
        candidates += [
            ("affiliation", rule, f"{other.key}/rules.yaml") for rule in other.rules
        ]
    defaults, _ = load_yaml(defaults_text) if defaults_text else ({}, [])
    for rule in (defaults or {}).get("rules", []) if isinstance(defaults, dict) else []:
        if isinstance(rule, dict):
            candidates.append(("default", rule, "_defaults/rules.yaml"))

    scored = []
    for order, (tier, rule, origin) in enumerate(candidates):
        if _status(rule) in INACTIVE_RULES:
            continue
        specificity = _matches(rule.get("when"), context)
        if specificity is not None:
            scored.append((TIERS.index(tier), -specificity, order, tier, rule, origin))
    scored.sort(key=lambda item: item[:3])

    # A channel's position is the best-placed rule that names it. Its address is the
    # best-placed rule that *states* one, which is not always the same rule: a broad rule
    # naming a channel says nothing about where that channel goes, so it must not bury the
    # address a narrower one gives. Collected in one pass, best first.
    stated_addresses: dict[str, tuple[str, str, int]] = {}
    for rank, (_, _, _, _, rule, origin) in enumerate(scored):
        for channel, stated in _channels_of(rule.get("do", {}))[0]:
            if stated is not None:
                stated_addresses.setdefault(channel, (stated, origin, rank))

    channels, seen = [], set()
    for rank, (_, _, _, tier, rule, origin) in enumerate(scored):
        do = rule.get("do", {})
        named, notes = _channels_of(do)
        entries: list[tuple[str | None, str | None]] = [
            (channel, None) for channel, _ in named
        ]
        if not entries and not isinstance(do, dict) and do not in (None, ""):
            # Free text: a `do` that is prose, not a channel. A mapping is never prose —
            # its repr is not an instruction anyone can act on, so a mapping that names no
            # channel is reported through its notes instead, below.
            entries = [(None, str(do))]
        elif not entries and notes:
            entries = [(None, None)]
        for channel, instruction in entries:
            if channel:
                label: tuple[str, str] = ("channel", channel)
            elif instruction:
                label = ("instruction", instruction)
            else:
                label = ("notes", "; ".join(notes))
            if label in seen:
                continue
            seen.add(label)
            stated = stated_addresses.get(channel) if channel else None
            if stated is not None:
                address, note, kind = stated[0], None, "stated"
                # The address may come from a different rule than the channel choice.
                if stated[2] != rank:
                    note = f"address stated by another rule in {stated[1]}"
            elif channel:
                address, note = _address(entity, channel)
                kind = "identity" if address else None
            else:
                address, note, kind = None, None, None
            channels.append(
                {
                    "channel": channel,
                    "address": address,
                    "address_kind": kind,
                    "note": "; ".join(filter(None, [note, *notes])) or None,
                    "tier": tier,
                    "instruction": instruction,
                    "rule_from": origin,
                    "source": rule.get("source"),
                }
            )
    if not channels:
        channels = [
            {
                "channel": identity.get("platform"),
                "address": f"{identity.get('platform')}:{identity.get('value')}",
                "address_kind": "identity",
                "note": None,
                "tier": "none",
                "instruction": "no rule matched; usable identities in the order listed",
                "rule_from": f"{key}/identities.yaml",
                "source": identity.get("source"),
            }
            for identity in _usable_identities(entity)
        ]
    return {"context": context, "channels": channels, "rules_matched": len(scored)}


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]
