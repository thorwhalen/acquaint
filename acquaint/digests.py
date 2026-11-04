"""Digests: what a conversation with an entity said, written up through a watermark.

A digest is one Markdown file per conversation, in the entity's folder
(``people/<id>/digests/<name>.md``, and the same under projects, orgs and groups). Its
frontmatter is the state of the processing, and its body is the notes:

.. code-block:: yaml

    schema: acquaint/digest/v1
    ref: whatsapp:ada-lovelace        # the correspond conversation reference: the SSOT
    archive: correspond               # where the raw messages live (never this store)
    through:                          # the watermark, per scope: processed up to this time
      content: '2026-11-03T19:37:47+01:00'
      style: '2026-06-21T19:27:45+02:00'
    updated: '2026-11-04'

``through`` answers "from which date and time is this conversation new?": hand it to
``correspond read <ref> --since <through>`` to get what has not been processed. Two scopes
exist because a conversation can be mined for how someone writes (``style``, the
**acquaint-profile** skill) separately from what it said (``content``, the
**acquaint-digest** skill).

The body has five sections: *Orientation* (who is in it, what it is for, its span),
*Takeaways* (decisions, agreements, asks, facts the operator will need), *Themes* (the
recurring subjects, each with where it comes up), *Index* (the conversation cut into
dated sections so an agent can go straight to one) and *Open threads* (what is waiting on
whom). Every item in those sections carries an anchor, ``[at: <ISO time>]`` (a message time
in the archive: ``rg -n '^2026-07-03T14:02' <transcript>``) or a ``[source: …]``; the
messages themselves stay in the archive, never here (``POLICY.md``: no whole message
bodies).

>>> digest_name("whatsapp:ada-lovelace"), digest_name("github:example/demo#12")
('digests/whatsapp-ada-lovelace.md', 'digests/github-example-demo-12.md')
"""

from __future__ import annotations

import re
from string import Template
from datetime import date, datetime
from typing import Any

from acquaint.records import join_frontmatter, split_frontmatter
from acquaint.resources import data_text
from acquaint.store import AcquaintError, Entity

__all__ = [
    "ANCHORED_SECTIONS",
    "DIGEST_DIR",
    "SCHEMA",
    "SCOPES",
    "digest_name",
    "digest_problems",
    "digests",
    "find_digest",
    "mark_digest",
    "new_digest",
]

DIGEST_DIR = "digests"
SCHEMA = "acquaint/digest/v1"
#: What a watermark can cover: what the conversation said, and how its author writes.
SCOPES = ("content", "style")
#: Sections whose every item needs an ``[at: …]`` or ``[source: …]`` anchor.
ANCHORED_SECTIONS = ("Takeaways", "Themes", "Index", "Open threads")
_ANCHOR_RE = re.compile(r"\[(?:at|source):\s*[^\]]+\]")
_QUOTE_RE = re.compile(r"[\"“]([^\"”]+)[\"”]")
#: The longest quote a digest keeps, in words (POLICY.md: no whole message bodies).
MAX_QUOTE_WORDS = 25


def digest_name(ref: str) -> str:
    """The digest's file name inside the entity's folder, derived from the reference."""
    slug = re.sub(r"[^a-z0-9]+", "-", ref.lower()).strip("-")
    if not slug:
        raise AcquaintError(f"{ref!r} is not a conversation reference")
    return f"{DIGEST_DIR}/{slug}.md"


def _time(value: Any, what: str) -> str:
    text = value.isoformat() if isinstance(value, (datetime, date)) else str(value)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise AcquaintError(
            f"{what} must be an ISO 8601 time, e.g. 2026-11-03T19:37:47+01:00, not {text!r}"
        ) from None
    return text


def _when(text: str) -> datetime:
    moment = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.astimezone()


def _summary(entity: Entity, name: str) -> dict:
    meta, _, errors = split_frontmatter(entity[name])
    through = meta.get("through") if isinstance(meta.get("through"), dict) else {}
    return {
        "ref": meta.get("ref"),
        "file": name,
        "path": f"{entity.key}/{name}",
        "archive": meta.get("archive"),
        "through": {k: str(v) for k, v in through.items()},
        "updated": str(meta.get("updated") or ""),
        "errors": errors,
    }


def digests(entity: Entity) -> list[dict]:
    """Every digest of the entity: its reference, file and watermarks."""
    return [
        _summary(entity, name)
        for name in sorted(entity)
        if name.startswith(f"{DIGEST_DIR}/") and name.endswith(".md")
    ]


def find_digest(entity: Entity, ref: str) -> dict | None:
    """The digest of one conversation, found by the ``ref`` in its frontmatter (else by file name)."""
    found = [d for d in digests(entity) if d["ref"] == ref]
    if found:
        return found[0]
    name = digest_name(ref)
    return _summary(entity, name) if name in entity else None


def new_digest(
    entity: Entity,
    ref: str,
    *,
    archive: str = "correspond",
    today: str | None = None,
) -> dict:
    """Create the digest of ``ref`` from its template, with no watermark yet. Refuses when one exists."""
    if find_digest(entity, ref):
        raise AcquaintError(
            f"{entity.key} already has a digest of {ref}: {find_digest(entity, ref)['file']}"
        )
    name = digest_name(ref)
    entity[name] = Template(data_text("templates/digest.md")).substitute(
        ref=ref,
        archive=archive,
        name=entity.name,
        today=today or date.today().isoformat(),
    )
    return _summary(entity, name)


def mark_digest(
    entity: Entity,
    ref: str,
    through: str,
    *,
    scope: str = "content",
    force: bool = False,
    today: str | None = None,
) -> dict:
    """Move the watermark of ``scope`` to ``through``. Moving it back needs ``force``."""
    if scope not in SCOPES:
        raise AcquaintError(f"scope is one of {', '.join(SCOPES)}, not {scope!r}")
    through = _time(through, "through")
    found = find_digest(entity, ref)
    if found is None:
        raise AcquaintError(
            f"{entity.key} has no digest of {ref}; create it first (acquaint digest-new {entity.slug} {ref})"
        )
    meta, body, errors = split_frontmatter(entity[found["file"]])
    if errors:
        raise AcquaintError(f"{found['path']}: {errors[0]}; fix the frontmatter by hand")
    marks = dict(meta.get("through") or {})
    previous = marks.get(scope)
    if previous and _when(through) < _when(previous) and not force:
        raise AcquaintError(
            f"{scope} is already processed through {previous}; moving it back to {through} needs force"
        )
    marks[scope] = through
    meta["through"] = marks
    meta["updated"] = today or date.today().isoformat()
    entity[found["file"]] = join_frontmatter(meta, body)
    return {**_summary(entity, found["file"]), "previous": previous}


def digest_problems(text: str) -> list[tuple[str, int | None, str, str]]:
    """``(severity, line, rule, message)`` for one digest file: frontmatter shape, unanchored items, long quotes."""
    from acquaint.records import blank_frontmatter, sectioned_items

    meta, _, errors = split_frontmatter(text)
    found: list[tuple[str, int | None, str, str]] = [
        ("error", None, "unparseable", e) for e in errors
    ]
    if errors:
        return found
    if not isinstance(meta.get("ref"), str) or ":" not in meta.get("ref", ""):
        found.append(
            (
                "error",
                None,
                "digest-ref",
                "ref must be a conversation reference, <channel>:<id>",
            )
        )
    through = meta.get("through") or {}
    if not isinstance(through, dict):
        found.append(
            ("error", None, "digest-through", "through must map scopes to times")
        )
        through = {}
    for scope, value in through.items():
        if scope not in SCOPES:
            found.append(
                (
                    "error",
                    None,
                    "digest-through",
                    f"unknown scope {scope!r}; use {', '.join(SCOPES)}",
                )
            )
        try:
            _time(value, f"through.{scope}")
        except AcquaintError as error:
            found.append(("error", None, "digest-through", str(error)))
    for section, number, item in sectioned_items(blank_frontmatter(text)):
        if section in ANCHORED_SECTIONS and not _ANCHOR_RE.search(item):
            found.append(
                (
                    "error",
                    number,
                    "unanchored",
                    f"an item under {section} needs [at: <ISO time>] or [source: …]",
                )
            )
        for quote in _QUOTE_RE.findall(item):
            if len(quote.split()) > MAX_QUOTE_WORDS:
                found.append(
                    (
                        "warning",
                        number,
                        "long-quote",
                        f"a quote of {len(quote.split())} words; keep {MAX_QUOTE_WORDS} or fewer and point at the message",
                    )
                )
    return found
