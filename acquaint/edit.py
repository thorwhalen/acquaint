"""Changing the store: create an entity, append an observation, rename with relinking, forget with a tombstone.

The hot path is append-only. :func:`append_observation` never edits an entry file, a
writing card or a rule: it appends a dated, sourced entry to ``log/YYYY-MM.md`` (or a
handle to ``identities.yaml``). Turning observations into profile lines is a separate,
reviewed pass.

These functions take exact references (``ada-lovelace``, ``person:ada-lovelace``,
``people/ada-lovelace``); matching names to ids is the caller's job
(:func:`acquaint.lookup.find_entity`), so nothing here acts on a guess.
"""

from __future__ import annotations

import hashlib
import re
import secrets
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
    next_log_id,
    slugify,
    source_kind,
    source_problem,
    split_frontmatter,
)
from acquaint.resources import data_text, data_yaml
from acquaint.store import ENTRY_FILE, KIND_DIRS, UNREADABLE, AcquaintError, Entity, Store, kind_dir, validate_key

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
_TOMBSTONE_HEADER = (
    "# Salted hashes of forgotten entities' identifiers, so an import does not silently re-create them.\n"
    "# The salt only prevents precomputed lookups: anyone holding this file can still test a guess.\n"
)


def _today(today: str | None) -> str:
    return today or date.today().isoformat()


def _find(store: Store, ref: str) -> str:
    try:
        return store.find(ref)
    except KeyError:
        raise AcquaintError(f"no entity with the id {ref!r}") from None


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


# --------------------------------------------------------------------- tombstones


def _tombstone_data(store: Store) -> dict:
    if TOMBSTONES not in store.files:
        return {}
    data, _ = load_yaml(store.files[TOMBSTONES])
    return data if isinstance(data, dict) else {}


def _hashes(values: list[str], salt: str) -> list[str]:
    return sorted({hashlib.sha256((salt + normalize(v)).encode()).hexdigest() for v in values if normalize(v)})


def tombstoned(store: Store, *identifiers: str) -> dict | None:
    """The tombstone matching any of these identifiers, if such an entity was forgotten."""
    data = _tombstone_data(store)
    salt, graves = data.get("salt"), data.get("tombstones") or []
    if not salt or not graves:
        return None
    wanted = set(_hashes(list(identifiers), str(salt)))
    return next((grave for grave in graves if wanted & set(grave.get("hashes", []))), None)


def _write_tombstone(store: Store, kind: str, identifiers: list[str], today: str) -> None:
    data = _tombstone_data(store)
    salt = str(data.get("salt") or secrets.token_hex(16))
    graves = list(data.get("tombstones") or [])
    graves.append({"kind": kind, "forgotten": today, "hashes": _hashes(identifiers, salt)})
    store.files[TOMBSTONES] = _TOMBSTONE_HEADER + dump_yaml({"salt": salt, "tombstones": graves})


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
    singular = {v: k for k, v in KIND_DIRS.items()}.get(folder, kind.strip().lower())
    slug = slugify(name, qualifier=qualifier)
    key = validate_key(f"{folder}/{slug}")
    grave = tombstoned(store, slug, name)
    if grave and store.exists(key):
        raise AcquaintError(
            f"a {singular} matching {name!r} was forgotten on {grave.get('forgotten', '?')}, but files remain in {key}; "
            f"run `acquaint forget {slug} --confirm` again to finish removing them"
        )
    if grave and not force:
        raise AcquaintError(
            f"a {singular} matching {name!r} was forgotten on {grave.get('forgotten', '?')}; "
            "pass --force to re-create it deliberately"
        )
    if store.exists(key):
        raise AcquaintError(
            f"{key} already exists. If this is a different {singular} with the same name, "
            f"pass a qualifier (e.g. --qualifier example-org) to make {slug}--example-org"
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
    body = Template(data_text(f"templates/{template}")).safe_substitute(name=name.strip(), kind=singular, slug=slug)
    created = [f"{key}/{ENTRY_FILE}"]
    if "POLICY.md" not in store.files:
        store.files["POLICY.md"] = data_text("templates/POLICY.md")
        created.append("POLICY.md")
    store[key] = {ENTRY_FILE: join_frontmatter(meta, body)}
    warning = store.location_warning()
    return {
        "key": key,
        "id": slug,
        "kind": singular,
        "path": store.path_of(key),
        "created": created,
        "warnings": [warning] if warning else [],
    }


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
    log_name = f"log/{today[:7]}.md"
    existing = entity.text(log_name)
    if UNREADABLE in existing:
        raise AcquaintError(f"{key}/{log_name} is not valid UTF-8; fix its encoding before appending to it")
    warnings = [message for _, message in policy_hits(text)]

    if kind == "identity":
        platform, sep, value = text.partition(":")
        if not sep or not platform.strip() or not value.strip():
            raise AcquaintError("an identity is written platform:value, e.g. 'email:ada@example.org'")
        _append_identity(entity, platform.strip().lower(), value.strip(), source, today)

    entry_id = next_log_id(existing)
    entry = format_log_entry(entry_id, today, kind, text, source=source or _UNSOURCED)
    separator = "" if not existing or existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    store.append_text(key, log_name, separator + entry)
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
    current = entity.text("identities.yaml", "identities: []\n")
    data, errors = load_yaml(current)
    if errors or UNREADABLE in current or not isinstance(data, dict):
        raise AcquaintError(f"{entity.key}/identities.yaml does not parse; fix it before adding to it")
    identities = list(data.get("identities") or [])
    if any(str(i.get("platform")) == platform and str(i.get("value")) == value for i in identities):
        return
    identities.append(
        {"platform": platform, "value": value, "source": source or _UNSOURCED, "first_seen": today, "status": "active"}
    )
    entity["identities.yaml"] = dump_yaml({**data, "identities": identities})


# ------------------------------------------------------------------------- rename


def _relink(store: Store, kind: str, old_slug: str, new_slug: str) -> list[str]:
    """Rewrite references to a renamed entity in other records, never inside URLs, logs or research.

    ``kind:slug`` tokens are rewritten wherever they stand as a token of their own; a
    project's bare slug is rewritten only as the value of a ``project:`` key in YAML.
    Folder paths (``projects/slug``) are left alone, because they also occur inside URLs.
    """
    old_ref, new_ref = f"{kind}:{old_slug}", f"{kind}:{new_slug}"
    ref_re = re.compile(rf"(?<![\w/.:@=&?#-]){re.escape(old_ref)}(?![\w/-])")
    project_re = re.compile(
        rf"(?P<pre>(?:^|[{{,])[ \t]*(?:-[ \t]+)?project[ \t]*:[ \t]*)(?P<q>['\"]?){re.escape(old_slug)}(?P=q)(?P<post>[ \t]*(?:[,}}#]|$))",
        re.M,
    )

    def outside_urls(text: str, pattern: re.Pattern, replacement) -> str:
        def replace(found: re.Match) -> str:
            start = text.rfind(" ", 0, found.start()) + 1
            end = text.find(" ", found.end())
            token = text[start : end if end != -1 else len(text)]
            return found.group(0) if "://" in token else replacement(found)

        return pattern.sub(replace, text)

    relinked = []
    for path in list(store.files):
        if "/log/" in path or "/research/" in path or not path.endswith((".md", ".yaml", ".yml")):
            continue
        text = store.files[path]
        if UNREADABLE in text:
            continue
        updated = outside_urls(text, ref_re, lambda _: new_ref)
        if kind == "project" and path.endswith((".yaml", ".yml")):
            updated = project_re.sub(lambda m: f"{m.group('pre')}{m.group('q')}{new_slug}{m.group('q')}{m.group('post')}", updated)
        if updated != text:
            store.files[path] = updated
            relinked.append(path)
    return relinked


def rename_entity(store: Store, ref: str, to: str, *, today: str | None = None) -> dict[str, Any]:
    """Give an entity a new id (``to`` is a slug) or a new name and id (``to`` is a name); links elsewhere follow."""
    key = _find(store, ref)
    entity = store[key]
    old_slug, old_name, kind = entity.slug, entity.name, entity.kind
    new_slug = to if to == slugify(to) else slugify(to)
    new_name = old_name if to == new_slug else to.strip()
    new_key = validate_key(f"{entity.kind_dir}/{new_slug}")
    if new_key == key:
        raise AcquaintError(f"{key} is already called that")
    if store.exists(new_key):
        raise AcquaintError(f"{new_key} already exists")
    profile = entity.text(ENTRY_FILE)
    meta, body, errors = split_frontmatter(profile)
    if errors or UNREADABLE in profile:
        raise AcquaintError(f"{key}/{ENTRY_FILE} does not parse; fix it before renaming: {(errors or ['not valid UTF-8'])[0]}")

    store.move(key, new_key)
    aka = [str(a) for a in _as_list(meta.get("aka")) if a not in (None, "")] + [old_slug, old_name]
    meta.update(
        id=new_slug,
        name=new_name,
        aka=list(dict.fromkeys(a for a in aka if a not in (new_name, new_slug))),
        updated=_today(today),
    )
    store.files[f"{new_key}/{ENTRY_FILE}"] = join_frontmatter(meta, body)
    relinked = _relink(store, kind, old_slug, new_slug)
    return {"from": key, "to": new_key, "name": new_name, "relinked": relinked}


# ------------------------------------------------------------------------- forget


def _forget_key(store: Store, ref: str) -> str:
    """The entity to forget, including a folder left without its entry file by an interrupted forget."""
    try:
        return store.find(ref)
    except KeyError:
        pass
    candidate = ref.strip()
    if ":" in candidate and "/" not in candidate:
        kind, _, slug = candidate.partition(":")
        candidate = f"{kind_dir(kind)}/{slug}"
    elif "/" not in candidate:
        candidate = f"people/{candidate}"
    if store.exists(candidate):
        return candidate
    raise AcquaintError(f"no entity with the id {ref!r}")


def forget_entity(store: Store, ref: str, *, confirm: bool = False, today: str | None = None) -> dict[str, Any]:
    """Remove an entity's whole folder, hidden files included, after writing a salted tombstone.

    Without ``confirm`` it only reports what it would remove. The tombstone is written
    first, so a removal that fails half way still stops the entity being re-created, and
    running ``forget`` again finishes the job.
    """
    key = validate_key(_forget_key(store, ref))
    entity = Entity(store, key)
    name_parts = {part.lower() for part in entity.name.split()}
    aka = [a for a in entity.aka if a.lower() not in name_parts]  # bare name parts would block unrelated people
    identifiers = [entity.slug, entity.name, *aka, *(str(i.get("value", "")) for i in entity.identities)]
    files = [f"{key}/{name}" for name in store.all_files(key)]
    plan = {"key": key, "files": files, "tombstone_identifiers": len({normalize(i) for i in identifiers if normalize(i)})}
    if not confirm:
        return {**plan, "done": False}

    today = _today(today)
    if not tombstoned(store, entity.slug):
        _write_tombstone(store, entity.kind, identifiers, today)
    try:
        del store[key]
    except OSError as error:
        left = [f"{key}/{name}" for name in store.all_files(key)]
        raise AcquaintError(
            f"tombstone written, but {len(left)} file(s) could not be removed ({error}); "
            f"fix that and run forget again: {', '.join(left)}"
        ) from error
    return {
        **plan,
        "done": True,
        "history_rewrite": [
            "The folder is gone from the store, hidden files included; it is not gone from git history or other clones.",
            f"git -C <data root> filter-repo --invert-paths --path {key}/   (needs git-filter-repo)",
            "git -C <data root> push --force   (after acquaint sync pull; other clones must re-clone)",
            "Copies in backups, forks or other machines are not touched by this.",
        ],
    }
