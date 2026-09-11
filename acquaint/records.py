"""The text formats acquaint stores, as pure functions: frontmatter, sections, source tags, slugs, log entries.

Nothing here touches a filesystem. A record is text in and data out, so the same
rules hold whether the text came from disk, a ``dict`` or a remote store.

The formats are deliberately hand-editable Markdown: YAML frontmatter for what a
machine looks up, ``## Sections`` of bullets for what a person writes, and an
inline ``[source: …]`` tag on every bullet that states a preference, a view or a
rule.

>>> slugify("Ada Lovelace")
'ada-lovelace'
>>> meta, body, errors = split_frontmatter("---\\nname: Ada\\n---\\n## Who\\n- a mathematician\\n")
>>> meta, list(sections(body)), errors
({'name': 'Ada'}, ['Who'], [])
>>> source_problem("- Prefers email. [source: https://example.org/thread/1]") is None
True
>>> source_problem("- Prefers email. [source: 2026-09-11]")
'a date alone is not a source'
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import yaml

__all__ = [
    "slugify",
    "split_frontmatter",
    "join_frontmatter",
    "load_yaml",
    "dump_yaml",
    "sections",
    "bullets",
    "source_refs",
    "source_kind",
    "source_problem",
    "parse_log",
    "format_log_entry",
]

_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(?P<yaml>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)(?P<body>.*)\Z", re.S
)
_SECTION_RE = re.compile(r"^##[ \t]+(?P<title>[^\n]+?)[ \t]*$", re.M)
_BULLET_RE = re.compile(r"^[ \t]*[-*][ \t]+(?P<text>\S.*)$")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_SOURCE_TAG_RE = re.compile(r"\[source:\s*(?P<ref>[^\]]*)\]", re.I)
_DATE_ONLY_RE = re.compile(
    r"^(?:(?:observed|seen|noted|on)\s+)?\d{4}(?:-\d{2}(?:-\d{2})?)?$", re.I
)
_QUOTE_RE = re.compile(r"[\"“”'‘’].+[\"“”'‘’]")
_LOG_HEADING_RE = re.compile(
    r"^##[ \t]+(?P<id>e\d+)[ \t]+·[ \t]+(?P<date>\S+)[ \t]+·[ \t]+(?P<kind>\S+)[ \t]*$",
    re.M,
)
_LOG_FIELD_RE = re.compile(r"^-[ \t]+(?P<key>[a-z_]+):[ \t]*(?P<value>.*)$")

#: The words that name "no primary source was found", said out loud.
NONE_LOCATED = ("none located", "no primary source located")


# --------------------------------------------------------------------------- slugs


def slugify(name: str, *, qualifier: str | None = None) -> str:
    """A readable, ASCII-folded, lowercase id: ``given-family``, plus ``--qualifier`` on a collision.

    >>> slugify("Zoë Ångström")
    'zoe-angstrom'
    >>> slugify("John Smith", qualifier="Example Org")
    'john-smith--example-org'
    """

    def fold(text: str) -> str:
        ascii_text = (
            unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        )
        return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")

    slug = fold(name)
    if not slug:
        raise ValueError(f"cannot make an id from {name!r}: no letters or digits")
    if qualifier:
        slug = f"{slug}--{fold(qualifier)}"
    return slug


# --------------------------------------------------------------------- frontmatter


class _Loader(yaml.SafeLoader):
    """A safe loader that keeps dates as the strings a person typed (so results stay JSON-ready)."""


_Loader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if not tag.endswith(":timestamp")]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml(text: str) -> tuple[Any, list[str]]:
    """Parse YAML, returning ``(data, errors)`` instead of raising: these files are hand-edited.

    >>> load_yaml("a: [1, 2]")
    ({'a': [1, 2]}, [])
    >>> data, errors = load_yaml("a: [1, 2")
    >>> data, bool(errors)
    (None, True)
    """
    try:
        return yaml.load(text, Loader=_Loader), []
    except yaml.YAMLError as error:
        return None, [f"YAML did not parse: {' '.join(str(error).split())}"]


class _Dumper(yaml.SafeDumper):
    """Block style for mappings; lists of plain scalars inline, as a person would type them."""


def _represent_list(dumper: yaml.SafeDumper, data: list) -> yaml.Node:
    scalars = all(isinstance(item, (str, int, float, bool)) or item is None for item in data)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=scalars)


_Dumper.add_representer(list, _represent_list)


def dump_yaml(data: Any) -> str:
    """Write YAML the way a person would: keys in order, short lists inline, unicode kept.

    >>> print(dump_yaml({"name": "Ada", "aka": ["Ada", "Lovelace"], "links": [{"to": "org:x"}]}), end="")
    name: Ada
    aka: [Ada, Lovelace]
    links:
    - to: org:x
    """
    return yaml.dump(
        data,
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    )


def split_frontmatter(text: str) -> tuple[dict, str, list[str]]:
    """Split ``---`` YAML frontmatter from a Markdown body: ``(meta, body, errors)``.

    A malformed header degrades to empty metadata plus an error, never an exception,
    so one bad hand edit cannot take down lookups of every other record.

    >>> split_frontmatter("no frontmatter here")
    ({}, 'no frontmatter here', ['no --- frontmatter block at the top of the file'])
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text, ["no --- frontmatter block at the top of the file"]
    meta, errors = load_yaml(match.group("yaml"))
    if errors:
        return {}, match.group("body"), errors
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        return {}, match.group("body"), ["frontmatter is not a mapping of keys to values"]
    return meta, match.group("body"), []


def join_frontmatter(meta: dict, body: str) -> str:
    """The inverse of :func:`split_frontmatter`.

    >>> join_frontmatter({"name": "Ada"}, "## Who\\n")
    '---\\nname: Ada\\n---\\n\\n## Who\\n'
    """
    return f"---\n{dump_yaml(meta)}---\n\n{body.lstrip()}"


# ------------------------------------------------------------------------ sections


def sections(body: str) -> dict[str, str]:
    """``## Title`` blocks of a Markdown body, in order, as ``{title: text}``.

    >>> sections("intro\\n## Who\\nAda\\n## Now\\n- busy\\n")
    {'Who': 'Ada\\n', 'Now': '- busy\\n'}
    """
    found = list(_SECTION_RE.finditer(body))
    result = {}
    for match, following in zip(found, found[1:] + [None]):
        end = following.start() if following else len(body)
        result[match.group("title")] = body[match.end() : end].lstrip("\r\n")
    return result


def bullets(text: str) -> list[tuple[int, str]]:
    """``(line_number, text)`` for each top-level bullet, with HTML comments removed first.

    Line numbers are 1-based and count from the start of ``text``.

    >>> bullets("- one\\n<!-- - hidden -->\\nnot a bullet\\n* two\\n")
    [(1, 'one'), (4, 'two')]
    """
    visible = _COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return [
        (number, match.group("text").rstrip())
        for number, line in enumerate(visible.splitlines(), start=1)
        if (match := _BULLET_RE.match(line))
    ]


# --------------------------------------------------------------------- source tags


def source_refs(line: str) -> list[str]:
    """Every ``[source: …]`` reference on a line, stripped.

    >>> source_refs("- Short replies. [source: log/2026-09.md#e03] [source: operator]")
    ['log/2026-09.md#e03', 'operator']
    """
    return [match.group("ref").strip() for match in _SOURCE_TAG_RE.finditer(line)]


def source_kind(ref: str) -> str:
    """Classify one source reference.

    One of ``url``, ``file``, ``self``, ``self-unquoted``, ``operator``,
    ``none-located``, ``date-only``, ``empty`` or ``other`` (free text, accepted
    but not checkable).

    >>> [source_kind(r) for r in ["https://example.org/x", "log/2026-09.md#e01",
    ...     'self: "email me the files"', "self, 2026-09", "operator", "none located",
    ...     "2026-09", "", "call with the team"]]
    ['url', 'file', 'self', 'self-unquoted', 'operator', 'none-located', 'date-only', 'empty', 'other']
    """
    ref = ref.strip()
    lowered = ref.lower()
    if not ref:
        return "empty"
    if _DATE_ONLY_RE.match(ref):
        return "date-only"
    if re.match(r"https?://\S+", ref):
        return "url"
    if lowered.startswith(NONE_LOCATED):
        return "none-located"
    if re.match(r"self\b", lowered):
        return "self" if _QUOTE_RE.search(ref) else "self-unquoted"
    if lowered.startswith("operator"):
        return "operator"
    if re.match(r"[\w./-]+\.(md|yaml|yml|txt)(#\S+)?$", ref):
        return "file"
    return "other"


def source_problem(line: str) -> str | None:
    """Why a preference-bearing line is not sourced, or ``None`` when it is.

    A source is a permalink, a file anchor (``log/2026-09.md#e03``), the person's own
    words (``self: "…"``), the operator's statement (``operator``), or an explicit
    ``none located``. A date alone is not a source.

    >>> source_problem("- Prefers calls.")
    'no [source: …] tag'
    >>> source_problem('- Prefers calls. [source: self: "call me, never email"]') is None
    True
    >>> source_problem("- Prefers calls. [source: self, 2026-09-01]")
    'self-stated sources need the quoted words: [source: self: "…"]'
    """
    refs = source_refs(line)
    if not refs:
        return "no [source: …] tag"
    kinds = [source_kind(ref) for ref in refs]
    if any(kind in {"url", "file", "self", "operator", "none-located", "other"} for kind in kinds):
        return None
    if "self-unquoted" in kinds:
        return 'self-stated sources need the quoted words: [source: self: "…"]'
    if "date-only" in kinds:
        return "a date alone is not a source"
    return "empty [source: ] tag"


# ------------------------------------------------------------------------------ log


def parse_log(text: str) -> list[dict]:
    """Entries of an append-only ``log/YYYY-MM.md`` file, oldest first.

    >>> entry = format_log_entry("e01", "2026-09-11", "observation", "short replies",
    ...                          source="https://example.org/thread/1")
    >>> parse_log(entry)
    [{'id': 'e01', 'date': '2026-09-11', 'kind': 'observation', 'text': 'short replies', 'source': 'https://example.org/thread/1'}]
    """
    found = list(_LOG_HEADING_RE.finditer(text))
    entries = []
    for match, following in zip(found, found[1:] + [None]):
        end = following.start() if following else len(text)
        entry = {key: match.group(key) for key in ("id", "date", "kind")}
        prose, fields = [], {}
        for line in text[match.end() : end].strip("\r\n").splitlines():
            field = _LOG_FIELD_RE.match(line)
            if field:
                fields[field.group("key")] = field.group("value").strip()
            elif line.strip():
                prose.append(line.rstrip())
        entries.append({**entry, "text": "\n".join(prose), **fields})
    return entries


def format_log_entry(
    entry_id: str, date: str, kind: str, text: str, *, source: str | None = None, **fields: str
) -> str:
    """One log entry: a ``## id · date · kind`` heading, the observation, then ``- key: value`` fields."""
    lines = [f"## {entry_id} · {date} · {kind}", " ".join(text.split())]
    if source is not None:
        lines.append(f"- source: {source}")
    lines += [f"- {key}: {value}" for key, value in fields.items() if value]
    return "\n".join(lines) + "\n"
