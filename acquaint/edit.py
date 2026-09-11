"""Changing the store: create an entity, append an observation, rename with relinking, forget with a tombstone.

The hot path is append-only. :func:`append_observation` never edits an entry file, a
writing card or a rule: it appends a dated, sourced entry to ``log/YYYY-MM.md`` (or a
handle to ``identities.yaml``). The one change it makes to an existing entry is making an
inactive handle active again, and only when asked (``reactivate``). ``identities.yaml`` is
rewritten whenever it changes, so comments in it are not kept. Turning observations into
profile lines is a separate, reviewed pass.

These functions take exact references (``ada-lovelace``, ``person:ada-lovelace``,
``people/ada-lovelace``); matching names to ids is the caller's job
(:func:`acquaint.lookup.find_entity`), so nothing here acts on a guess.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import shlex
from datetime import date, timedelta
from string import Template
from typing import Any

from acquaint.lint import policy_hits
from acquaint.lookup import USABLE_STATUSES, normalise_handle, normalize
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
from acquaint.store import (
    ENTRY_FILE,
    KIND_DIRS,
    UNREADABLE,
    AcquaintError,
    Entity,
    Store,
    kind_dir,
    validate_key,
)

__all__ = [
    "OBSERVATION_KINDS",
    "SCHEMA",
    "TOMBSTONES",
    "append_observation",
    "forget_entity",
    "new_entity",
    "rename_entity",
    "tombstone_problem",
    "tombstoned",
]

SCHEMA = "acquaint/profile/v1"
TOMBSTONES = "_tombstones.yaml"
#: What ``remember`` can record. The last three need a source at write time.
OBSERVATION_KINDS = (
    "observation",
    "interaction",
    "identity",
    "preference",
    "view",
    "rule",
)
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


def tombstone_problem(store: Store) -> str | None:
    """Why ``_tombstones.yaml`` cannot be trusted, or ``None``. A broken file must never read as "nobody was forgotten"."""
    if TOMBSTONES not in store.files:
        return None
    text = store.files[TOMBSTONES]
    data, errors = load_yaml(text)
    if errors or UNREADABLE in text:
        return f"{TOMBSTONES} does not parse ({(errors or ['not valid UTF-8'])[0]})"
    if data is None:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("tombstones") or [], list):
        return f"{TOMBSTONES} should be a mapping with a 'tombstones' list"
    if data.get("tombstones") and not data.get("salt"):
        return f"{TOMBSTONES} has tombstones but no salt, so none of them can be matched"
    return None


def _tombstone_data(store: Store) -> dict:
    problem = tombstone_problem(store)
    if problem:
        raise AcquaintError(
            f"{problem}; fix it before creating or forgetting anyone, or a forgotten person could come back"
        )
    data, _ = (
        load_yaml(store.files[TOMBSTONES]) if TOMBSTONES in store.files else ({}, [])
    )
    return data or {}


def _hashes(values: list[str], salt: str) -> list[str]:
    return sorted(
        {
            hashlib.sha256((salt + normalize(v)).encode()).hexdigest()
            for v in values
            if normalize(v)
        }
    )


def tombstoned(store: Store, *identifiers: str) -> dict | None:
    """The tombstone matching any of these identifiers, if such an entity was forgotten. Raises if the tombstone file is broken."""
    data = _tombstone_data(store)
    salt, graves = data.get("salt"), data.get("tombstones") or []
    if not salt or not graves:
        return None
    wanted = set(_hashes(list(identifiers), str(salt)))
    return next(
        (
            grave
            for grave in graves
            if isinstance(grave, dict) and wanted & set(grave.get("hashes", []))
        ),
        None,
    )


def _write_tombstone(store: Store, kind: str, identifiers: list[str], today: str) -> None:
    data = _tombstone_data(store)
    salt = str(data.get("salt") or secrets.token_hex(16))
    graves = list(data.get("tombstones") or [])
    graves.append(
        {"kind": kind, "forgotten": today, "hashes": _hashes(identifiers, salt)}
    )
    store.files[TOMBSTONES] = _TOMBSTONE_HEADER + dump_yaml(
        {"salt": salt, "tombstones": graves}
    )


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
        "review_due": (
            date.fromisoformat(today) + timedelta(days=review_days)
        ).isoformat(),
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
    reactivate: bool = False,
    today: str | None = None,
) -> dict[str, Any]:
    """Append one dated, sourced entry to the entity's ``log/YYYY-MM.md`` (and, for ``identity``, to ``identities.yaml``).

    An identity equal to an inactive one is refused, naming that entry, unless
    ``reactivate`` is set (see :func:`_append_identity`). A refusal writes nothing.
    """
    if kind not in OBSERVATION_KINDS:
        raise AcquaintError(
            f"kind must be one of {', '.join(OBSERVATION_KINDS)}; got {kind!r}"
        )
    if reactivate and kind != "identity":
        raise AcquaintError("--reactivate applies to --kind identity only")
    if reactivate and source is None:
        raise AcquaintError(
            "--reactivate needs --source: what shows the identity is current again"
        )
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
        raise AcquaintError(
            f"{key}/{log_name} is not valid UTF-8; fix its encoding before appending to it"
        )
    warnings = [message for _, message in policy_hits(text)]

    identity = None
    if kind == "identity":
        platform, sep, value = text.partition(":")
        if not sep or not platform.strip() or not value.strip():
            raise AcquaintError(
                "an identity is written platform:value, e.g. 'email:ada@example.org'"
            )
        identity = _append_identity(
            entity,
            platform.strip().lower(),
            value.strip(),
            source,
            today,
            reactivate=reactivate,
        )
        if reactivate and identity["change"] != "reactivated":
            warnings.append(
                f"--reactivate had nothing to do: {identity['handle']} was "
                + (
                    "not recorded before"
                    if identity["change"] == "added"
                    else "already usable"
                )
            )

    entry_id = next_log_id(existing)
    entry = format_log_entry(entry_id, today, kind, text, source=source or _UNSOURCED)
    separator = (
        ""
        if not existing or existing.endswith("\n\n")
        else ("\n" if existing.endswith("\n") else "\n\n")
    )
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
        "identity": identity,
        "warnings": warnings,
    }


def _append_identity(
    entity: Entity,
    platform: str,
    value: str,
    source: str | None,
    today: str,
    *,
    reactivate: bool = False,
) -> dict[str, Any]:
    """Add ``platform:value`` to ``identities.yaml``: ``{"handle", "change", "previous_status"}``.

    ``change`` is ``added``, ``already_usable`` or ``reactivated``. Handles compare as
    :func:`acquaint.lookup.resolve_handle` compares them (case, a leading ``@``, Gmail
    dots). An entry with the same handle and an inactive status (``stale``, ``retracted``,
    …) is never kept silently: it is refused, naming the entry and the command that
    reactivates it, unless ``reactivate`` is set. The entry then becomes ``active`` with
    the new source (the caller checks there is one) and keeps its old status, source and
    evidence beside it.
    """

    def status_of(identity: dict) -> str:  # as acquaint.lookup reads it: none recorded means active
        return str(identity.get("status") or "active").strip().lower()

    current = entity.text("identities.yaml", "identities: []\n")
    data, errors = load_yaml(current)
    if errors or UNREADABLE in current or not isinstance(data, dict):
        raise AcquaintError(
            f"{entity.key}/identities.yaml does not parse; fix it before adding to it"
        )
    identities = list(data.get("identities") or [])
    handle = f"{platform}:{value}"
    wanted = normalise_handle(platform, value)
    same = [
        i
        for i in identities
        if isinstance(i, dict)
        and str(i.get("platform", "")).lower() == platform
        and normalise_handle(platform, str(i.get("value", ""))) == wanted
    ]
    if any(status_of(i) in USABLE_STATUSES for i in same):
        return {"handle": handle, "change": "already_usable", "previous_status": None}
    if same and not reactivate:
        entry = same[0]
        # Ends with --source so that pasting it without a source is a usage error, never a shell redirection.
        command = f"acquaint remember {entity.ref} {shlex.quote(handle)} --kind identity --reactivate --source"
        how = (
            f"the operator can reactivate it with: {command} {shlex.quote(source)}"
            if source
            else f"the operator can reactivate it, adding a source that shows it: {command}"
        )
        raise AcquaintError(
            f"{entry.get('platform')}:{entry.get('value')} is already recorded for {entity.ref}"
            f" as {status_of(entry)}"
            f" (source: {entry.get('source') or entry.get('evidence') or _UNSOURCED},"
            f" first seen {entry.get('first_seen') or 'unknown'},"
            f" in {entity.key}/identities.yaml), so nothing was recorded."
            f" If it is current again, {how}"
        )
    if same:
        entry = same[0]
        previous = status_of(entry)
        old = {k: entry.pop(k) for k in ("source", "evidence") if entry.get(k)}
        entry.update(
            {
                "source": source,
                "status": "active",
                "previous_status": previous,
                "reactivated": today,
            }
        )
        entry.update({f"previous_{k}": v for k, v in old.items()})
        change = "reactivated"
    else:
        identities.append(
            {
                "platform": platform,
                "value": value,
                "source": source or _UNSOURCED,
                "first_seen": today,
                "status": "active",
            }
        )
        previous, change = None, "added"
    entity["identities.yaml"] = dump_yaml({**data, "identities": identities})
    return {"handle": handle, "change": change, "previous_status": previous}


# ------------------------------------------------------------------------- rename


def _relink(
    store: Store, kind: str, folder: str, old_slug: str, new_slug: str
) -> tuple[list[str], list[str]]:
    """Rewrite references to a renamed entity in other records; never inside URLs, logs or research.

    Markdown: ``kind:slug`` and ``folder:slug`` tokens standing on their own (not inside a
    whitespace-delimited token containing ``://``). YAML: parsed, and any value equal to
    the old reference or key is replaced, as is a project's bare id as a ``project`` value
    (single or in a list); a rewritten YAML file is written back without its comments.
    Returns ``(files rewritten, YAML files whose comments were dropped)``.
    """
    old_refs = {
        f"{kind}:{old_slug}": f"{kind}:{new_slug}",
        f"{folder}:{old_slug}": f"{folder}:{new_slug}",
    }
    old_key, new_key = f"{folder}/{old_slug}", f"{folder}/{new_slug}"
    ref_re = re.compile(
        r"(?<![\w/.:@=&?#-])(" + "|".join(map(re.escape, old_refs)) + r")(?![\w/-])"
    )

    def in_markdown(text: str) -> str:
        def replace(found: re.Match) -> str:
            start = max(text.rfind(c, 0, found.start()) for c in " \t\n") + 1
            ends = [i for i in (text.find(c, found.end()) for c in " \t\n") if i != -1]
            token = text[start : min(ends) if ends else len(text)]
            return found.group(0) if "://" in token else old_refs[found.group(1)]

        return ref_re.sub(replace, text)

    def in_yaml(value: Any, parent: Any = None) -> Any:
        if isinstance(value, dict):
            return {k: in_yaml(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [in_yaml(v, parent) for v in value]
        if isinstance(value, str):
            if value in old_refs:
                return old_refs[value]
            if value == old_key:
                return new_key
            if kind == "project" and parent == "project" and value == old_slug:
                return new_slug
        return value

    relinked, comments_dropped = [], []
    for path in list(store.files):
        if "/log/" in path or "/research/" in path:
            continue
        text = store.files[path]
        if UNREADABLE in text:
            continue
        if path.endswith(".md"):
            updated = in_markdown(text)
        elif path.endswith((".yaml", ".yml")):
            data, errors = load_yaml(text)
            if errors or in_yaml(data) == data:
                continue
            updated = (_TOMBSTONE_HEADER if path == TOMBSTONES else "") + dump_yaml(
                in_yaml(data)
            )
            if re.search(r"(^|\s)#", text):
                comments_dropped.append(path)
        else:
            continue
        if updated != text:
            store.files[path] = updated
            relinked.append(path)
    return relinked, comments_dropped


def rename_entity(
    store: Store, ref: str, to: str, *, today: str | None = None
) -> dict[str, Any]:
    """Give an entity a new id (``to`` is a slug) or a new name and id (``to`` is a name); links elsewhere follow."""
    key = _find(store, ref)
    entity = store[key]
    old_slug, old_name, kind, folder = (
        entity.slug,
        entity.name,
        entity.kind,
        entity.kind_dir,
    )
    new_slug = to if to == slugify(to) else slugify(to)
    new_name = old_name if to == new_slug else to.strip()
    new_key = validate_key(f"{folder}/{new_slug}")
    if new_key == key:
        raise AcquaintError(f"{key} is already called that")
    if store.exists(new_key):
        raise AcquaintError(f"{new_key} already exists")
    profile = entity.text(ENTRY_FILE)
    meta, body, errors = split_frontmatter(profile)
    if errors or UNREADABLE in profile:
        raise AcquaintError(
            f"{key}/{ENTRY_FILE} does not parse; fix it before renaming: {(errors or ['not valid UTF-8'])[0]}"
        )

    store.move(key, new_key)
    aka = [str(a) for a in _as_list(meta.get("aka")) if a not in (None, "")] + [
        old_slug,
        old_name,
    ]
    meta.update(
        id=new_slug,
        name=new_name,
        aka=list(dict.fromkeys(a for a in aka if a not in (new_name, new_slug))),
        updated=_today(today),
    )
    store.files[f"{new_key}/{ENTRY_FILE}"] = join_frontmatter(meta, body)
    relinked, comments_dropped = _relink(store, kind, folder, old_slug, new_slug)
    return {
        "from": key,
        "to": new_key,
        "name": new_name,
        "relinked": relinked,
        "yaml_comments_dropped": comments_dropped,
    }


# ------------------------------------------------------------------------- forget


def _forget_key(store: Store, ref: str) -> str:
    """The entity to forget, including a folder left without its entry file by an interrupted forget."""
    candidate = ref.strip().lower()
    if "/" not in candidate and ":" not in candidate:
        ids = store.find_id(candidate)
        if len(ids) > 1:
            raise AcquaintError(
                f"{ref!r} names more than one entity: {', '.join(ids)}; say which, e.g. {Entity(store, ids[1]).ref}"
            )
        candidate = ids[0] if ids else f"people/{candidate}"
    elif "/" not in candidate:
        kind, _, slug = candidate.partition(":")
        candidate = f"{kind_dir(kind)}/{slug}"
    try:
        key = validate_key(candidate)
    except AcquaintError:
        raise AcquaintError(f"no entity with the id {ref!r}") from None
    if store.root is not None:
        for part in (store.root / key.split("/")[0], store.root / key):
            if part.is_symlink():
                raise AcquaintError(
                    f"{part.relative_to(store.root).as_posix()} is a link to {os.path.realpath(part)}; "
                    "acquaint does not follow links out of the store, so remove the link and its target by hand"
                )
    if store.exists(key):
        return key
    raise AcquaintError(f"no entity with the id {ref!r}")


def _references(store: Store, entity: Entity, identifiers: list[str]) -> list[dict]:
    """Other records that still name the entity: its references, its key, its full name, its handles."""
    needles = {
        entity.ref,
        f"{entity.kind_dir}:{entity.slug}",
        entity.key,
        *(i for i in identifiers if len(i) >= 4),
    }
    needles.discard(entity.slug)
    found = []
    for path in list(store.files):
        if (
            path.startswith(entity.key + "/")
            or not path.endswith((".md", ".yaml", ".yml"))
            or path == TOMBSTONES
        ):
            continue
        text = store.files[path].lower()
        mentions = sorted(n for n in needles if n.lower() in text)
        if mentions:
            found.append({"file": path, "mentions": mentions})
    return found


def forget_entity(
    store: Store, ref: str, *, confirm: bool = False, today: str | None = None
) -> dict[str, Any]:
    """Remove an entity's whole folder, hidden files included, after writing a salted tombstone.

    Without ``confirm`` it only reports what it would remove, and which other records
    still mention the entity (it does not edit them: other people's logs are append-only).
    The tombstone is written first, so a removal that fails half way still stops the
    entity being re-created, and running ``forget`` again finishes the job.
    """
    key = _forget_key(store, ref)
    entity = Entity(store, key)
    name_parts = {part.lower() for part in entity.name.split()}
    aka = [
        a for a in entity.aka if a.lower() not in name_parts
    ]  # bare name parts would block unrelated people
    identifiers = [
        entity.slug,
        entity.name,
        *aka,
        *(str(i.get("value", "")) for i in entity.identities),
    ]
    identifiers = [i for i in dict.fromkeys(identifiers) if normalize(i)]
    plan = {
        "key": key,
        "files": [f"{key}/{name}" for name in store.all_files(key)],
        "tombstone_identifiers": len({normalize(i) for i in identifiers}),
        "references": _references(
            store,
            entity,
            [i for i in identifiers if i != entity.slug and i.lower() not in name_parts],
        ),
    }
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
