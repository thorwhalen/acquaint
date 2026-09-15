# acquaint.tools

The single source of truth for every surface: plain functions, flat arguments in, JSON-ready dicts out.

The CLI is `cw` over [`TOOLS`](#acquaint.tools.TOOLS); the MCP server exposes the same functions (by
`acquaint.tools:<name>` reference); the shipped skills describe these verbs. Nothing
in this module knows about any of those surfaces.

Every tool takes `data_dir` (default: `$ACQUAINT_DATA_DIR`, else `data_dir` in
`~/.config/acquaint/config.toml`, else `~/.local/share/acquaint`). Every result carries
`ok` and a one-line `summary`; long human-readable content is in `text`.

Tools never act on a guess. A name, alias, handle or email counts only when exactly one
entity has it exactly; a partial match is returned as a suggestion. `rename` and
`forget` need the exact id. Library callers with their own store use the core
functions ([`acquaint.lookup.find_entity()`](acquaint.lookup.html.md#acquaint.lookup.find_entity), `acquaint.brief.compose_brief()`, …)
with a [`Store`](acquaint.store.html.md#acquaint.store.Store).

### Module Attributes

| [`TOOLS`](#acquaint.tools.TOOLS)        | Every tool, in the order surfaces list them.                                     |
|---------------------------------------------------------------|----------------------------------------------------------------------------------|
| [`SIDE_EFFECTS`](#acquaint.tools.SIDE_EFFECTS) | What each tool changes, for surfaces that must decide what to expose or confirm. |

### Functions

| [`brief`](#acquaint.tools.brief)(person, \*[, purpose, project, data_dir])    | Everything to know before writing to someone: card, writing style, reach, project norms, recent observations, gaps.                                                     |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`check`](#acquaint.tools.check)(text, \*[, data_dir])                        | Scan prose that names people before publishing it: conflations (one person written as two), ambiguous names, unknown names.                                             |
| [`forget`](#acquaint.tools.forget)(entity, \*[, confirm, data_dir])            | Remove an entity's folder and leave a salted tombstone.                                                                                                                 |
| [`lint`](#acquaint.tools.lint)([entity, data_dir])                           | Check records: every preference, view and rule sourced; tiers, labels and seals set by the operator; nothing POLICY.md forbids; files parse; entry files within budget. |
| [`new`](#acquaint.tools.new)(kind, name, \*[, qualifier, description, ...]) | Create a person, project, org or group from its template (a readable slug id; `qualifier` separates two of the same name).                                              |
| [`reach`](#acquaint.tools.reach)(person, \*[, purpose, urgency, ...])         | Ordered channels for reaching someone in a context.                                                                                                                     |
| [`remember`](#acquaint.tools.remember)(entity, text, \*[, source, kind, ...])    | Append a dated observation (`observation`, `interaction`, `identity`, `preference`, `view`, `rule`) to an entity's log, with its source.                                |
| [`rename`](#acquaint.tools.rename)(entity, to, \*[, data_dir])                 | Change an entity's id (`to` is a slug) or name and id (`to` is a name), rewriting links to it.                                                                          |
| [`resolve`](#acquaint.tools.resolve)(handle, \*[, data_dir])                    | Map a channel handle (`github:octocat`, `email:ada@example.org`) to the entity it belongs to, with the evidence.                                                        |
| [`style_lint`](#acquaint.tools.style_lint)(text, \*[, recipient, tolerance, ...])  | The deterministic half of deslop: machine-writing tells in a draft, at the recipient's tolerance and against their blocklist.                                           |
| [`sync_init`](#acquaint.tools.sync_init)(\*, repo[, remote_url, ...])             | Make the data root a checkout of a PRIVATE GitHub repository (created private through `gh` unless `existing_only`), with a pre-push guard.                              |
| [`sync_pull`](#acquaint.tools.sync_pull)(\*[, dry_run, data_dir])                 | Pull the store from its private remote, rebasing local work on top.                                                                                                     |
| [`sync_push`](#acquaint.tools.sync_push)(\*[, message, dry_run, data_dir])        | Commit, rebase onto the remote and push the store, after re-checking the remote, the guard and the visibility.                                                          |
| [`sync_status`](#acquaint.tools.sync_status)(\*[, check_visibility, data_dir])      | Whether the store is synced, to which repository, uncommitted changes, ahead/behind, the guard, and live visibility.                                                    |
| [`who`](#acquaint.tools.who)(name, \*[, field, brief, data_dir])            | Look up one person, project, org or group by exact id, name, alias, handle or email.                                                                                    |

### Exceptions

| [`AcquaintError`](#acquaint.tools.AcquaintError)   | An expected failure with a message meant for the person or agent that asked.   |
|------------------------------------------------------------------|--------------------------------------------------------------------------------|

### *exception* acquaint.tools.AcquaintError

Bases: [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)

An expected failure with a message meant for the person or agent that asked.

### acquaint.tools.SIDE_EFFECTS *= {'brief': 'read', 'check': 'read', 'forget': 'destructive', 'lint': 'read', 'new': 'create', 'reach': 'read', 'remember': 'append', 'rename': 'rewrite', 'resolve': 'read', 'style_lint': 'read', 'sync_init': 'external', 'sync_pull': 'rewrite', 'sync_push': 'external', 'sync_status': 'external-read', 'who': 'read'}*

What each tool changes, for surfaces that must decide what to expose or confirm.
`read` changes nothing and stays local; `append` adds to a log; `create` adds a
record; `rewrite` changes existing records; `destructive` removes data;
`external-read` queries a remote service; `external` acts on one.

### acquaint.tools.TOOLS *= [<function who>, <function resolve>, <function check>, <function reach>, <function brief>, <function remember>, <function lint>, <function new>, <function rename>, <function forget>, <function sync_init>, <function sync_push>, <function sync_pull>, <function sync_status>, <function style_lint>]*

Every tool, in the order surfaces list them.

### acquaint.tools.brief(person, , purpose=None, project=None, data_dir=None)

Everything to know before writing to someone: card, writing style, reach, project norms, recent observations, gaps.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.check(text, , data_dir=None)

Scan prose that names people before publishing it: conflations (one person written as two), ambiguous names, unknown names.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.forget(entity, , confirm=False, data_dir=None)

Remove an entity’s folder and leave a salted tombstone. Needs the exact id; without `confirm`, only reports what would be removed.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.lint(entity=None, , data_dir=None)

Check records: every preference, view and rule sourced; tiers, labels and seals set by the operator; nothing POLICY.md forbids; files parse; entry files within budget.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.new(kind, name, , qualifier=None, description=None, force=False, data_dir=None)

Create a person, project, org or group from its template (a readable slug id; `qualifier` separates two of the same name).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.reach(person, , purpose=None, urgency=None, project=None, message_type=None, topic=None, data_dir=None)

Ordered channels for reaching someone in a context. Only active addresses; returns them, sends nothing. `outcome` is `reachable`, `no_address` (a rule matched, but no usable address is recorded for its channels) or `no_channel`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.remember(entity, text, , source=None, kind='observation', reactivate=False, data_dir=None)

Append a dated observation (`observation`, `interaction`, `identity`, `preference`, `view`, `rule`) to an entity’s log, with its source. An identity equal to an inactive one (`stale`, `retracted`, …) is refused, naming that entry and the command with which the operator can make it active again.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.rename(entity, to, , data_dir=None)

Change an entity’s id (`to` is a slug) or name and id (`to` is a name), rewriting links to it. Needs the exact id.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.resolve(handle, , data_dir=None)

Map a channel handle (`github:octocat`, `email:ada@example.org`) to the entity it belongs to, with the evidence.

`ok` is true only when an active identity on the named platform belongs to exactly
one entity. A handle without a platform (`@octocat`), a match by name only, an
inactive identity, or several owners all return `ok: false` with what was found.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.style_lint(text, , recipient=None, tolerance=None, data_dir=None)

The deterministic half of deslop: machine-writing tells in a draft, at the recipient’s tolerance and against their blocklist.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.sync_init(, repo, remote_url=None, existing_only=False, dry_run=False, data_dir=None)

Make the data root a checkout of a PRIVATE GitHub repository (created private through `gh` unless `existing_only`), with a pre-push guard.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.sync_pull(, dry_run=False, data_dir=None)

Pull the store from its private remote, rebasing local work on top.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.sync_push(, message=None, dry_run=False, data_dir=None)

Commit, rebase onto the remote and push the store, after re-checking the remote, the guard and the visibility.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.sync_status(, check_visibility=True, data_dir=None)

Whether the store is synced, to which repository, uncommitted changes, ahead/behind, the guard, and live visibility.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.tools.who(name, , field=None, brief=False, data_dir=None)

Look up one person, project, org or group by exact id, name, alias, handle or email.

Costs scale with what you ask: `field` returns one value (`aka`, `email`,
`github`, `label`, `tier`, any frontmatter key), `brief` the identity block, and the default the
whole entry file. It never guesses: no exact match, or several, returns the
candidates and `ok: false`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
