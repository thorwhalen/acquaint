"""Changing the store: create an entity, append an observation, rename with relinking, forget with a tombstone.

The hot path is append-only. :func:`append_observation` never edits an entry file,
a writing card or a rule: it adds a dated, sourced entry to ``log/YYYY-MM.md`` (or a
handle to ``identities.yaml``). Turning observations into profile lines is a
separate, reviewed pass.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from string import Template
from typing import Any

from acquaint.lint import policy_hits
from acquaint.lookup import normalize
from acquaint.records import (
    dump_yaml,
    format_log_entry,
    join_frontmatter,
    load_yaml,
    parse_log,
    slugify,
    source_kind,
    source_problem,
    split_frontmatter,
)
from acquaint.resources import data_text, data_yaml
from acquaint.store import ENTRY_FILE, KIND_DIRS, AcquaintError, Entity, Store, kind_dir

__all__ = [
    "OBSERVATION_KINDS",
    "SCHEMA",
    "append_observation",
    "forget_entity",
    "new_entity",
    "rename_entity",
    "tombstoned",
]

SCHEMA = "acquaint/profile/v1"
TOMBSTONES = "_tombstones.yaml"
#: What ``remember`` can record. The last three need a source at write time.
OBSERVATION_KINDS = ("observation", "interaction", "identity", "preference", "view", "rule")
_NEEDS_SOURCE = {"preference", "view", "rule"}
_UNSOURCED = "none given"


def _today(today: str | None) -> str:
    return today or date.today().isoformat()


def _find(store: Store, ref: str) -> str:
    try:
        return store.find(ref)
    except KeyError:
        known = ", ".join(key.split("/", 1)[1] for key in list(store)[:12]) or "(store is empty)"
        raise AcquaintError(f"no entity {ref!r}. Known: {known}") from None


def _hashes(values: list[str]) -> list[str]:
    return sorted({hashlib.sha256(normalize(v).encode()).hexdigest() for v in values if normalize(v)})


def _tombstones(store: Store) -> list[dict]:
    data, _ = load_yaml(store.files[TOMBSTONES]) if TOMBSTONES in store.files else ({}, [])
    return list((data or {}).get("tombstones", [])) if isinstance(data, dict) else []


def tombstoned(store: Store, *identifiers: str) -> dict | None:
    """The tombstone matching any of these identifiers, if the entity was forgotten."""
    wanted = set(_hashes(list(identifiers)))
    return next((t for t in _tombstones(store) if wanted & set(t.get("hashes", []))), None)


# ---------------------------------------------------------------------------- new


def new_entity(
    store: Store,
    kind: str,
    name: str,
    *,
    qualifier: str | None = None,
    description: str | None = None,
    force: bool = False,
    today: str | None = None,
) -> dict[str, Any]:
    """Scaffold ``<kind dir>/<slug>/PROFILE.md`` from the template for its kind, and seed ``POLICY.md``."""
    folder = kind_dir(kind)
    singular = {v: k for k, v in KIND_DIRS.items()}.get(folder, kind.lower())
    slug = slugify(name, qualifier=qualifier)
    key = f"{folder}/{slug}"
    if key in store:
        raise AcquaintError(
            f"{key} already exists. If this is a different {singular} with the same name, "
            f"pass a qualifier (e.g. --qualifier example-org) to make {slug}--example-org"
        )
    grave = tombstoned(store, slug, name)
    if grave and not force:
        raise AcquaintError(
            f"a {singular} matching {name!r} was forgotten on {grave.get('forgotten', '?')}; "
            "pass --force to re-create it deliberately"
        )
    today = _today(today)
    review_days = data_yaml("policy.yaml")["budgets"]["review_due_days"]
    parts = [p for p in re.split(r"\s+", name.strip()) if len(p) > 1]
    meta = {
        "schema": SCHEMA,
        "kind": singular,
        "id": slug,
        "name": name.strip(),
        "aka": parts if singular == "person" and len(parts) > 1 else [],
        "description": description or "",
        "updated": today,
        "review_due": (date.fromisoformat(today) + timedelta(days=review_days)).isoformat(),
    }
    template = "person.md" if singular == "person" else "ledger.md"
    body = Template(data_text(f"templates/{template}")).safe_substitute(
        name=name.strip(), kind=singular, slug=slug
    )
    created = [f"{key}/{ENTRY_FILE}"]
    if "POLICY.md" not in store.files:
        store.files["POLICY.md"] = data_text("templates/POLICY.md")
        created.append("POLICY.md")
    store[key] = {ENTRY_FILE: join_frontmatter(meta, body)}
    return {"key": key, "id": slug, "kind": singular, "path": store.path_of(key), "created": created}


# ----------------------------------------------------------------------- remember


def append_observation(
    store: Store,
    ref: str,
    text: str,
    *,
    source: str | None = None,
    kind: str = "observation",
    today: str | None = None,
) -> dict[str, Any]:
    """Append one dated, sourced entry to the entity's ``log/YYYY-MM.md`` (and, for ``identity``, to ``identities.yaml``)."""
    if kind not in OBSERVATION_KINDS:
        raise AcquaintError(f"kind must be one of {', '.join(OBSERVATION_KINDS)}; got {kind!r}")
    text = " ".join(text.split())
    if not text:
        raise AcquaintError("nothing to remember: the text is empty")
    if source is not None:
        problem = source_problem(f"[source: {source}]")
        if problem:
            raise AcquaintError(f"--source {source!r}: {problem}")
    elif kind in _NEEDS_SOURCE:
        raise AcquaintError(
            f"a {kind} needs its source: --source with a permalink, the person's words "
            "('self: \"...\"'), 'operator', or 'none located' if you looked and found nothing"
        )
    key = _find(store, ref)
    entity = store[key]
    today = _today(today)
    warnings = [message for _, message in policy_hits(text)]

    if kind == "identity":
        platform, sep, value = text.partition(":")
        if not sep or not platform.strip() or not value.strip():
            raise AcquaintError("an identity is written platform:value, e.g. 'email:ada@example.org'")
        _append_identity(entity, platform.strip().lower(), value.strip(), source, today)

    log_name = f"log/{today[:7]}.md"
    existing = entity.text(log_name)
    numbers = [int(e["id"][1:]) for e in parse_log(existing)]
    entry_id = f"e{(max(numbers) + 1) if numbers else 1:02d}"
    entry = format_log_entry(entry_id, today, kind, text, source=source or _UNSOURCED)
    separator = "" if not existing or existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    entity[log_name] = existing + separator + entry
    if source is None:
        warnings.append(
            "recorded without a source: it stays an observation and cannot be promoted "
            "into the profile until one is found"
        )
    return {
        "key": key,
        "id": entity.slug,
        "entry": entry_id,
        "ref": f"{log_name}#{entry_id}",
        "kind": kind,
        "source": source,
        "source_kind": source_kind(source) if source else None,
        "warnings": warnings,
    }


def _append_identity(entity: Entity, platform: str, value: str, source: str | None, today: str) -> None:
    data, errors = load_yaml(entity.text("identities.yaml", "identities: []\n"))
    if errors or not isinstance(data, dict):
        raise AcquaintError(f"{entity.key}/identities.yaml does not parse; fix it before adding to it")
    identities = list(data.get("identities") or [])
    if any(str(i.get("platform")) == platform and str(i.get("value")) == value for i in identities):
        return
    identities.append(
        {"platform": platform, "value": value, "source": source or _UNSOURCED, "first_seen": today, "status": "active"}
    )
    entity["identities.yaml"] = dump_yaml({**data, "identities": identities})


# ------------------------------------------------------------------------- rename


def rename_entity(store: Store, ref: str, to: str, *, today: str | None = None) -> dict[str, Any]:
    """Give an entity a new id (``to`` is a slug) or a new name and id (``to`` is a name), rewriting links to it."""
    key = _find(store, ref)
    entity = store[key]
    old_slug, old_name, old_ref = entity.slug, entity.name, entity.ref
    new_slug = to if to == slugify(to) else slugify(to)
    new_name = old_name if to == new_slug else to.strip()
    new_key = f"{entity.kind_dir}/{new_slug}"
    if new_key == key:
        raise AcquaintError(f"{key} is already called that")
    if new_key in store:
        raise AcquaintError(f"{new_key} already exists")

    files = {name: entity[name] for name in entity}
    meta, body, errors = split_frontmatter(files[ENTRY_FILE])
    if errors:
        raise AcquaintError(f"{key}/{ENTRY_FILE} does not parse; fix it before renaming: {errors[0]}")
    aka = [a for a in [*(meta.get("aka") or []), old_slug, old_name] if a and a != new_name]
    meta.update(id=new_slug, name=new_name, aka=list(dict.fromkeys(aka)), updated=_today(today))
    files[ENTRY_FILE] = join_frontmatter(meta, body)
    store[new_key] = files
    del store[key]

    new_ref = f"{entity.kind}:{new_slug}"
    pattern = re.compile(rf"(?<![\w-])({re.escape(old_ref)}|{re.escape(key)})(?![\w-])")
    relinked = []
    for path in list(store.files):
        if "/log/" in path or "/research/" in path or not path.endswith((".md", ".yaml", ".yml")):
            continue
        text = store.files[path]
        updated = pattern.sub(lambda m: new_ref if ":" in m.group(1) else new_key, text)
        if updated != text:
            store.files[path] = updated
            relinked.append(path)
    return {"from": key, "to": new_key, "name": new_name, "relinked": relinked}


# ------------------------------------------------------------------------- forget


def forget_entity(store: Store, ref: str, *, confirm: bool = False, today: str | None = None) -> dict[str, Any]:
    """Remove an entity and leave a hashed tombstone. Without ``confirm`` it only reports what it would do."""
    key = _find(store, ref)
    entity = store[key]
    # Bare name parts ("Ada") are left out: hashing them would block an unrelated "Ada" later.
    name_parts = {part.lower() for part in entity.name.split()}
    aka = [a for a in entity.aka if str(a).lower() not in name_parts]
    identifiers = [entity.slug, entity.name, *aka, *(str(i.get("value", "")) for i in entity.identities)]
    hashes = _hashes(identifiers)
    plan = {"key": key, "files": [f"{key}/{name}" for name in entity], "tombstone_hashes": len(hashes)}
    if not confirm:
        return {**plan, "done": False}

    del store[key]
    graves = _tombstones(store)
    graves.append({"kind": entity.kind, "forgotten": _today(today), "hashes": hashes})
    store.files[TOMBSTONES] = (
        "# Hashed identifiers of forgotten entities, so an import does not silently re-create them.\n"
        + dump_yaml({"tombstones": graves})
    )
    return {
        **plan,
        "done": True,
        "history_rewrite": [
            "The files are gone from the working tree, not from git history or other clones.",
            f"git -C <data root> filter-repo --invert-paths --path {key}/   (needs git-filter-repo)",
            "git -C <data root> push --force   (after acquaint sync pull; other clones must re-clone)",
            "Copies in backups, forks or other machines are not touched by this.",
        ],
    }
