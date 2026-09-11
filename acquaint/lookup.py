"""Finding the right record: name matching, handle resolution, the conflation check, and channel choice.

All functions take a :class:`~acquaint.store.Store` (any mapping of entities) and
return plain data. Matching is deterministic normalisation: case, punctuation and
accents are ignored, and every candidate is returned so callers can refuse to guess.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from acquaint.records import load_yaml
from acquaint.store import Entity

__all__ = ["match", "normalize", "resolve_handle", "check_text", "reach_channels", "TIERS"]

#: Who set a rule, most authoritative first. The operator's instruction for the
#: message at hand outranks all of these; it belongs to the caller, not the store.
TIERS = ("self", "operator", "affiliation", "observed", "default")
_INACTIVE = {"superseded", "retracted", "expired"}
_SPLIT_HINT = re.compile(r"^\W*(or|and|aka|a\.k\.a\.?|vs\.?|/|,|&|\+)\W*$", re.I)
_NAME_LIKE = re.compile(r"\b[A-Z][a-z]+(?:[ '-][A-Z][a-z]+)+\b")
_SENTENCE_STARTERS = {
    "The", "This", "That", "These", "Those", "When", "Where", "What", "Why", "How",
    "If", "In", "On", "At", "For", "And", "But", "So", "Dear", "Hi", "Hello", "Thanks",
}


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", folded.lower())


def _emails(entity: Entity) -> list[str]:
    return [str(i["value"]) for i in entity.identities if i.get("platform") == "email" and i.get("value")]


def _forms(entity: Entity) -> set[str]:
    forms = {normalize(f) for f in entity.surface_forms}
    for email in _emails(entity):
        forms |= {normalize(email), normalize(email.split("@")[0])}
    return {f for f in forms if f}


# -------------------------------------------------------------------------- match


def match(store: Mapping[str, Entity], query: str) -> dict[str, list[str]]:
    """Store keys matching a name, alias, handle, email or id: ``{"exact": [...], "partial": [...]}``.

    ``partial`` holds entities where the query is part of a longer form (at least
    three characters), for "did you mean" rather than for acting on.
    """
    q = normalize(query)
    exact, partial = [], []
    if not q:
        return {"exact": exact, "partial": partial}
    for key in store:
        forms = _forms(store[key])
        if q in forms or q == normalize(key.split("/", 1)[1]):
            exact.append(key)
        elif len(q) >= 3 and any(q in form for form in forms):
            partial.append(key)
    return {"exact": exact, "partial": partial}


# ------------------------------------------------------------------------ handles


def _normalise_handle(platform: str | None, value: str) -> str:
    value = value.strip()
    if platform == "email" or (platform is None and re.fullmatch(r"[^@\s]+@[^@\s]+", value)):
        local, _, domain = value.lower().partition("@")
        if domain in {"gmail.com", "googlemail.com"}:
            local = local.split("+", 1)[0].replace(".", "")
        return f"{local}@{domain}"
    return value.lstrip("@").lower()


def _split_handle(handle: str) -> tuple[str | None, str]:
    handle = handle.strip()
    if re.fullmatch(r"[a-z][a-z0-9_-]*:[^/].*", handle) and not handle.startswith(("http:", "https:")):
        platform, _, value = handle.partition(":")
        return platform.lower(), value
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", handle):
        return "email", handle
    return None, handle


def resolve_handle(store: Mapping[str, Entity], handle: str) -> list[dict[str, Any]]:
    """Entities a channel handle belongs to, strongest evidence first.

    ``github:octocat``, ``email:ada@example.org``, ``ada@example.org`` and ``@octocat``
    are matched against ``identities.yaml`` (Gmail dots and ``+tags`` ignored). A
    handle found in no identity file falls back to name matching, reported as
    ``evidence: name only``, which is never enough to act on alone.
    """
    platform, value = _split_handle(handle)
    wanted = _normalise_handle(platform, value)
    found = []
    for key in store:
        entity = store[key]
        for identity in entity.identities:
            if platform and str(identity.get("platform", "")).lower() != platform:
                continue
            if _normalise_handle(identity.get("platform"), str(identity.get("value", ""))) != wanted:
                continue
            found.append(
                {
                    "id": entity.slug,
                    "key": key,
                    "name": entity.name,
                    "platform": identity.get("platform"),
                    "value": identity.get("value"),
                    "evidence": identity.get("evidence") or identity.get("source") or "unrecorded",
                    "status": identity.get("status", "active"),
                }
            )
    if found or platform:
        return found
    names = match(store, value)
    return [
        {"id": store[key].slug, "key": key, "name": store[key].name, "evidence": "name only"}
        for key in names["exact"]
    ]


# -------------------------------------------------------------------- conflations


def check_text(store: Mapping[str, Entity], text: str) -> dict[str, Any]:
    """Scan prose for people errors before it is published.

    Reports the entities mentioned; **conflations** (one entity written as if it were
    two: two different names for it joined by "or", "and", "/", "," …); **ambiguous**
    names (one form shared by several entities); and **unknown** name-like phrases
    that match nobody, which are either a new person to add or a misspelling.
    """
    hits: dict[str, list[tuple[int, str]]] = {}
    owners: dict[str, set[str]] = {}
    for key in store:
        entity = store[key]
        for form in entity.surface_forms:
            if len(form) < 3:
                continue
            for found in re.finditer(rf"(?<![\w@]){re.escape(form)}(?!\w)", text, re.I):
                hits.setdefault(key, []).append((found.start(), found.group(0)))
                owners.setdefault(normalize(found.group(0)), set()).add(key)

    conflations = []
    for key, spans in hits.items():
        spans = sorted(set(spans))
        for (p1, s1), (p2, s2) in zip(spans, spans[1:]):
            if normalize(s1) == normalize(s2) or p2 < p1 + len(s1):
                continue
            between = text[p1 + len(s1) : p2]
            if len(between) <= 12 and _SPLIT_HINT.match(between):
                conflations.append(
                    {
                        "id": store[key].slug,
                        "name": store[key].name,
                        "forms": [s1, s2],
                        "excerpt": text[max(0, p1 - 30) : p2 + len(s2) + 30].strip(),
                    }
                )

    ambiguous = [
        {"form": form, "ids": sorted(store[k].slug for k in keys)}
        for form, keys in sorted(owners.items())
        if len(keys) > 1
    ]
    known = {f for key in store for f in _forms(store[key])}
    unknown = sorted(
        {
            phrase
            for phrase in _NAME_LIKE.findall(text)
            if phrase.split()[0] not in _SENTENCE_STARTERS
            and not any(normalize(word) in known for word in re.split(r"[ '-]", phrase))
        }
    )
    return {
        "mentioned": sorted(store[key].slug for key in hits),
        "conflations": conflations,
        "ambiguous": ambiguous,
        "unknown_candidates": unknown,
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
            actual = context.get(condition)
        if actual is None:
            return None
        allowed = expected if isinstance(expected, list) else [expected]
        if str(actual).lower() not in {str(a).lower() for a in allowed}:
            return None
    return len(when)


def _tier_of(rule: dict, default: str) -> str:
    setter = str(rule.get("set_by") or rule.get("authority") or default).lower()
    return {"self-stated": "self", "person": "self"}.get(setter, setter if setter in TIERS else default)


def reach_channels(
    store: Mapping[str, Entity],
    key: str,
    *,
    defaults_text: str = "",
    **context: str | None,
) -> dict[str, Any]:
    """Ordered channels for reaching one entity in a context (``purpose``, ``urgency``, ``project``, ``message_type``, ``topic``).

    Precedence: the person's own stated rules > the operator's rules about them >
    norms of a project or affiliation > observed habits > global defaults. Within a
    tier the most specific matching rule wins. It returns addresses; it sends nothing.
    """
    context = {k: str(v) for k, v in context.items() if v}
    entity = store[key]
    candidates: list[tuple[str, dict, str]] = [
        (_tier_of(rule, "operator"), rule, f"{key}/rules.yaml") for rule in entity.rules
    ]
    affiliations = [str(link.get("to", "")) for link in entity.links]
    if context.get("project"):
        affiliations.append(f"project:{context['project']}")
    for ref in dict.fromkeys(affiliations):
        try:
            other = store[_ref_key(store, ref)]
        except KeyError:
            continue
        candidates += [(("affiliation"), rule, f"{other.key}/rules.yaml") for rule in other.rules]
    defaults, _ = load_yaml(defaults_text) if defaults_text else ({}, [])
    for rule in (defaults or {}).get("rules", []) if isinstance(defaults, dict) else []:
        candidates.append(("default", rule, "_defaults/rules.yaml"))

    scored = []
    for order, (tier, rule, origin) in enumerate(candidates):
        if str(rule.get("status", "active")).lower() in _INACTIVE:
            continue
        specificity = _matches(rule.get("when"), context)
        if specificity is not None:
            scored.append((TIERS.index(tier), -specificity, order, tier, rule, origin))
    scored.sort(key=lambda item: item[:3])

    channels, seen = [], set()
    for _, _, _, tier, rule, origin in scored:
        do = rule.get("do", {})
        wanted = [do.get("channel"), *_as_list(do.get("fallback"))] if isinstance(do, dict) else [None]
        for channel in wanted:
            label = channel or str(do)
            if label in seen:
                continue
            seen.add(label)
            channels.append(
                {
                    "channel": channel,
                    "address": _address(entity, channel),
                    "tier": tier,
                    "instruction": None if isinstance(do, dict) else str(do),
                    "rule_from": origin,
                    "source": rule.get("source"),
                }
            )
    if not channels:
        channels = [
            {
                "channel": identity.get("platform"),
                "address": f"{identity.get('platform')}:{identity.get('value')}",
                "tier": "none",
                "instruction": "no rule matched; identities in the order listed",
                "rule_from": f"{key}/identities.yaml",
                "source": identity.get("source"),
            }
            for identity in entity.identities
            if str(identity.get("status", "active")).lower() == "active"
        ]
    return {"context": context, "channels": channels, "rules_matched": len(scored)}


def _ref_key(store: Mapping[str, Entity], ref: str) -> str:
    find = getattr(store, "find", None)
    if find is None:
        raise KeyError(ref)
    return find(ref)


def _address(entity: Entity, channel: str | None) -> str | None:
    if not channel:
        return None
    for identity in entity.identities:
        if str(identity.get("platform", "")).lower() == channel.lower():
            return f"{identity['platform']}:{identity.get('value')}"
    return None


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]
