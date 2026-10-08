"""Meeting todos are filed only for an unambiguous project, its registered members, and a meta repository that is private now."""

import subprocess

from acquaint import meta
from acquaint.store import Store

PROJECT = """---
name: Example Org
kind: org
github_org: example-org
---
# Example Org
"""


def _person(name, *, linked=True, github="ada-l"):
    files = {
        "PROFILE.md": f"---\nname: {name}\nkind: person\n---\n# {name}\n",
    }
    if linked:
        files["links.yaml"] = "links:\n- to: org:example-org\n  relation: member\n  since: '2026-01-01'\n  source: operator\n"
    if github:
        files["identities.yaml"] = f"identities:\n- platform: github\n  value: {github}\n  source: operator\n  status: active\n"
    return files


def _store(**people):
    files = {"orgs/example-org/PROFILE.md": PROJECT}
    for slug, entity in people.items():
        files.update({f"people/{slug}/{name}": text for name, text in entity.items()})
    return Store(files=files)


def _gh(private="true", code=0):
    def run(args, *, cwd=None):
        assert args[:2] == ["gh", "api"]
        return subprocess.CompletedProcess(args, code, private + "\n", "")

    return run


def test_all_three_conditions_hold():
    store = _store(**{"ada-lovelace": _person("Ada Lovelace")})
    found = meta.todo_preflight(store, "example-org", ["ada-lovelace"], run=_gh())
    assert found["ok"], found["problems"]
    assert (found["project"], found["meta_repo"]) == ("org:example-org", "example-org/meta")
    assert found["people"] == [{"ref": "person:ada-lovelace", "name": "Ada Lovelace", "github": "ada-l"}]


def test_each_failure_comes_with_a_fix():
    store = _store(
        **{"ada-lovelace": _person("Ada Lovelace", linked=False), "grace-hopper": _person("Grace Hopper", github=None)}
    )
    found = meta.todo_preflight(store, "example-org", ["ada-lovelace", "grace-hopper", "nobody"], run=_gh("false"))
    checks = sorted(p["check"] for p in found["problems"])
    assert not found["ok"] and checks == ["membership", "meta_repo", "person"]
    assert all(p["fix"] for p in found["problems"])
    assert any("no active github identity" in w for w in found["warnings"])


def test_an_unknown_project_or_an_unreadable_repository_is_refused():
    store = _store(**{"ada-lovelace": _person("Ada Lovelace")})
    unknown = meta.todo_preflight(store, "atlantis", ["ada-lovelace"], run=_gh())
    assert not unknown["ok"] and unknown["problems"][0]["check"] == "project"
    unreadable = meta.todo_preflight(store, "example-org", ["ada-lovelace"], run=_gh(code=1))
    assert not unreadable["ok"] and "could not be read" in unreadable["problems"][0]["message"]


def test_a_declared_meta_repo_wins_over_the_org_convention():
    store = _store(**{"ada-lovelace": _person("Ada Lovelace")})
    store.files["orgs/example-org/PROFILE.md"] = PROJECT.replace("github_org", "meta_repo: ada-l/notes\ngithub_org")
    assert meta.todo_preflight(store, "example-org", ["ada-lovelace"], run=_gh())["meta_repo"] == "ada-l/notes"
