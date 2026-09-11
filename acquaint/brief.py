"""The brief: everything an agent should know before writing to someone, assembled in one call.

A brief is the reuse point for communication intelligence. It gathers the entry
file's card sections, the writing card (``style.md``), positions and standing
objections (``views.md``), how to reach them for this purpose, the norms of the
project the message belongs to, recent observations (marked as evidence, not
facts), reminders for the purpose, the disclosure stance, and an explicit list of
what is **not** known, so gaps get asked about instead of filled in.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from acquaint.lint import lint_store
from acquaint.lookup import reach_channels
from acquaint.records import parse_log, sections, split_frontmatter
from acquaint.resources import data_yaml
from acquaint.store import AcquaintError, Store

__all__ = ["compose_brief", "CARD_SECTIONS"]

#: Entry-file sections a brief carries, in the order it shows them.
CARD_SECTIONS = ("Who", "Write to them", "Read them", "Don't", "Now")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_UNTIL_RE = re.compile(r"\(until:\s*(\d{4}-\d{2}-\d{2})\)")


def _visible(text: str) -> str:
    """Section text with HTML comments and blank runs removed; empty when only guidance comments remain."""
    text = _COMMENT_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _drop_expired(text: str, today: str) -> str:
    kept = [
        line
        for line in text.splitlines()
        if not ((m := _UNTIL_RE.search(line)) and m.group(1) < today)
    ]
    return "\n".join(kept).strip()


def _recent_observations(entity, limit: int) -> list[dict]:
    entries = [
        {**entry, "ref": f"{name}#{entry['id']}"}
        for name in sorted(n for n in entity if n.startswith("log/"))
        for entry in parse_log(entity[name])
    ]
    return entries[-limit:] if limit else entries


def compose_brief(
    store: Store,
    key: str,
    *,
    purpose: str | None = None,
    project: str | None = None,
    today: str | None = None,
) -> dict[str, Any]:
    """Assemble the brief for writing to one entity, as data plus a Markdown ``text`` rendering."""
    today = today or date.today().isoformat()
    entity = store[key]
    purposes = data_yaml("purposes.yaml")
    budgets = data_yaml("policy.yaml")["budgets"]

    card = {title: _visible(entity.sections.get(title, "")) for title in CARD_SECTIONS}
    card["Now"] = _drop_expired(card["Now"], today)
    style_meta, style_body, style_errors = split_frontmatter(entity.text("style.md")) if "style.md" in entity else ({}, "", [])
    style_text = _visible(style_body if not style_errors or style_body else entity.text("style.md"))
    views_text = _visible(entity.text("views.md"))

    tolerance = str(style_meta.get("ai_tolerance") or "unknown").lower()
    disclosure = style_meta.get("disclosure") or purposes["disclosure"].get(tolerance, purposes["disclosure"]["unknown"])
    spec = purposes["purposes"].get(str(purpose).lower(), {}) if purpose else {}
    reminders = list(purposes["default"]["reminders"]) + list(spec.get("reminders", []))

    reach = reach_channels(
        store,
        key,
        defaults_text=store.files["_defaults/rules.yaml"] if "_defaults/rules.yaml" in store.files else "",
        purpose=purpose,
        project=project,
    )["channels"]

    norms, project_key = "", None
    if project:
        try:
            project_key = store.find(project if ":" in project or "/" in project else f"project:{project}")
            project_sections = store[project_key].sections
            norms = "\n\n".join(
                filter(None, (_visible(project_sections.get(t, "")) for t in ("Norms", "Now")))
            )
        except (KeyError, AcquaintError):
            project_key = None

    affiliations = [
        " · ".join(str(link[k]) for k in ("to", "relation", "role") if link.get(k))
        for link in entity.links
    ]
    observations = _recent_observations(entity, budgets["brief_observations"])
    lint = lint_store(store, key, today=today)

    gaps = [f"nothing recorded under '{title}'" for title in ("Write to them", "Read them", "Don't") if not card[title]]
    if not style_text:
        gaps.append("no writing card (style.md): register, length and AI tolerance are unknown")
    if not entity.identities:
        gaps.append("no identities (handles or addresses) recorded")
    if not any(ch["tier"] != "none" for ch in reach):
        gaps.append("no channel rules match this context")
    if project and not project_key:
        gaps.append(f"no project {project!r} in the store, so no project norms")

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
    }
    result["text"] = _render(entity, result)
    return result


def _render(entity, brief: dict[str, Any]) -> str:
    title = f"# Brief: {brief['name']} ({entity.ref})"
    scope = " · ".join(filter(None, [brief["purpose"] and f"purpose: {brief['purpose']}", brief["project"] and f"project: {brief['project']}"]))
    out = [title + (f", {scope}" if scope else ""), ""]
    if description := entity.meta.get("description"):
        out += [str(description), ""]
    if brief["relational"]:
        out += [f"**This is a relational message ({brief['purpose']}). The operator writes it; do not draft the text.**", ""]

    out.append("## How to reach them")
    if brief["reach"]:
        for n, ch in enumerate(brief["reach"], start=1):
            what = ch["channel"] or ch["instruction"]
            where = f" → {ch['address']}" if ch["address"] else ""
            why = f"{ch['tier']} rule" if ch["tier"] != "none" else ch["instruction"]
            source = f"; source: {ch['source']}" if ch.get("source") else ""
            out.append(f"{n}. {what}{where} ({why}{source})")
    else:
        out.append("No identities or channel rules recorded.")
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
            out.append(f"- {entry['date']} · {entry['kind']}: {entry['text']} (source: {entry.get('source', 'none given')}; {entry['ref']})")
        out.append("")
    out += [f"## For this message{' (' + brief['purpose'] + ')' if brief['purpose'] else ''}", *(f"- {r}" for r in brief["reminders"]), ""]
    if brief["gaps"]:
        out += ["## Not known (ask, don't guess)", *(f"- {g}" for g in brief["gaps"]), ""]
    if brief["lint"]["errors"]:
        out += [f"**This record has {brief['lint']['errors']} lint error(s); run `acquaint lint {entity.slug}` before relying on it.**", ""]
    out.append(f"Before sending: `acquaint style-lint --recipient {entity.slug} \"<draft>\"` and `acquaint check \"<draft>\"`.")
    return "\n".join(out).rstrip() + "\n"
