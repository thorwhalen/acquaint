"""The disclosure vocabulary: tiers on people; labels, seals and clearances on records; and which tier is in force.

What a reader may be told is decided by the operator and evaluated by code, so its words
are fixed here and nowhere else. Where they are written:

- ``trust.yaml`` beside a person's entry file:
  ``{tiers: [{tier, valid_from, valid_to, review_by, recorded, source, note}]}``;
- any record's frontmatter: ``label``, ``sealed_from``, ``vocabulary``, ``clearance`` (orgs
  and groups), ``default_tier`` (orgs and projects), and ``label_source``;
- one fact line: ``[label: …]`` and ``[sealed-from: …]`` beside its ``[source: …]``.

A tier records a disclosure consequence, never a judgement of the person. Only the
operator grants one. Nothing here reads a store: these are pure functions over parsed
records, and :mod:`acquaint.lint` says what is wrong with them.

>>> tiers = [
...     {"tier": "reviewed", "valid_from": "2026-01-01", "valid_to": "2026-09-01", "source": "operator"},
...     {"tier": "open", "valid_from": "2026-09-01", "review_by": "2026-11-01", "source": "operator"},
... ]
>>> tier_in_force(tiers, today="2026-09-15")["tier"], effective_tier(tiers, today="2026-09-15")
('open', ('open', False))
>>> effective_tier(tiers, today="2026-11-02")
('need-to-know', True)
>>> entity_label({}, "project"), entity_label({}, "person"), entity_label({"label": "red"}, "person")
('amber', 'green', 'red')
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from acquaint.records import fact_tags

__all__ = [
    "CLEARANCE_KINDS",
    "DEFAULT_TIER",
    "DEFAULT_TIER_KINDS",
    "LABELS",
    "OPERATOR_SET_FIELDS",
    "PERMISSIVE_TIERS",
    "TIERS",
    "TRUST_FILE",
    "TRUST_SOURCES",
    "effective_tier",
    "entity_label",
    "fact_label",
    "is_lapsed",
    "tier_in_force",
]

TRUST_FILE = "trust.yaml"
#: One ordinal scale, most permissive first.
TIERS = ("open", "involved", "need-to-know", "reviewed")
#: The tiers that need a ``review_by`` and lapse to :data:`DEFAULT_TIER` once it passes.
PERMISSIVE_TIERS = ("open", "involved")
#: The tier of anyone without one in force.
DEFAULT_TIER = "need-to-know"
#: What an unknown tier value is read as: fail closed.
_UNKNOWN_TIER = "reviewed"
#: Traffic Light Protocol names, most restrictive first. Also the clearance values.
LABELS = ("red", "amber", "green", "clear")
_DEFAULT_LABELS = {"person": "green"}
_DEFAULT_LABEL = "amber"
#: What an unknown or malformed label is read as: fail closed.
_UNKNOWN_LABEL = "red"
#: The only sources a tier may have: the operator, or the person's own quoted words.
TRUST_SOURCES = ("operator", "self")
#: Frontmatter fields that need ``label_source: operator``.
OPERATOR_SET_FIELDS = ("label", "sealed_from", "clearance", "default_tier")
CLEARANCE_KINDS = ("org", "group")
DEFAULT_TIER_KINDS = ("org", "project")


def _blank(value: Any) -> bool:
    return value is None or value == ""


def _covers(entry: Mapping, today: str) -> bool:
    start, end = entry.get("valid_from"), entry.get("valid_to")
    return (_blank(start) or str(start) <= today) and (_blank(end) or today < str(end))


def tier_in_force(tiers: Sequence[Mapping], *, today: str) -> Mapping | None:
    """The entry whose validity covers ``today`` (from ``valid_from``, up to but not including ``valid_to``).

    Superseded entries stay in the file with their ``valid_to``; when two still overlap,
    the later ``valid_from`` wins, then the later entry.

    >>> tier_in_force([{"tier": "open", "valid_from": "2026-10-01"}], today="2026-09-15") is None
    True
    """
    covering = [
        (str(entry.get("valid_from") or ""), index, entry)
        for index, entry in enumerate(tiers)
        if _covers(entry, today)
    ]
    return max(covering, key=lambda row: row[:2])[2] if covering else None


def is_lapsed(entry: Mapping, *, today: str) -> bool:
    """Whether a permissive tier's review is overdue, or was never scheduled. Restrictive tiers never lapse.

    >>> is_lapsed({"tier": "involved"}, today="2026-09-15"), is_lapsed({"tier": "reviewed"}, today="2026-09-15")
    (True, False)
    """
    review_by = entry.get("review_by")
    return entry.get("tier") in PERMISSIVE_TIERS and (
        _blank(review_by) or str(review_by) < today
    )


def effective_tier(tiers: Sequence[Mapping], *, today: str) -> tuple[str | None, bool]:
    """``(tier, lapsed)`` for today: the tier in force, :data:`DEFAULT_TIER` in place of a lapsed one.

    ``None`` when no entry covers today (what applies then, a linked org's
    ``default_tier`` or the default, is the disclosure computation's question). An
    unknown tier value reads as ``reviewed``.

    >>> effective_tier([{"tier": "trusted"}], today="2026-09-15"), effective_tier([], today="2026-09-15")
    (('reviewed', False), (None, False))
    """
    entry = tier_in_force(tiers, today=today)
    if entry is None:
        return None, False
    if entry.get("tier") not in TIERS:
        return _UNKNOWN_TIER, False
    if is_lapsed(entry, today=today):
        return DEFAULT_TIER, True
    return entry["tier"], False


def entity_label(meta: Mapping, kind: str) -> str:
    """A record's label: its frontmatter ``label``, else ``green`` for a person and ``amber`` for anything else.

    A label that is not one of :data:`LABELS` reads as ``red``.
    """
    label = meta.get("label")
    if _blank(label):
        return _DEFAULT_LABELS.get(kind, _DEFAULT_LABEL)
    return label if label in LABELS else _UNKNOWN_LABEL


def fact_label(text: str, record_label: str) -> str:
    """One fact's label: its own ``[label: …]`` tag, else the label of the record it sits in.

    A malformed or unknown tag reads as ``red``.

    >>> fact_label("- Heron ships in October. [label: amber] [source: operator]", "green")
    'amber'
    >>> fact_label("- Prefers email. [source: operator]", "green"), fact_label("- x [label: purple]", "green")
    ('green', 'red')
    """
    tags = fact_tags(text)
    if tags["label"] is None and not tags["problems"]:
        return record_label
    return (
        tags["label"]
        if tags["label"] in LABELS and not tags["problems"]
        else _UNKNOWN_LABEL
    )
