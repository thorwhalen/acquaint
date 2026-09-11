"""Where records live and how code reaches them: the data root, :class:`Store` and :class:`Entity`.

Layout under the data root (one folder per entity, one entry file each)::

    POLICY.md                    what may be recorded
    _tombstones.yaml             hashed identifiers of forgotten entities
    people/<slug>/PROFILE.md     the entry file (required)
    people/<slug>/identities.yaml, rules.yaml, links.yaml, style.md, views.md,
                  sources.md, log/YYYY-MM.md, research/…   (each optional)
    projects/<slug>/PROFILE.md   (and orgs/, groups/, or any other kind)

:class:`Store` is a ``MutableMapping[str, Entity]`` keyed ``"<kind dir>/<slug>"``.
Underneath it is any ``MutableMapping[str, str]`` of relative paths to text: a
``dol`` files store by default, a ``dict`` in tests. That mapping is the storage
seam; nothing above it knows where bytes physically live.

>>> store = Store(files={})
>>> store["people/ada-lovelace"] = {"PROFILE.md": "---\\nname: Ada Lovelace\\n---\\n"}
>>> list(store), store["people/ada-lovelace"].name
(['people/ada-lovelace'], 'Ada Lovelace')
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator, Mapping, MutableMapping
from pathlib import Path
from typing import Any

from acquaint.records import load_yaml, sections, split_frontmatter

__all__ = [
    "DATA_DIR_ENVVAR",
    "ENTRY_FILE",
    "KIND_DIRS",
    "AcquaintError",
    "Entity",
    "Store",
    "config_path",
    "data_dir",
    "kind_dir",
    "text_files",
]

APP_NAME = "acquaint"
DATA_DIR_ENVVAR = "ACQUAINT_DATA_DIR"
ENTRY_FILE = "PROFILE.md"
#: The kinds that ship, singular -> folder. The vocabulary is open: see :func:`kind_dir`.
KIND_DIRS = {"person": "people", "project": "projects", "org": "orgs", "group": "groups"}
_KIND_OF_DIR = {folder: kind for kind, folder in KIND_DIRS.items()}


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

    >>> data_dir("/tmp/profiles").as_posix()
    '/tmp/profiles'
    """
    chosen = data_dir or os.environ.get(DATA_DIR_ENVVAR) or _configured_data_dir()
    if chosen:
        return Path(chosen).expanduser()
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
    if not kind.replace("-", "").isalnum():
        raise AcquaintError(f"a kind is a plain word, got {kind!r}")
    if kind.endswith("s"):
        return kind
    if kind.endswith("y") and kind[-2:-1] not in set("aeiou"):
        return f"{kind[:-1]}ies"
    return f"{kind}s"


_resolve_data_dir = data_dir


# ------------------------------------------------------------------------- files


def text_files(root: str | os.PathLike) -> MutableMapping[str, str]:
    """A ``dol`` files store under ``root``: UTF-8 text values, ``/``-separated keys, folders made on write.

    Bytes underneath, decoded here, so Windows neither re-encodes ``·`` nor rewrites newlines.
    """
    from dol import Files, mk_dirs_if_missing, wrap_kvs

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    files = mk_dirs_if_missing(Files(str(root)))
    return wrap_kvs(
        files,
        key_of_id=lambda k: k.replace(os.sep, "/"),
        id_of_key=lambda k: k.replace("/", os.sep),
        obj_of_data=lambda b: b.decode("utf-8"),
        data_of_obj=lambda s: s.encode("utf-8"),
    )


class _Prefixed(MutableMapping):
    """The files under one folder of a larger mapping, with keys relative to that folder."""

    def __init__(self, files: MutableMapping[str, str], prefix: str):
        self._files = files
        self._prefix = prefix.rstrip("/") + "/"

    def __iter__(self) -> Iterator[str]:
        n = len(self._prefix)
        return iter(sorted(k[n:] for k in list(self._files) if k.startswith(self._prefix)))

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and (self._prefix + key) in self._files

    def __getitem__(self, key: str) -> str:
        return self._files[self._prefix + key]

    def __setitem__(self, key: str, value: str) -> None:
        self._files[self._prefix + key] = value

    def __delitem__(self, key: str) -> None:
        del self._files[self._prefix + key]


# ------------------------------------------------------------------------ entity


class Entity(_Prefixed):
    """One person, project, org or group: a mapping of its files, plus parsed views of them.

    Every parsed view is recomputed on access (these are small text files) so an
    edit made through the mapping is never hidden behind a stale cache. Parse
    problems are collected in :attr:`errors`; they never raise.
    """

    def __init__(self, files: MutableMapping[str, str], key: str):
        super().__init__(files, key)
        self.key = key
        self.kind_dir, _, self.slug = key.partition("/")

    def __repr__(self) -> str:
        return f"Entity({self.key!r})"

    @property
    def kind(self) -> str:
        """``person``, ``project``, ``org``, ``group``, or the folder name for an open kind."""
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
        """The entry file's ``## Sections``."""
        return sections(self.body)

    @property
    def name(self) -> str:
        """The display name, falling back to the id."""
        return str(self.meta.get("name") or self.slug)

    @property
    def aka(self) -> list[str]:
        """Other names this entity goes by (always a list)."""
        return _as_list(self.meta.get("aka"))

    def _yaml_list(self, filename: str, key: str) -> tuple[list[dict], list[str]]:
        if filename not in self:
            return [], []
        data, errors = load_yaml(self[filename])
        if errors:
            return [], [f"{filename}: {e}" for e in errors]
        items = (data or {}).get(key, []) if isinstance(data, dict) else data
        if not isinstance(items, list):
            return [], [f"{filename}: '{key}' should be a list"]
        good = [item for item in items if isinstance(item, dict)]
        bad = len(items) - len(good)
        return good, [f"{filename}: {bad} entry(ies) are not mappings"] if bad else []

    @property
    def identities(self) -> list[dict]:
        """Handles and addresses from ``identities.yaml``: ``{platform, value, source, …}``."""
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
        """Everything about this entity's files that did not parse."""
        errors = [f"{ENTRY_FILE}: {e}" for e in self._profile()[2]]
        for filename, key in (
            ("identities.yaml", "identities"),
            ("rules.yaml", "rules"),
            ("links.yaml", "links"),
        ):
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


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


# ------------------------------------------------------------------------- store


class Store(MutableMapping):
    """``MutableMapping[str, Entity]`` over one folder per entity, keyed ``"<kind dir>/<slug>"``.

    >>> store = Store(files={})
    >>> store["projects/example"] = {"PROFILE.md": "---\\nname: Example\\n---\\n"}
    >>> store.find("project:example"), store.find("example")
    ('projects/example', 'projects/example')
    """

    def __init__(
        self,
        data_dir: str | os.PathLike | None = None,
        *,
        files: MutableMapping[str, str] | None = None,
    ):
        if files is None:
            self.root: Path | None = _resolve_data_dir(data_dir)
            files = text_files(self.root)
        else:
            self.root = Path(data_dir) if data_dir else None
        self.files = files

    def __repr__(self) -> str:
        return f"Store({str(self.root) if self.root else type(self.files).__name__!r})"

    def __iter__(self) -> Iterator[str]:
        suffix = "/" + ENTRY_FILE
        keys = (
            k[: -len(suffix)]
            for k in list(self.files)
            if k.endswith(suffix) and k.count("/") == 2 and not k.startswith("_")
        )
        return iter(sorted(keys))

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and f"{key}/{ENTRY_FILE}" in self.files

    def __getitem__(self, key: str) -> Entity:
        if key not in self:
            raise KeyError(key)
        return Entity(self.files, key)

    def __setitem__(self, key: str, files: Mapping[str, str]) -> None:
        if key.count("/") != 1:
            raise KeyError(f"store keys look like 'people/ada-lovelace', got {key!r}")
        for name, text in dict(files).items():
            self.files[f"{key}/{name}"] = text

    def __delitem__(self, key: str) -> None:
        entity = self[key]
        for name in list(entity):
            del entity[name]

    def path_of(self, key: str) -> str:
        """Where an entity lives, for a person to open: a real path when on disk, else the key."""
        return str(self.root / key) if self.root else key

    def find(self, ref: str) -> str:
        """The store key for ``people/ada-lovelace``, ``person:ada-lovelace`` or a bare ``ada-lovelace``.

        A bare slug is looked up among people first, then every other kind; a
        bare slug that names entities of two other kinds is an error.
        """
        ref = ref.strip()
        if "/" in ref:
            candidates = [ref]
        elif ":" in ref:
            kind, _, slug = ref.partition(":")
            candidates = [f"{kind_dir(kind)}/{slug}"]
        else:
            people = f"people/{ref}"
            if people in self:
                return people
            candidates = [key for key in self if key.split("/", 1)[1] == ref]
            if len(candidates) > 1:
                raise AcquaintError(
                    f"{ref!r} names more than one entity: {', '.join(candidates)}; "
                    "say which, e.g. 'project:" + ref + "'"
                )
        if candidates and candidates[0] in self:
            return candidates[0]
        raise KeyError(ref)
