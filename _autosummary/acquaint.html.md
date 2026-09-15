# acquaint

acquaint: people, and what they are involved in, for AI agents.

Who someone is, how to reach them, how to read them, how to write to them, kept as
hand-editable Markdown with a source on every preference, outside any code repository.

The verbs are the same in Python, on the command line (`acquaint who ada -f aka`) and
over MCP:

```default
>>> from acquaint import new, remember, who, brief
>>> new("person", "Ada Lovelace")
>>> remember("ada-lovelace", "prefers email for anything with attachments",
...          source="https://example.org/thread/1")
>>> who("ada", field="aka")["value"]
['Ada', 'Lovelace']
```

For library use, [`Store`](#acquaint.Store) is a `MutableMapping` of entities over any mapping of
files (a `dol` files store by default).

### Functions

| [`brief`](#acquaint.brief)(person, \*[, purpose, project, data_dir])    | Everything to know before writing to someone: card, writing style, reach, project norms, recent observations, gaps.                                                     |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`check`](#acquaint.check)(text, \*[, data_dir])                        | Scan prose that names people before publishing it: conflations (one person written as two), ambiguous names, unknown names.                                             |
| [`data_dir`](#acquaint.data_dir)([data_dir])                               | The data root: the argument, else `$ACQUAINT_DATA_DIR`, else `data_dir` in config.toml, else `~/.local/share/acquaint`.                                                 |
| [`forget`](#acquaint.forget)(entity, \*[, confirm, data_dir])            | Remove an entity's folder and leave a salted tombstone.                                                                                                                 |
| [`lint`](#acquaint.lint)([entity, data_dir])                           | Check records: every preference, view and rule sourced; tiers, labels and seals set by the operator; nothing POLICY.md forbids; files parse; entry files within budget. |
| [`new`](#acquaint.new)(kind, name, \*[, qualifier, description, ...]) | Create a person, project, org or group from its template (a readable slug id; `qualifier` separates two of the same name).                                              |
| [`reach`](#acquaint.reach)(person, \*[, purpose, urgency, ...])         | Ordered channels for reaching someone in a context.                                                                                                                     |
| [`remember`](#acquaint.remember)(entity, text, \*[, source, kind, ...])    | Append a dated observation (`observation`, `interaction`, `identity`, `preference`, `view`, `rule`) to an entity's log, with its source.                                |
| [`rename`](#acquaint.rename)(entity, to, \*[, data_dir])                 | Change an entity's id (`to` is a slug) or name and id (`to` is a name), rewriting links to it.                                                                          |
| [`resolve`](#acquaint.resolve)(handle, \*[, data_dir])                    | Map a channel handle (`github:octocat`, `email:ada@example.org`) to the entity it belongs to, with the evidence.                                                        |
| [`style_lint`](#acquaint.style_lint)(text, \*[, recipient, tolerance, ...])  | The deterministic half of deslop: machine-writing tells in a draft, at the recipient's tolerance and against their blocklist.                                           |
| [`sync_init`](#acquaint.sync_init)(\*, repo[, remote_url, ...])             | Make the data root a checkout of a PRIVATE GitHub repository (created private through `gh` unless `existing_only`), with a pre-push guard.                              |
| [`sync_pull`](#acquaint.sync_pull)(\*[, dry_run, data_dir])                 | Pull the store from its private remote, rebasing local work on top.                                                                                                     |
| [`sync_push`](#acquaint.sync_push)(\*[, message, dry_run, data_dir])        | Commit, rebase onto the remote and push the store, after re-checking the remote, the guard and the visibility.                                                          |
| [`sync_status`](#acquaint.sync_status)(\*[, check_visibility, data_dir])      | Whether the store is synced, to which repository, uncommitted changes, ahead/behind, the guard, and live visibility.                                                    |
| [`who`](#acquaint.who)(name, \*[, field, brief, data_dir])            | Look up one person, project, org or group by exact id, name, alias, handle or email.                                                                                    |

### Classes

| [`Entity`](#acquaint.Entity)(store, key)       | One person, project, org or group: a mapping of its files (relative names to text), plus parsed views of them.   |
|---------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| [`Store`](#acquaint.Store)([data_dir, files]) | `MutableMapping[str, Entity]` over one folder per entity, keyed `"<kind dir>/<slug>"`.                           |

### Exceptions

| [`AcquaintError`](#acquaint.AcquaintError)   | An expected failure with a message meant for the person or agent that asked.   |
|------------------------------------------------------------------|--------------------------------------------------------------------------------|

### *exception* acquaint.AcquaintError

Bases: [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)

An expected failure with a message meant for the person or agent that asked.

### *class* acquaint.Entity(store, key)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

One person, project, org or group: a mapping of its files (relative names to text), plus parsed views of them.

Parsed views are recomputed on access (these are small text files), so an edit made
through the mapping is never hidden behind a stale cache. Parse problems are collected
in [`errors`](#acquaint.Entity.errors); they never raise.

#### *property* aka *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Other names this entity goes by, as strings (a scalar `aka` is one alias, not its letters).

#### *property* body *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The entry file’s Markdown body.

#### *property* errors *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Everything about the entry file and the YAML files that did not parse.

#### *property* identities *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[dict](https://docs.python.org/3/builtins/stdtypes.html#dict)]*

`{platform, value, source, status, …}`.

* **Type:**
  Handles and addresses from `identities.yaml`

#### *property* kind *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`person`, `project`, `org`, `group`, or the singular of an open kind’s folder.

#### *property* links *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[dict](https://docs.python.org/3/builtins/stdtypes.html#dict)]*

`{to, relation, role, since, until, source}`.

* **Type:**
  Affiliations from `links.yaml`

#### *property* meta *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)*

The entry file’s frontmatter (empty when it did not parse).

#### *property* name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The display name, falling back to the id.

#### *property* ref *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`person:ada-lovelace`.

* **Type:**
  The link form other records use

#### *property* rules *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[dict](https://docs.python.org/3/builtins/stdtypes.html#dict)]*

`{when, do, set_by, source}`.

* **Type:**
  Channel and communication rules from `rules.yaml`

#### *property* sections *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

The entry file’s `## Sections`, keyed by normalized title.

#### summary()

The identity block: frontmatter plus identities, JSON-ready.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

#### *property* surface_forms *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

id, name, aka, name parts, handles.

* **Type:**
  Every string a document might use for this entity

#### text(name, default='')

A file’s text, or `default` when the file does not exist.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### *property* trust *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[dict](https://docs.python.org/3/builtins/stdtypes.html#dict)]*

`{tier, valid_from, valid_to, review_by, recorded, source, note}` (see [`acquaint.trust`](acquaint.trust.html.md#module-acquaint.trust)).

* **Type:**
  Disclosure tiers from `trust.yaml`

### *class* acquaint.Store(data_dir=None, , files=None)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

`MutableMapping[str, Entity]` over one folder per entity, keyed `"<kind dir>/<slug>"`.

```pycon
>>> store = Store(files={})
>>> store["projects/example"] = {"PROFILE.md": "---\nname: Example\n---\n"}
>>> store.find("project:example"), store.find("example")
('projects/example', 'projects/example')
```

#### all_files(key)

Every file under the entity’s folder, hidden ones included.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### append_text(key, name, text)

Append to one of an entity’s files (created if missing); a true append on disk, so concurrent writers do not erase each other.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### exists(key)

Whether anything is stored under the entity’s folder, with or without an entry file.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### find(ref)

The store key for `people/ada-lovelace`, `person:ada-lovelace` or a bare `ada-lovelace`.

A bare id that names entities of two kinds is an error: say which, e.g.
`project:atlas`. Anything that is not a valid key raises `KeyError`, so no
reference reaches outside the data root.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### find_id(slug)

Every key whose id is `slug`, in any kind (ids are lowercase, so the lookup is too).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### location_warning()

A warning when the data root is, or sits inside, a git repository that is not an acquaint store.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### misnamed()

Entry files on disk the store cannot address: a folder or file name not in lowercase `kind/id/PROFILE.md` form, or a linked folder.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### move(src, dst)

Move an entity’s whole folder to a new key (hidden files included).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### path_of(key)

Where an entity lives, for a person to open: a real path when on disk, else the key.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### acquaint.brief(person, , purpose=None, project=None, data_dir=None)

Everything to know before writing to someone: card, writing style, reach, project norms, recent observations, gaps.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.check(text, , data_dir=None)

Scan prose that names people before publishing it: conflations (one person written as two), ambiguous names, unknown names.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.data_dir(data_dir=None)

The data root: the argument, else `$ACQUAINT_DATA_DIR`, else `data_dir` in config.toml, else `~/.local/share/acquaint`.

An explicit argument may be relative (it is resolved now). The environment variable
and the config file must hold absolute paths: a relative one would put profiles
wherever the current directory happens to be.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

```pycon
>>> data_dir("profiles").is_absolute()
True
```

### acquaint.forget(entity, , confirm=False, data_dir=None)

Remove an entity’s folder and leave a salted tombstone. Needs the exact id; without `confirm`, only reports what would be removed.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.lint(entity=None, , data_dir=None)

Check records: every preference, view and rule sourced; tiers, labels and seals set by the operator; nothing POLICY.md forbids; files parse; entry files within budget.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.new(kind, name, , qualifier=None, description=None, force=False, data_dir=None)

Create a person, project, org or group from its template (a readable slug id; `qualifier` separates two of the same name).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.reach(person, , purpose=None, urgency=None, project=None, message_type=None, topic=None, data_dir=None)

Ordered channels for reaching someone in a context. Only active addresses; returns them, sends nothing. `outcome` is `reachable`, `no_address` (a rule matched, but no usable address is recorded for its channels) or `no_channel`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.remember(entity, text, , source=None, kind='observation', reactivate=False, data_dir=None)

Append a dated observation (`observation`, `interaction`, `identity`, `preference`, `view`, `rule`) to an entity’s log, with its source. An identity equal to an inactive one (`stale`, `retracted`, …) is refused, naming that entry and the command with which the operator can make it active again.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.rename(entity, to, , data_dir=None)

Change an entity’s id (`to` is a slug) or name and id (`to` is a name), rewriting links to it. Needs the exact id.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.resolve(handle, , data_dir=None)

Map a channel handle (`github:octocat`, `email:ada@example.org`) to the entity it belongs to, with the evidence.

`ok` is true only when an active identity on the named platform belongs to exactly
one entity. A handle without a platform (`@octocat`), a match by name only, an
inactive identity, or several owners all return `ok: false` with what was found.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.style_lint(text, , recipient=None, tolerance=None, data_dir=None)

The deterministic half of deslop: machine-writing tells in a draft, at the recipient’s tolerance and against their blocklist.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.sync_init(, repo, remote_url=None, existing_only=False, dry_run=False, data_dir=None)

Make the data root a checkout of a PRIVATE GitHub repository (created private through `gh` unless `existing_only`), with a pre-push guard.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.sync_pull(, dry_run=False, data_dir=None)

Pull the store from its private remote, rebasing local work on top.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.sync_push(, message=None, dry_run=False, data_dir=None)

Commit, rebase onto the remote and push the store, after re-checking the remote, the guard and the visibility.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.sync_status(, check_visibility=True, data_dir=None)

Whether the store is synced, to which repository, uncommitted changes, ahead/behind, the guard, and live visibility.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.who(name, , field=None, brief=False, data_dir=None)

Look up one person, project, org or group by exact id, name, alias, handle or email.

Costs scale with what you ask: `field` returns one value (`aka`, `email`,
`github`, `label`, `tier`, any frontmatter key), `brief` the identity block, and the default the
whole entry file. It never guesses: no exact match, or several, returns the
candidates and `ok: false`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### Modules

| [`deslop`](acquaint.deslop.html.md#module-acquaint.deslop)       | The deterministic half of deslop: find the patterns that make prose read as machine-written, scaled to the reader.                                                               |
|--------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`edit`](acquaint.edit.html.md#module-acquaint.edit)           | Changing the store: create an entity, append an observation, rename with relinking, forget with a tombstone.                                                                     |
| [`lookup`](acquaint.lookup.html.md#module-acquaint.lookup)       | Finding the right record: exact references, handle resolution, the conflation check, and channel choice.                                                                         |
| [`mcp`](acquaint.mcp.html.md#module-acquaint.mcp)             | MCP over stdio: the same tools, for Claude Desktop and other local MCP clients.                                                                                                  |
| [`records`](acquaint.records.html.md#module-acquaint.records)     | The text formats acquaint stores, as pure functions: frontmatter, sections, items, source tags, slugs, log entries.                                                              |
| [`render`](acquaint.render.html.md#module-acquaint.render)       | Turning a tool's result into terminal output: `(stdout, stderr, exit code)`.                                                                                                     |
| [`resources`](acquaint.resources.html.md#module-acquaint.resources) | Files shipped inside the package: record templates, the policy tripwires, purpose reminders, the tells catalogue, skills.                                                        |
| [`store`](acquaint.store.html.md#module-acquaint.store)         | Where records live and how code reaches them: the data root, [`Store`](#acquaint.Store) and [`Entity`](#acquaint.Entity). |
| [`sync`](acquaint.sync.html.md#module-acquaint.sync)           | Private-repository sync for the data root: create the repository private, refuse anything else, guard every push.                                                                |
| [`tools`](acquaint.tools.html.md#module-acquaint.tools)         | The single source of truth for every surface: plain functions, flat arguments in, JSON-ready dicts out.                                                                          |
| [`trust`](acquaint.trust.html.md#module-acquaint.trust)         | The disclosure vocabulary: tiers on people; labels, seals and clearances on records; and which tier is in force.                                                                 |
