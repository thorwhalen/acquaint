# acquaint.store

Where records live and how code reaches them: the data root, [`Store`](#acquaint.store.Store) and [`Entity`](#acquaint.store.Entity).

Layout under the data root (one folder per entity, one entry file each):

```default
POLICY.md                    what may be recorded
_tombstones.yaml             salted hashes of forgotten entities' identifiers
people/<slug>/PROFILE.md     the entry file (required)
people/<slug>/identities.yaml, rules.yaml, links.yaml, trust.yaml, style.md, views.md,
              sources.md, log/YYYY-MM.md, research/…   (each optional)
projects/<slug>/PROFILE.md   (and orgs/, groups/, or any other kind)
```

[`Store`](#acquaint.store.Store) is a `MutableMapping[str, Entity]` keyed `"<kind dir>/<slug>"`, where
both parts are lowercase letters, digits and hyphens; nothing else is a key, so no
reference can reach outside the data root. Underneath it is any
`MutableMapping[str, str]` of relative paths to text: a `dol` files store by
default, a `dict` in tests. That mapping is the storage seam.

When the store is on disk, an entity is a real directory whose name matches its key
exactly (case included, even on case-insensitive filesystems) and is not a link.
Listing, moving and removing work on those directories, so hidden files move and go
with their entity. A file that is not valid UTF-8 reads with replacement characters and
is reported, instead of failing every lookup. Entry files the store cannot address (a
capitalised folder, a linked folder, `profile.md`) are listed by [`Store.misnamed()`](#acquaint.store.Store.misnamed).

```pycon
>>> store = Store(files={})
>>> store["people/ada-lovelace"] = {"PROFILE.md": "---\nname: Ada Lovelace\n---\n"}
>>> list(store), store["people/ada-lovelace"].name
(['people/ada-lovelace'], 'Ada Lovelace')
```

### Module Attributes

| [`KIND_DIRS`](#acquaint.store.KIND_DIRS)   | see [`kind_dir()`](#acquaint.store.kind_dir).   |
|--------------------------------------------------------------|--------------------------------------------------------------------|
| [`UNREADABLE`](#acquaint.store.UNREADABLE)  | What undecodable bytes read as.                                    |

### Functions

| [`config_path`](#acquaint.store.config_path)()        | `~/.config/acquaint/config.toml` (honouring `XDG_CONFIG_HOME`; `%APPDATA%` on Windows).                                 |
|-----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| [`data_dir`](#acquaint.store.data_dir)([data_dir]) | The data root: the argument, else `$ACQUAINT_DATA_DIR`, else `data_dir` in config.toml, else `~/.local/share/acquaint`. |
| [`kind_dir`](#acquaint.store.kind_dir)(kind)       | The folder for a kind: `person`/`people` -> `people`; an unknown kind is used as given, pluralised.                     |
| [`text_files`](#acquaint.store.text_files)(root)     | A `dol` files store under `root`, for text.                                                                             |
| [`validate_key`](#acquaint.store.validate_key)(key)    | Return `key` if it is `<kind dir>/<slug>` of lowercase letters, digits and hyphens; refuse anything else.               |

### Classes

| [`Entity`](#acquaint.store.Entity)(store, key)       | One person, project, org or group: a mapping of its files (relative names to text), plus parsed views of them.   |
|---------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| [`Store`](#acquaint.store.Store)([data_dir, files]) | `MutableMapping[str, Entity]` over one folder per entity, keyed `"<kind dir>/<slug>"`.                           |

### Exceptions

| [`AcquaintError`](#acquaint.store.AcquaintError)   | An expected failure with a message meant for the person or agent that asked.   |
|------------------------------------------------------------------|--------------------------------------------------------------------------------|

### *exception* acquaint.store.AcquaintError

Bases: [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)

An expected failure with a message meant for the person or agent that asked.

### *class* acquaint.store.Entity(store, key)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

One person, project, org or group: a mapping of its files (relative names to text), plus parsed views of them.

Parsed views are recomputed on access (these are small text files), so an edit made
through the mapping is never hidden behind a stale cache. Parse problems are collected
in [`errors`](#acquaint.store.Entity.errors); they never raise.

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

`{tier, valid_from, valid_to, review_by, recorded, source, note}` (see [`acquaint.trust`](acquaint.trust.md#module-acquaint.trust)).

* **Type:**
  Disclosure tiers from `trust.yaml`

### acquaint.store.KIND_DIRS *= {'group': 'groups', 'org': 'orgs', 'person': 'people', 'project': 'projects'}*

see [`kind_dir()`](#acquaint.store.kind_dir).

* **Type:**
  The kinds that ship, singular -> folder. The vocabulary is open

### *class* acquaint.store.Store(data_dir=None, , files=None)

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

### acquaint.store.UNREADABLE *= '�'*

What undecodable bytes read as. A file containing it is reported as not valid UTF-8.

### acquaint.store.config_path()

`~/.config/acquaint/config.toml` (honouring `XDG_CONFIG_HOME`; `%APPDATA%` on Windows).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### acquaint.store.data_dir(data_dir=None)

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

### acquaint.store.kind_dir(kind)

The folder for a kind: `person`/`people` -> `people`; an unknown kind is used as given, pluralised.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> [kind_dir(k) for k in ("person", "people", "org", "community", "teams")]
['people', 'people', 'orgs', 'communities', 'teams']
```

### acquaint.store.text_files(root)

A `dol` files store under `root`, for text.

UTF-8 values (undecodable bytes read as U+FFFD instead of raising; a byte-order mark
dropped), `\n` line endings, `/`-separated keys on every platform, folders made on
write and never on read, and permanent deletes (never to a trash folder, where
“forgotten” data would linger).

* **Return type:**
  [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### acquaint.store.validate_key(key)

Return `key` if it is `<kind dir>/<slug>` of lowercase letters, digits and hyphens; refuse anything else.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> validate_key("people/ada-lovelace")
'people/ada-lovelace'
>>> try:
...     validate_key("../outside/people/someone")
... except AcquaintError as error:
...     print(error)
not a store key: '../outside/people/someone' (expected <kind>/<id>, e.g. people/ada-lovelace)
```
