# acquaint.edit

Changing the store: create an entity, append an observation, rename with relinking, forget with a tombstone.

The hot path is append-only. [`append_observation()`](#acquaint.edit.append_observation) never edits an entry file, a
writing card or a rule: it appends a dated, sourced entry to `log/YYYY-MM.md` (or a
handle to `identities.yaml`). The one change it makes to an existing entry is making an
inactive handle active again, and only when asked (`reactivate`). `identities.yaml` is
rewritten whenever it changes, so comments in it are not kept. Turning observations into
profile lines is a separate, reviewed pass.

These functions take exact references (`ada-lovelace`, `person:ada-lovelace`,
`people/ada-lovelace`); matching names to ids is the caller’s job
([`acquaint.lookup.find_entity()`](acquaint.lookup.html.md#acquaint.lookup.find_entity)), so nothing here acts on a guess.

### Module Attributes

| [`OBSERVATION_KINDS`](#acquaint.edit.OBSERVATION_KINDS)   | What `remember` can record.   |
|----------------------------------------------------------------------|-------------------------------|

### Functions

| [`append_observation`](#acquaint.edit.append_observation)(store, ref, text, \*[, ...])   | Append one dated, sourced entry to the entity's `log/YYYY-MM.md` (and, for `identity`, to `identities.yaml`).   |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| [`forget_entity`](#acquaint.edit.forget_entity)(store, ref, \*[, confirm, today])   | Remove an entity's whole folder, hidden files included, after writing a salted tombstone.                       |
| [`new_entity`](#acquaint.edit.new_entity)(store, kind, name, \*[, ...])          | Scaffold `<kind dir>/<slug>/PROFILE.md` from the template for its kind, and seed `POLICY.md`.                   |
| [`rename_entity`](#acquaint.edit.rename_entity)(store, ref, to, \*[, today])        | Give an entity a new id (`to` is a slug) or a new name and id (`to` is a name); links elsewhere follow.         |
| [`tombstone_problem`](#acquaint.edit.tombstone_problem)(store)                          | Why `_tombstones.yaml` cannot be trusted, or `None`.                                                            |
| [`tombstoned`](#acquaint.edit.tombstoned)(store, \*identifiers)                  | The tombstone matching any of these identifiers, if such an entity was forgotten.                               |

### acquaint.edit.OBSERVATION_KINDS *= ('observation', 'interaction', 'identity', 'preference', 'view', 'rule')*

What `remember` can record. The last three need a source at write time.

### acquaint.edit.append_observation(store, ref, text, , source=None, kind='observation', reactivate=False, disclosed=(), today=None)

Append one dated, sourced entry to the entity’s `log/YYYY-MM.md` (and, for `identity`, to `identities.yaml`).

An identity equal to an inactive one is refused, naming that entry, unless
`reactivate` is set (see `_append_identity()`). `disclosed` (`interaction`
only) lists the records the message identified, by exact id or reference, written as
references (`project:heron`); never the text. A refusal writes nothing.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### acquaint.edit.forget_entity(store, ref, , confirm=False, today=None)

Remove an entity’s whole folder, hidden files included, after writing a salted tombstone.

Without `confirm` it only reports what it would remove, and which other records
still mention the entity (it does not edit them: other people’s logs are append-only).
The tombstone is written first, so a removal that fails half way still stops the
entity being re-created, and running `forget` again finishes the job.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### acquaint.edit.new_entity(store, kind, name, , qualifier=None, description=None, force=False, today=None)

Scaffold `<kind dir>/<slug>/PROFILE.md` from the template for its kind, and seed `POLICY.md`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### acquaint.edit.rename_entity(store, ref, to, , today=None)

Give an entity a new id (`to` is a slug) or a new name and id (`to` is a name); links elsewhere follow.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### acquaint.edit.tombstone_problem(store)

Why `_tombstones.yaml` cannot be trusted, or `None`. A broken file must never read as “nobody was forgotten”.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### acquaint.edit.tombstoned(store, \*identifiers)

The tombstone matching any of these identifiers, if such an entity was forgotten. Raises if the tombstone file is broken.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
