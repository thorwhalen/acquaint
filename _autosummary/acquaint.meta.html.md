# acquaint.meta

Where a project’s meeting todos may be filed: its declared private meta repository, and the people who belong to it.

Before agents file todos from a meeting as GitHub issues, three things must hold, and
[`todo_preflight()`](#acquaint.meta.todo_preflight) checks them against the store and the live repository:

1. **the project is unambiguous**: exactly one `project` or `org` record matches;
2. **every participant is registered and belongs to it**: each resolves to exactly one
   person whose `links.yaml` links them to that project or org;
3. **the project declares a private meta repository**: `meta_repo: owner/name` in the
   record’s frontmatter, or `github_org: <org>`, which means `<org>/meta`; and `gh`
   reports that repository private now.

Every failed check comes back as a problem with a concrete fix, so the skill can tell the
user how to proceed instead of guessing. Each participant’s GitHub login (an active
`github` identity) is returned for assigning issues, with a warning when there is none.

```pycon
>>> meta_repo_of({"github_org": "example-org"})
'example-org/meta'
>>> meta_repo_of({"meta_repo": "ada-lovelace/notes", "github_org": "example-org"})
'ada-lovelace/notes'
>>> meta_repo_of({}) is None
True
```

### Module Attributes

| [`META_REPO_NAME`](#acquaint.meta.META_REPO_NAME)   | The repository name a declared `github_org` implies.   |
|-------------------------------------------------------------------|--------------------------------------------------------|

### Functions

| [`meta_repo_of`](#acquaint.meta.meta_repo_of)(meta)                                | The meta repository a record's frontmatter declares: `meta_repo`, else `<github_org>/meta`, else `None`.         |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| [`repo_privacy`](#acquaint.meta.repo_privacy)(repo, \*[, run])                     | `(True, …)` if `gh` reports the repository private now, `(False, …)` if not, `(None, why)` if it could not tell. |
| [`todo_preflight`](#acquaint.meta.todo_preflight)(store, project, people, \*[, run]) | Check that meeting todos for `project` and `people` may be filed, and where.                                     |

### acquaint.meta.META_REPO_NAME *= 'meta'*

The repository name a declared `github_org` implies.

### acquaint.meta.meta_repo_of(meta)

The meta repository a record’s frontmatter declares: `meta_repo`, else `<github_org>/meta`, else `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### acquaint.meta.repo_privacy(repo, \*, run=<function run_command>)

`(True, …)` if `gh` reports the repository private now, `(False, …)` if not, `(None, why)` if it could not tell.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`bool`](https://docs.python.org/3/builtins/functions.html#bool) | [`None`](https://docs.python.org/3/builtins/constants.html#None), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### acquaint.meta.todo_preflight(store, project, people, \*, run=<function run_command>)

Check that meeting todos for `project` and `people` may be filed, and where.

Returns `ok`, the resolved `project` reference, the `meta_repo`, one row per
participant (`ref`, `github`), `problems` (each a `check`, a `message` and a
`fix`) and `warnings`. `ok` is false whenever any problem is found.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
