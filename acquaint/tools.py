"""The single source of truth for every surface: plain functions, flat arguments in, JSON-ready dicts out.

The CLI is ``cw`` over :data:`TOOLS`; the MCP server registers ``acquaint.tools:<name>``
string references to the same functions; the shipped skills describe these verbs.
Nothing in this module knows about any of those surfaces.

Every tool takes ``data_dir`` (default: ``$ACQUAINT_DATA_DIR``, else ``data_dir`` in
``~/.config/acquaint/config.toml``, else ``~/.local/share/acquaint``). Every result
carries ``ok`` and a one-line ``summary``; long human-readable content is in ``text``.
Expected failures (no such person, an unsourced preference) come back as ``ok: False``
or raise :class:`~acquaint.store.AcquaintError` with a message meant for the caller.
"""

from __future__ import annotations

from typing import Any

from acquaint import sync as _sync
from acquaint.brief import compose_brief
from acquaint.deslop import lint_text, recipient_card
from acquaint.edit import append_observation, forget_entity, new_entity, rename_entity
from acquaint.lint import lint_store
from acquaint.lookup import check_text, match, reach_channels, resolve_handle
from acquaint.store import ENTRY_FILE, AcquaintError, Entity, Store, data_dir as _data_dir

__all__ = [
    "AcquaintError",
    "SIDE_EFFECTS",
    "TOOLS",
    "brief",
    "check",
    "forget",
    "lint",
    "new",
    "reach",
    "remember",
    "rename",
    "resolve",
    "style_lint",
    "sync_init",
    "sync_pull",
    "sync_push",
    "sync_status",
    "who",
]


def _store(data_dir: str | None) -> Store:
    return Store(data_dir)


def _key(store: Store, ref: str) -> str:
    try:
        return store.find(ref)
    except KeyError:
        pass
    found = match(store, ref)
    keys = found["exact"] or found["partial"]
    if len(keys) == 1:
        return keys[0]
    if keys:
        raise AcquaintError(f"{ref!r} could be {', '.join(k.split('/', 1)[1] for k in keys)}; say which")
    raise AcquaintError(f"no entity {ref!r}; `acquaint new person \"Given Family\"` creates one")


def _field(store: Store, entity: Entity, field: str) -> Any:
    field = field.strip().lower()
    by_platform = lambda platform: [i.get("value") for i in entity.identities if str(i.get("platform", "")).lower() == platform]  # noqa: E731
    if field in entity.meta:
        return entity.meta[field]
    if field in {"email", "emails"}:
        return by_platform("email")
    if field in {"identities", "rules", "links"}:
        return getattr(entity, field)
    if field == "path":
        return store.path_of(entity.key)
    if field == "files":
        return list(entity)
    return by_platform(field) or None


# --------------------------------------------------------------------- read tools


def who(name: str, *, field: str | None = None, brief: bool = False, data_dir: str | None = None) -> dict:
    """Look up one person, project, org or group by name, alias, handle, email or id.

    Costs scale with what you ask: ``field`` returns one value (``aka``, ``email``,
    ``github``, any frontmatter key), ``brief`` the identity block, and the default the
    whole entry file. Several matches return the candidates instead of a guess.
    """
    store = _store(data_dir)
    found = match(store, name)
    try:
        keys = [store.find(name)] if (":" in name or "/" in name) else (found["exact"] or found["partial"])
    except (KeyError, AcquaintError):
        keys = []
    if not keys:
        known = [k.split("/", 1)[1] for k in list(store)[:20]]
        return {"ok": False, "query": name, "known": known, "summary": f"no match for {name!r}; known: {', '.join(known) or '(store is empty)'}"}
    if len(keys) > 1:
        candidates = [{"id": store[k].slug, "key": k, "name": store[k].name} for k in keys]
        return {"ok": False, "query": name, "candidates": candidates, "summary": f"{name!r} is ambiguous: {', '.join(c['id'] for c in candidates)}"}

    entity = store[keys[0]]
    base = {"ok": True, "id": entity.slug, "key": entity.key, "name": entity.name}
    if entity.errors:
        base["warnings"] = [f"{entity.key}: {e}" for e in entity.errors]
    if field:
        value = _field(store, entity, field)
        if value in (None, [], ""):
            return {**base, "ok": False, "field": field, "summary": f"{entity.slug} has no recorded {field!r}"}
        shown = ", ".join(map(str, value)) if isinstance(value, list) else value
        return {**base, "field": field, "value": value, "summary": f"{entity.slug} {field}: {shown}"}
    identity = entity.summary()
    if brief:
        lines = [f"{entity.name} ({entity.ref})"] + [f"{k}: {v}" for k, v in identity.items() if k not in {"id", "key", "kind", "name", "schema"} and v not in (None, "", [])]
        return {**base, "identity": identity, "summary": lines[0], "text": "\n".join(lines)}
    return {**base, "identity": identity, "path": store.path_of(entity.key), "files": list(entity), "summary": f"{entity.name} ({entity.ref})", "text": entity.text(ENTRY_FILE)}


def resolve(handle: str, *, data_dir: str | None = None) -> dict:
    """Map a channel handle (``github:octocat``, ``email:ada@example.org``, ``@octocat``) to the entity it belongs to, with the evidence."""
    matches = resolve_handle(_store(data_dir), handle)
    ids = sorted({m["id"] for m in matches})
    ok = len(ids) == 1
    summary = (
        f"{handle} → {ids[0]}" if ok else f"{handle} matches {', '.join(ids)}: do not pick one" if ids else f"{handle} matches no recorded identity"
    )
    text = "\n".join(f"{m['id']}  {m.get('platform') or 'name'}:{m.get('value', m['name'])}  evidence: {m['evidence']}" for m in matches)
    return {"ok": ok, "handle": handle, "matches": matches, "summary": summary, "text": text or summary}


def check(text: str, *, data_dir: str | None = None) -> dict:
    """Scan prose that names people before publishing it: conflations (one person written as two), ambiguous names, unknown names."""
    result = check_text(_store(data_dir), text)
    lines = [
        f"CONFLATION  {c['name']} is ONE entity, written as {' / '.join(repr(f) for f in c['forms'])}: …{c['excerpt']}…"
        for c in result["conflations"]
    ]
    lines += [f"AMBIGUOUS   {a['form']!r} could be {', '.join(a['ids'])}" for a in result["ambiguous"]]
    if result["unknown_candidates"]:
        lines.append(f"UNKNOWN     name-like phrases in no record: {', '.join(result['unknown_candidates'])}")
    if result["mentioned"]:
        lines.append(f"mentioned   {', '.join(result['mentioned'])}")
    ok = not result["conflations"]
    summary = "no conflations" if ok else f"{len(result['conflations'])} conflation(s)"
    return {"ok": ok, **result, "summary": summary, "text": "\n".join(lines) or summary}


def reach(
    person: str,
    *,
    purpose: str | None = None,
    urgency: str | None = None,
    project: str | None = None,
    message_type: str | None = None,
    topic: str | None = None,
    data_dir: str | None = None,
) -> dict:
    """Ordered channels for reaching someone in a context. Returns addresses; sends nothing."""
    store = _store(data_dir)
    key = _key(store, person)
    defaults = store.files["_defaults/rules.yaml"] if "_defaults/rules.yaml" in store.files else ""
    result = reach_channels(store, key, defaults_text=defaults, purpose=purpose, urgency=urgency, project=project, message_type=message_type, topic=topic)
    lines = [
        f"{n}. {c['channel'] or c['instruction']}" + (f" → {c['address']}" if c["address"] else "") + f"  [{c['tier']}]"
        for n, c in enumerate(result["channels"], start=1)
    ]
    summary = f"{len(result['channels'])} channel(s) for {store[key].slug}" if lines else f"no identities or rules recorded for {store[key].slug}"
    return {"ok": bool(lines), "id": store[key].slug, **result, "summary": summary, "text": "\n".join(lines) or summary}


def brief(person: str, *, purpose: str | None = None, project: str | None = None, data_dir: str | None = None) -> dict:
    """Everything to know before writing to someone: card, writing style, reach, project norms, recent observations, gaps."""
    store = _store(data_dir)
    result = compose_brief(store, _key(store, person), purpose=purpose, project=project)
    return {"ok": True, **result, "summary": f"brief for {result['name']}" + (f" ({purpose})" if purpose else "")}


def lint(entity: str | None = None, *, data_dir: str | None = None) -> dict:
    """Check records: every preference, view and rule sourced; nothing POLICY.md forbids; files parse; entry files within budget."""
    store = _store(data_dir)
    result = lint_store(store, _key(store, entity) if entity else None)
    lines = [
        f"{f['severity']:7} {f['entity']}/{f['file']}" + (f":{f['line']}" if f["line"] else "") + f"  {f['rule']}: {f['message']}"
        for f in result["errors"] + result["warnings"]
    ]
    ok = not result["errors"]
    summary = f"{result['checked']} checked, {len(result['errors'])} error(s), {len(result['warnings'])} warning(s)"
    return {"ok": ok, **result, "summary": summary, "text": "\n".join(lines + [summary])}


def style_lint(text: str, *, recipient: str | None = None, tolerance: str | None = None, data_dir: str | None = None) -> dict:
    """The deterministic half of deslop: machine-writing tells in a draft, at the recipient's tolerance and against their blocklist."""
    card = {"tolerance": "unknown", "blocklist": []}
    if recipient:
        store = _store(data_dir)
        card = recipient_card(store[_key(store, recipient)])
    level = tolerance or card["tolerance"]
    result = lint_text(text, tolerance=level, blocklist=card["blocklist"])
    route = (
        result["relational_message"] if result["relational"]
        else "operator approves; an explicit disclosure decision is required" if level == "averse"
        else "no special handling" if level == "tolerant"
        else "operator approves before sending"
    )
    enforced = [f for f in result["findings"] if f["enforced"]]
    lines = [f"{f['tier']} {f['rule']}: {f['message']}" + (f"  …{f['excerpt']}…" if f["excerpt"] else "") for f in enforced]
    summary = f"{len(enforced)} finding(s) to fix at tolerance {level}; route: {route}"
    return {**result, "recipient": recipient, "route": route, "summary": summary, "text": "\n".join(lines + [summary])}


# -------------------------------------------------------------------- write tools


def remember(entity: str, text: str, *, source: str | None = None, kind: str = "observation", data_dir: str | None = None) -> dict:
    """Append a dated observation (``observation``, ``interaction``, ``identity``, ``preference``, ``view``, ``rule``) to an entity's log, with its source."""
    store = _store(data_dir)
    result = append_observation(store, _key(store, entity), text, source=source, kind=kind)
    return {"ok": True, **result, "summary": f"recorded {result['kind']} {result['ref']} for {result['id']}"}


def new(kind: str, name: str, *, qualifier: str | None = None, description: str | None = None, force: bool = False, data_dir: str | None = None) -> dict:
    """Create a person, project, org or group from its template (a readable slug id; ``qualifier`` separates two of the same name)."""
    result = new_entity(_store(data_dir), kind, name, qualifier=qualifier, description=description, force=force)
    return {"ok": True, **result, "summary": f"created {result['key']} at {result['path']}"}


def rename(entity: str, to: str, *, data_dir: str | None = None) -> dict:
    """Change an entity's id (``to`` is a slug) or name and id (``to`` is a name), rewriting links to it; the old forms become aliases."""
    store = _store(data_dir)
    result = rename_entity(store, _key(store, entity), to)
    return {"ok": True, **result, "summary": f"renamed {result['from']} → {result['to']}; relinked {len(result['relinked'])} file(s)"}


def forget(entity: str, *, confirm: bool = False, data_dir: str | None = None) -> dict:
    """Remove an entity and leave a hashed tombstone. Without ``confirm``, only reports what would be removed."""
    store = _store(data_dir)
    result = forget_entity(store, _key(store, entity), confirm=confirm)
    if not result["done"]:
        summary = f"would remove {len(result['files'])} file(s) of {result['key']}; pass --confirm to do it"
        return {"ok": True, **result, "summary": summary, "text": "\n".join([*result["files"], summary])}
    return {"ok": True, **result, "summary": f"forgot {result['key']}", "text": "\n".join([f"forgot {result['key']}", *result["history_rewrite"]])}


# ------------------------------------------------------------------------- sync


def sync_init(*, repo: str, remote_url: str | None = None, existing_only: bool = False, dry_run: bool = False, data_dir: str | None = None) -> dict:
    """Make the data root a checkout of a PRIVATE GitHub repository (created private through ``gh`` unless ``existing_only``), with a pre-push visibility guard."""
    result = _sync.init(_data_dir(data_dir), repo, remote_url=remote_url, create=not existing_only, dry_run=dry_run)
    if dry_run:
        return {"ok": True, **result, "summary": f"dry run: would sync the store to {repo}", "text": "\n".join(result["plan"])}
    return {"ok": True, **result, "summary": f"store synced to {repo} ({result['visibility']}); pre-push guard installed"}


def sync_push(*, message: str | None = None, dry_run: bool = False, data_dir: str | None = None) -> dict:
    """Commit, rebase onto the remote and push the store, after re-checking that the remote is the recorded, private one."""
    result = _sync.push(_data_dir(data_dir), message=message, dry_run=dry_run)
    summary = f"would commit {result['would_commit']} change(s)" if dry_run else f"pushed to {result['repo']}" if result.get("pushed") else result.get("note", "nothing pushed")
    return {"ok": True, **result, "summary": summary}


def sync_pull(*, dry_run: bool = False, data_dir: str | None = None) -> dict:
    """Pull the store from its private remote, rebasing local work on top."""
    result = _sync.pull(_data_dir(data_dir), dry_run=dry_run)
    return {"ok": True, **result, "summary": "dry run: " + "; ".join(result["plan"]) if dry_run else f"pulled {result['repo']} at {result['head']}"}


def sync_status(*, check_visibility: bool = True, data_dir: str | None = None) -> dict:
    """Whether the store is synced, to which repository, uncommitted changes, ahead/behind, the hook, and live visibility."""
    result = _sync.status(_data_dir(data_dir), check_visibility=check_visibility)
    if not result["synced"]:
        return {"ok": True, **result, "summary": result["note"]}
    problems = [p for p, bad in (("visibility is not PRIVATE", result.get("visibility", "PRIVATE") != "PRIVATE"), ("pre-push guard missing or changed", not result["hook_installed"])) if bad]
    lines = [f"{k}: {v}" for k, v in result.items() if k not in {"synced"}]
    return {"ok": not problems, **result, "problems": problems, "summary": "; ".join(problems) or f"synced to {result['repo']}", "text": "\n".join(lines + problems)}


#: Every tool, in the order surfaces list them.
TOOLS = [who, resolve, check, reach, brief, remember, lint, new, rename, forget, sync_init, sync_push, sync_pull, sync_status, style_lint]

#: What each tool changes, for surfaces that must decide what to expose or confirm.
#: ``read`` changes nothing; ``append`` adds to a log; ``create`` adds a record;
#: ``rewrite`` changes existing records; ``destructive`` removes data; ``external``
#: acts on a remote service.
SIDE_EFFECTS = {
    "who": "read", "resolve": "read", "check": "read", "reach": "read", "brief": "read",
    "lint": "read", "style_lint": "read", "sync_status": "read",
    "remember": "append", "new": "create",
    "rename": "rewrite", "sync_pull": "rewrite",
    "forget": "destructive",
    "sync_init": "external", "sync_push": "external",
}
