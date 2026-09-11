"""Where records live and how code reaches them: the data root, :class:`Store` and :class:`Entity`.

Layout under the data root (one folder per entity, one entry file each)::

    POLICY.md                    what may be recorded
    _tombstones.yaml             salted hashes of forgotten entities' identifiers
    people/<slug>/PROFILE.md     the entry file (required)
    people/<slug>/identities.yaml, rules.yaml, links.yaml, style.md, views.md,
                  sources.md, log/YYYY-MM.md, research/…   (each optional)
    projects/<slug>/PROFILE.md   (and orgs/, groups/, or any other kind)

:class:`Store` is a ``MutableMapping[str, Entity]`` keyed ``"<kind dir>/<slug>"``, where
both parts are lowercase letters, digits and hyphens; nothing else is a key, so no
reference can reach outside the data root. Underneath it is any
``MutableMapping[str, str]`` of relative paths to text: a ``dol`` files store by
default, a ``dict`` in tests. That mapping is the storage seam.

When the store is on disk, listing, moving and removing work on the directories
themselves (so hidden files move and go with their entity), and a file that is not
valid UTF-8 reads with replacement characters and is reported, instead of failing
every lookup.

>>> store = Store(files={})
>>> store["people/ada-lovelace"] = {"PROFILE.md": "---\\nname: Ada Lovelace\\n---\\n"}
>>> list(store), store["people/ada-lovelace"].name
(['people/ada-lovelace'], 'Ada Lovelace')
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections.abc import Iterator, Mapping, MutableMapping
from pathlib import Path
from typing import Any

from acquaint.records import load_yaml, normalize_newlines, sections, split_frontmatter

__all__ = [
    "DATA_DIR_ENVVAR",
    "ENTRY_FILE",
    "KIND_DIRS",
    "UNREADABLE",
    "AcquaintError",
    "Entity",
    "Store",
    "config_path",
    "data_dir",
    "kind_dir",
    "text_files",
    "validate_key",
]

APP_NAME = "acquaint"
DATA_DIR_ENVVAR = "ACQUAINT_DATA_DIR"
ENTRY_FILE = "PROFILE.md"
#: The kinds that ship, singular -> folder. The vocabulary is open: see :func:`kind_dir`.
KIND_DIRS = {"person": "people", "project": "projects", "org": "orgs", "group": "groups"}
_KIND_OF_DIR = {folder: kind for kind, folder in KIND_DIRS.items()}
_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
#: What undecodable bytes read as. A file containing it is reported as not valid UTF-8.
UNREADABLE = "�"
_YAML_LISTS = (("identities.yaml", "identities"), ("rules.yaml", "rules"), ("links.yaml", "links"))


class AcquaintError(Exception):
    """An expected failure with a message meant for the person or agent that asked."""


# ------------------------------------------------------------------------- paths


def _xdg_dir(envvar: str, posix_default: str, windows_envvar: str) -> Path:
    if sys.platform == "win32" and os.environ.get(windows_envvar):
        return Path(os.environ[windows_envvar])
    return Path(os.environ.get(envvar) or Path.home() / posix_default)


def config_path() -> Path:
    """``~/.config/acquaint/config.toml`` (honouring ``XDG_CONFIG_HOME``; ``%APPDATA%`` on Windows)."""
    return _xdg_dir("XDG_CONFIG_HOME", ".config", "APPDATA") / APP_NAME / "config.toml"


def data_dir(data_dir: str | os.PathLike | None = None) -> Path:
    """The data root: the argument, else ``$ACQUAINT_DATA_DIR``, else ``data_dir`` in config.toml, else ``~/.local/share/acquaint``.

    An explicit argument may be relative (it is resolved now). The environment variable
    and the config file must hold absolute paths: a relative one would put profiles
    wherever the current directory happens to be.

    >>> data_dir("profiles").is_absolute()
    True
    """
    if data_dir:
        return Path(os.path.abspath(os.path.expanduser(str(data_dir))))
    configured, origin = os.environ.get(DATA_DIR_ENVVAR), f"${DATA_DIR_ENVVAR}"
    if not configured:
        configured, origin = _configured_data_dir(), f"data_dir in {config_path()}"
    if configured:
        path = Path(os.path.expanduser(configured))
        if not path.is_absolute():
            raise AcquaintError(f"{origin} must be an absolute path, got {configured!r}")
        return path
    return _xdg_dir("XDG_DATA_HOME", ".local/share", "LOCALAPPDATA") / APP_NAME


def _configured_data_dir() -> str | None:
    path = config_path()
    if not path.is_file():
        return None
    import tomllib

    try:
        value = tomllib.loads(path.read_text(encoding="utf-8")).get("data_dir")
    except tomllib.TOMLDecodeError as error:
        raise AcquaintError(f"{path} is not valid TOML: {error}") from error
    return str(value) if value else None


_resolve_data_dir = data_dir


def kind_dir(kind: str) -> str:
    """The folder for a kind: ``person``/``people`` -> ``people``; an unknown kind is used as given, pluralised.

    >>> [kind_dir(k) for k in ("person", "people", "org", "community", "teams")]
    ['people', 'people', 'orgs', 'communities', 'teams']
    """
    kind = kind.strip().lower()
    if kind in KIND_DIRS:
        return KIND_DIRS[kind]
    if kind in _KIND_OF_DIR:
        return kind
    if not _SEGMENT_RE.match(kind):
        raise AcquaintError(f"a kind is a plain lowercase word, got {kind!r}")
    if kind.endswith("s"):
        return kind
    if kind.endswith("y") and kind[-2:-1] not in set("aeiou"):
        return f"{kind[:-1]}ies"
    return f"{kind}s"


def _is_key(key: str) -> bool:
    parts = key.split("/")
    return len(parts) == 2 and all(_SEGMENT_RE.match(part) for part in parts)


def validate_key(key: str) -> str:
    """Return ``key`` if it is ``<kind dir>/<slug>`` of lowercase letters, digits and hyphens; refuse anything else.

    >>> validate_key("people/ada-lovelace")
    'people/ada-lovelace'
    >>> try:
    ...     validate_key("../outside/people/someone")
    ... except AcquaintError as error:
    ...     print(error)
    not a store key: '../outside/people/someone' (expected <kind>/<id>, e.g. people/ada-lovelace)
    """
    if not _is_key(key):
        raise AcquaintError(f"not a store key: {key!r} (expected <kind>/<id>, e.g. people/ada-lovelace)")
    return key


# ------------------------------------------------------------------------- files


def text_files(root: str | os.PathLike) -> MutableMapping[str, str]:
    """A ``dol`` files store under ``root``, for text.

    UTF-8 values (undecodable bytes read as U+FFFD instead of raising), ``\\n`` line
    endings, ``/``-separated keys on every platform, folders made on write and never on
    read, and permanent deletes (never to a trash folder, where "forgotten" data would linger).
    """
    from dol import Files, mk_dirs_if_missing, wrap_kvs

    files = mk_dirs_if_missing(Files(str(root), delete_func=os.remove))
    return wrap_kvs(
        files,
        key_of_id=lambda k: k.replace(os.sep, "/"),
        id_of_key=lambda k: k.replace("/", os.sep),
        obj_of_data=lambda b: normalize_newlines(b.decode("utf-8", errors="replace")),
        data_of_obj=lambda s: s.encode("utf-8"),
    )


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


# ------------------------------------------------------------------------ entity


class Entity(MutableMapping):
    """One person, project, org or group: a mapping of its files (relative names to text), plus parsed views of them.

    Parsed views are recomputed on access (these are small text files), so an edit made
    through the mapping is never hidden behind a stale cache. Parse problems are collected
    in :attr:`errors`; they never raise.
    """

    def __init__(self, store: Store, key: str):
        self.store = store
        self.key = key
        self.kind_dir, _, self.slug = key.partition("/")

    def __repr__(self) -> str:
        return f"Entity({self.key!r})"

    def __iter__(self) -> Iterator[str]:
        return iter(self.store._entity_files(self.key))

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and f"{self.key}/{name}" in self.store.files

    def __getitem__(self, name: str) -> str:
        return self.store.files[f"{self.key}/{name}"]

    def __setitem__(self, name: str, text: str) -> None:
        self.store.files[f"{self.key}/{name}"] = text

    def __delitem__(self, name: str) -> None:
        del self.store.files[f"{self.key}/{name}"]

    @property
    def kind(self) -> str:
        """``person``, ``project``, ``org``, ``group``, or the singular of an open kind's folder."""
        if self.kind_dir in _KIND_OF_DIR:
            return _KIND_OF_DIR[self.kind_dir]
        if self.kind_dir.endswith("ies"):
            return self.kind_dir[:-3] + "y"
        return self.kind_dir.removesuffix("s")

    @property
    def ref(self) -> str:
        """The link form other records use: ``person:ada-lovelace``."""
        return f"{self.kind}:{self.slug}"

    def text(self, name: str, default: str = "") -> str:
        """A file's text, or ``default`` when the file does not exist."""
        return self[name] if name in self else default

    def _profile(self) -> tuple[dict, str, list[str]]:
        return split_frontmatter(self.text(ENTRY_FILE))

    @property
    def meta(self) -> dict:
        """The entry file's frontmatter (empty when it did not parse)."""
        return self._profile()[0]

    @property
    def body(self) -> str:
        """The entry file's Markdown body."""
        return self._profile()[1]

    @property
    def sections(self) -> dict[str, str]:
        """The entry file's ``## Sections``, keyed by normalized title."""
        return sections(self.body)

    @property
    def name(self) -> str:
        """The display name, falling back to the id."""
        name = self.meta.get("name")
        return str(name) if name not in (None, "") else self.slug

    @property
    def aka(self) -> list[str]:
        """Other names this entity goes by, as strings (a scalar ``aka`` is one alias, not its letters)."""
        return [str(a) for a in _as_list(self.meta.get("aka")) if a not in (None, "")]

    def _yaml_list(self, filename: str, key: str) -> tuple[list[dict], list[str]]:
        if filename not in self:
            return [], []
        data, errors = load_yaml(self[filename])
        if errors:
            return [], [f"{filename}: {e}" for e in errors]
        found = (data or {}).get(key, []) if isinstance(data, dict) else data
        if found is None:
            return [], []
        if not isinstance(found, list):
            return [], [f"{filename}: '{key}' should be a list"]
        good = [item for item in found if isinstance(item, dict)]
        bad = len(found) - len(good)
        return good, [f"{filename}: {bad} entry(ies) are not mappings"] if bad else []

    @property
    def identities(self) -> list[dict]:
        """Handles and addresses from ``identities.yaml``: ``{platform, value, source, status, …}``."""
        return self._yaml_list("identities.yaml", "identities")[0]

    @property
    def rules(self) -> list[dict]:
        """Channel and communication rules from ``rules.yaml``: ``{when, do, set_by, source}``."""
        return self._yaml_list("rules.yaml", "rules")[0]

    @property
    def links(self) -> list[dict]:
        """Affiliations from ``links.yaml``: ``{to, relation, role, since, until, source}``."""
        return self._yaml_list("links.yaml", "links")[0]

    @property
    def errors(self) -> list[str]:
        """Everything about the entry file and the YAML files that did not parse."""
        profile = self.text(ENTRY_FILE)
        errors = [f"{ENTRY_FILE}: {e}" for e in self._profile()[2]]
        if UNREADABLE in profile:
            errors.append(f"{ENTRY_FILE}: not valid UTF-8 (undecodable bytes shown as {UNREADABLE})")
        for filename, key in _YAML_LISTS:
            errors += self._yaml_list(filename, key)[1]
        return errors

    @property
    def surface_forms(self) -> list[str]:
        """Every string a document might use for this entity: id, name, aka, name parts, handles."""
        forms = [self.slug, self.name, *self.aka]
        forms += [part for part in self.name.split() if len(part) > 2]
        forms += [str(i.get("value", "")) for i in self.identities if i.get("platform") != "email"]
        return sorted({f.strip() for f in forms if f and f.strip()})

    def summary(self) -> dict[str, Any]:
        """The identity block: frontmatter plus identities, JSON-ready."""
        return {
            "id": self.slug,
            "key": self.key,
            "kind": self.kind,
            **{k: v for k, v in self.meta.items() if k not in {"id", "kind"}},
            "identities": self.identities,
            **({"errors": self.errors} if self.errors else {}),
        }


# ------------------------------------------------------------------------- store


class Store(MutableMapping):
    """``MutableMapping[str, Entity]`` over one folder per entity, keyed ``"<kind dir>/<slug>"``.

    >>> store = Store(files={})
    >>> store["projects/example"] = {"PROFILE.md": "---\\nname: Example\\n---\\n"}
    >>> store.find("project:example"), store.find("example")
    ('projects/example', 'projects/example')
    """

    def __init__(self, data_dir: str | os.PathLike | None = None, *, files: MutableMapping[str, str] | None = None):
        if files is None:
            self.root: Path | None = _resolve_data_dir(data_dir)
            files = text_files(self.root)
        else:
            self.root = None
        self.files = files

    def __repr__(self) -> str:
        return f"Store({str(self.root) if self.root else type(self.files).__name__!r})"

    # -- mapping ---------------------------------------------------------------

    def __iter__(self) -> Iterator[str]:
        if self.root is not None:
            if not self.root.is_dir():
                return iter(())
            keys = (f"{p.parent.parent.name}/{p.parent.name}" for p in self.root.glob(f"*/*/{ENTRY_FILE}"))
        else:
            suffix = "/" + ENTRY_FILE
            keys = (k[: -len(suffix)] for k in list(self.files) if k.endswith(suffix) and k.count("/") == 2)
        return iter(sorted(k for k in keys if _is_key(k)))

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str) or not _is_key(key):
            return False
        if self.root is not None:
            return (self.root / key / ENTRY_FILE).is_file()
        return f"{key}/{ENTRY_FILE}" in self.files

    def __getitem__(self, key: str) -> Entity:
        if key not in self:
            raise KeyError(key)
        return Entity(self, key)

    def __setitem__(self, key: str, files: Mapping[str, str]) -> None:
        validate_key(key)
        for name, text in dict(files).items():
            self.files[f"{key}/{name}"] = text

    def __delitem__(self, key: str) -> None:
        """Remove the entity's whole folder, hidden files included; never to a trash folder."""
        validate_key(key)
        if not self.exists(key):
            raise KeyError(key)
        if self.root is not None:
            shutil.rmtree(self.root / key)
            return
        for name in self._entity_files(key, hidden=True):
            del self.files[f"{key}/{name}"]

    # -- folders ---------------------------------------------------------------

    def exists(self, key: str) -> bool:
        """Whether anything is stored under the entity's folder, with or without an entry file."""
        if not _is_key(key):
            return False
        if self.root is not None:
            return (self.root / key).is_dir()
        return any(k.startswith(key + "/") for k in list(self.files))

    def _entity_files(self, key: str, *, hidden: bool = False) -> list[str]:
        if self.root is not None:
            base = self.root / key
            if not base.is_dir():
                return []
            found = []
            for dirpath, dirnames, filenames in os.walk(base):
                if not hidden:
                    dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                    filenames = [f for f in filenames if not f.startswith(".")]
                rel = Path(dirpath).relative_to(base)
                found += [(rel / f).as_posix() for f in filenames]
            return sorted(found)
        prefix = key + "/"
        names = [k[len(prefix) :] for k in list(self.files) if k.startswith(prefix)]
        if not hidden:
            names = [n for n in names if not any(part.startswith(".") for part in n.split("/"))]
        return sorted(names)

    def all_files(self, key: str) -> list[str]:
        """Every file under the entity's folder, hidden ones included."""
        validate_key(key)
        return self._entity_files(key, hidden=True)

    def move(self, src: str, dst: str) -> None:
        """Move an entity's whole folder to a new key (hidden files included)."""
        validate_key(src)
        validate_key(dst)
        if self.exists(dst):
            raise AcquaintError(f"{dst} already exists")
        if self.root is not None:
            (self.root / dst).parent.mkdir(parents=True, exist_ok=True)
            os.replace(self.root / src, self.root / dst)
            return
        for name in self._entity_files(src, hidden=True):
            self.files[f"{dst}/{name}"] = self.files[f"{src}/{name}"]
            del self.files[f"{src}/{name}"]

    def append_text(self, key: str, name: str, text: str) -> None:
        """Append to one of an entity's files (created if missing); a true append on disk, so concurrent writers do not erase each other."""
        validate_key(key)
        if self.root is not None:
            path = self.root / key / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
            return
        path = f"{key}/{name}"
        self.files[path] = (self.files[path] if path in self.files else "") + text

    def path_of(self, key: str) -> str:
        """Where an entity lives, for a person to open: a real path when on disk, else the key."""
        return str(self.root / key) if self.root else key

    def location_warning(self) -> str | None:
        """A warning when the data root sits inside another git repository: profile data belongs outside code repositories."""
        if self.root is None:
            return None
        root = Path(os.path.abspath(self.root))
        for parent in root.parents:
            if (parent / ".git").exists():
                return f"the data root {root} is inside the git repository at {parent}; keep profile data outside code repositories"
        return None

    def find(self, ref: str) -> str:
        """The store key for ``people/ada-lovelace``, ``person:ada-lovelace`` or a bare ``ada-lovelace``.

        A bare id is looked up among people first, then every other kind; a bare id that
        names entities of two other kinds is an error. Anything that is not a valid key
        raises ``KeyError``, so no reference reaches outside the data root.
        """
        ref = ref.strip()
        if "/" in ref:
            key = ref
        elif ":" in ref:
            kind, _, slug = ref.partition(":")
            try:
                key = f"{kind_dir(kind)}/{slug}"
            except AcquaintError:
                raise KeyError(ref) from None
        else:
            if f"people/{ref}" in self:
                return f"people/{ref}"
            candidates = [key for key in self if key.split("/", 1)[1] == ref]
            if len(candidates) > 1:
                raise AcquaintError(
                    f"{ref!r} names more than one entity: {', '.join(candidates)}; say which, e.g. 'project:{ref}'"
                )
            key = candidates[0] if candidates else ""
        if key in self:
            return key
        raise KeyError(ref)
