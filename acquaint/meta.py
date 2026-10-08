"""Where a project's meeting todos may be filed: its declared private meta repository, and the people who belong to it.

Before agents file todos from a meeting as GitHub issues, three things must hold, and
:func:`todo_preflight` checks them against the store and the live repository:

1. **the project is unambiguous**: exactly one ``project`` or ``org`` record matches;
2. **every participant is registered and belongs to it**: each resolves to exactly one
   person whose ``links.yaml`` links them to that project or org;
3. **the project declares a private meta repository**: ``meta_repo: owner/name`` in the
   record's frontmatter, or ``github_org: <org>``, which means ``<org>/meta``; and ``gh``
   reports that repository private now.

Every failed check comes back as a problem with a concrete fix, so the skill can tell the
user how to proceed instead of guessing. Each participant's GitHub login (an active
``github`` identity) is returned for assigning issues, with a warning when there is none.

>>> meta_repo_of({"github_org": "example-org"})
'example-org/meta'
>>> meta_repo_of({"meta_repo": "ada-lovelace/notes", "github_org": "example-org"})
'ada-lovelace/notes'
>>> meta_repo_of({}) is None
True
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from acquaint.lookup import find_entity
from acquaint.store import AcquaintError, Store
from acquaint.sync import Runner, run_command

__all__ = ["META_REPO_NAME", "meta_repo_of", "repo_privacy", "todo_preflight"]

#: The repository name a declared ``github_org`` implies.
META_REPO_NAME = "meta"
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$")
_PROJECT_KINDS = {"project", "org"}


def meta_repo_of(meta: Mapping[str, Any]) -> str | None:
    """The meta repository a record's frontmatter declares: ``meta_repo``, else ``<github_org>/meta``, else ``None``."""
    declared = str(meta.get("meta_repo") or "").strip()
    if declared:
        return declared
    org = str(meta.get("github_org") or "").strip()
    return f"{org}/{META_REPO_NAME}" if org else None


def repo_privacy(repo: str, *, run: Runner = run_command) -> tuple[bool | None, str]:
    """``(True, …)`` if ``gh`` reports the repository private now, ``(False, …)`` if not, ``(None, why)`` if it could not tell."""
    found = run(["gh", "api", f"repos/{repo}", "--jq", ".private"])
    if found.returncode != 0:
        return None, f"{repo} could not be read through gh (missing, or no access)"
    answer = (found.stdout or "").strip()
    if answer == "true":
        return True, f"{repo} is private"
    if answer == "false":
        return False, f"{repo} is public"
    return None, f"unexpected answer from gh about {repo}: {answer!r}"


def _linked_to(person, target_ref: str) -> bool:
    return any(
        str(link.get("to", "")).strip().lower() == target_ref
        and not str(link.get("until") or "").strip()
        for link in person.links
    )


def _github_login(person) -> str | None:
    for identity in person.identities:
        if str(identity.get("platform", "")).lower() == "github" and str(
            identity.get("status") or "active"
        ).lower() == "active":
            return str(identity.get("value", "")).strip() or None
    return None


def todo_preflight(
    store: Store,
    project: str,
    people: Iterable[str],
    *,
    run: Runner = run_command,
) -> dict[str, Any]:
    """Check that meeting todos for ``project`` and ``people`` may be filed, and where.

    Returns ``ok``, the resolved ``project`` reference, the ``meta_repo``, one row per
    participant (``ref``, ``github``), ``problems`` (each a ``check``, a ``message`` and a
    ``fix``) and ``warnings``. ``ok`` is false whenever any problem is found.
    """
    problems: list[dict[str, str]] = []
    warnings: list[str] = []

    def problem(check: str, message: str, fix: str) -> None:
        problems.append({"check": check, "message": message, "fix": fix})

    entity = None
    try:
        key = find_entity(store, project)
        entity = store[key]
        if entity.kind not in _PROJECT_KINDS:
            problem(
                "project",
                f"{project!r} is a {entity.kind} record, not a project or org",
                f"name the project or company itself (`acquaint who {project}` lists what matched)",
            )
            entity = None
    except (AcquaintError, KeyError) as error:
        problem(
            "project",
            f"no single project or org record for {project!r} ({error})",
            f"register it: `acquaint new org \"{project}\"` (a company) or "
            f"`acquaint new project \"{project}\"`, or name the existing one by id (`org:<id>`)",
        )
    target = entity.ref if entity is not None else None

    repo = None
    if entity is not None:
        repo = meta_repo_of(entity.meta)
        if repo is None:
            problem(
                "meta_repo",
                f"{target} declares no meta repository",
                f"add `meta_repo: <owner>/<name>` (any private repository) or `github_org: <org>` "
                f"(meaning <org>/{META_REPO_NAME}) to the frontmatter of {entity.key}/PROFILE.md",
            )
        elif not _REPO_RE.match(repo):
            problem("meta_repo", f"{repo!r} is not an owner/name repository", f"fix the meta_repo value in {entity.key}/PROFILE.md")
            repo = None
        else:
            private, why = repo_privacy(repo, run=run)
            if private is not True:
                problem(
                    "meta_repo",
                    why,
                    f"create it private (`gh repo create {repo} --private`) or make it private "
                    f"(`gh repo edit {repo} --visibility private --accept-visibility-change-consequences`); "
                    "todos are never filed in a repository that is not private",
                )

    rows = []
    for name in people:
        name = name.strip()
        if not name:
            continue
        try:
            person = store[find_entity(store, name)]
        except (AcquaintError, KeyError) as error:
            problem(
                "person",
                f"{name!r} is not one registered person ({error})",
                f"register them (`acquaint new person \"{name}\"`) or name the existing record by id",
            )
            continue
        if person.kind != "person":
            problem("person", f"{name!r} is a {person.kind} record, not a person", "name the person")
            continue
        login = _github_login(person)
        if login is None:
            warnings.append(
                f"{person.ref} has no active github identity: their issue cannot be assigned "
                f"(add one to {person.key}/identities.yaml)"
            )
        if target is not None and not _linked_to(person, target):
            problem(
                "membership",
                f"{person.ref} is not linked to {target}",
                f"add to {person.key}/links.yaml: `- {{to: {target}, relation: <their role>, since: <date>, source: <where you learned it>}}`",
            )
        rows.append({"ref": person.ref, "name": person.name, "github": login})

    if not rows and not any(p["check"] == "person" for p in problems):
        problem("person", "no participants given", "list the people the todos belong to")

    return {
        "ok": not problems,
        "project": target,
        "meta_repo": repo,
        "people": rows,
        "problems": problems,
        "warnings": warnings,
    }
