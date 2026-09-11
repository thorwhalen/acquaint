"""The text formats acquaint stores, as pure functions: frontmatter, sections, items, source tags, slugs, log entries.

Nothing here touches a filesystem. A record is text in and data out, so the same
rules hold whether the text came from disk, a ``dict`` or a remote store. Every parser
accepts ``\\r\\n`` line endings, because a store synced through Windows will have them.

The formats are deliberately hand-editable Markdown: YAML frontmatter for what a
machine looks up, ``## Sections`` of items for what a person writes, and an inline
``[source: …]`` tag on every item that states a preference, a view or a rule.

>>> slugify("Ada Lovelace")
'ada-lovelace'
>>> meta, body, errors = split_frontmatter("---\\r\\nname: Ada\\r\\n---\\r\\n## Who\\r\\n- a mathematician\\r\\n")
>>> meta, list(sections(body)), errors
({'name': 'Ada'}, ['Who'], [])
>>> source_problem("- Prefers email. [source: https://example.org/thread/1]") is None
True
>>> source_problem("- Prefers email. [source: September 2026]")
'a date alone is not a source'
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import yaml

__all__ = [
    "NONE_LOCATED",
    "blank_frontmatter",
    "dump_yaml",
    "format_log_entry",
    "items",
    "join_frontmatter",
    "load_yaml",
    "next_log_id",
    "normalize_newlines",
    "normalize_title",
    "parse_log",
    "sectioned_items",
    "sections",
    "slugify",
    "source_kind",
    "source_problem",
    "source_refs",
    "split_frontmatter",
]

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(?P<yaml>.*?)\n---[ \t]*(?:\n|\Z)(?P<body>.*)\Z", re.S)
_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})[ \t]+(?P<title>.*?)[ \t]*$")
_BULLET_RE = re.compile(r"^(?P<indent>[ \t]*)(?:[-*+]|\d{1,3}[.)])[ \t]+(?P<text>\S.*)$")
_THEMATIC_BREAK_RE = re.compile(r"^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_FENCE_RE = re.compile(r"^[ \t]*(?:```|~~~)")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_SOURCE_TAG_RE = re.compile(r"\[source:\s*(?P<ref>[^\]]*)\]", re.I)
#: Quoted words: straight or curly double quotes, curly single quotes, or straight
#: single quotes that are not apostrophes inside words ("it's what they're like").
_QUOTE_RE = re.compile(r"\"[^\"]+\"|“[^”]+”|‘[^’]+’|(?<!\w)'[^']+'(?!\w)")
_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
#: Everything a date, a time or "observed on …" can be made of; a reference made only of these is date-only.
_DATE_NOISE_RE = re.compile(
    rf"\b(?:{_MONTH}|observed|seen|noted|on|around|circa|ca|about|in|at|am|pm|utc|gmt|q[1-4]|t|z)\b|[\d\s\-/.:,+]",
    re.I,
)
#: References that say "I have no source" without saying that you looked.
_PLACEHOLDERS = {
    "unknown", "todo", "tbd", "tbc", "none", "n/a", "na", "?", "-", "inferred", "inference",
    "guess", "guessed", "assumed", "assumption", "various", "misc", "source", "citation needed",
    "xxx", "see above",
}
_LOG_HEADING_RE = re.compile(
    r"^##[ \t]+(?P<id>e\d+)[ \t]*[·|–—-][ \t]*(?P<date>\S+)[ \t]*[·|–—-][ \t]*(?P<kind>\S+)[ \t]*$", re.M
)
_LOG_ID_RE = re.compile(r"^##[ \t]+e(\d+)\b", re.M)
_LOG_FIELD_RE = re.compile(r"^-[ \t]+(?P<key>[a-z_]+):[ \t]*(?P<value>.*)$")
_NEEDS_ESCAPE_RE = re.compile(r"[-*+#>\\]|\d{1,3}[.)]\s")

#: The words that say "no primary source was found", out loud.
NONE_LOCATED = ("none located", "no primary source located")


# --------------------------------------------------------------------------- basics


def normalize_newlines(text: str) -> str:
    """``\\r\\n`` and lone ``\\r`` as ``\\n``.

    >>> normalize_newlines("a\\r\\nb\\rc")
    'a\\nb\\nc'
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_title(title: str) -> str:
    """A heading as written, minus decoration: closing ``#``s, a trailing colon, typographic apostrophes, extra space.

    >>> normalize_title("  Don’t:  ## ")
    "Don't"
    """
    title = title.replace("’", "'").replace("‘", "'")
    title = re.sub(r"[ \t]+#+[ \t]*$|^#+[ \t]*$", "", title)
    return re.sub(r"\s+", " ", title).strip().rstrip(":").strip()


def slugify(name: str, *, qualifier: str | None = None) -> str:
    """A readable, ASCII-folded, lowercase id: ``given-family``, plus ``--qualifier`` on a collision.

    >>> slugify("Zoë Ångström")
    'zoe-angstrom'
    >>> slugify("John Smith", qualifier="Example Org")
    'john-smith--example-org'
    """

    def fold(text: str) -> str:
        ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")

    slug = fold(name)
    if not slug:
        raise ValueError(f"cannot make an id from {name!r}: no letters or digits")
    if qualifier:
        qualified = fold(qualifier)
        if not qualified:
            raise ValueError(f"cannot use {qualifier!r} as a qualifier: no letters or digits")
        slug = f"{slug}--{qualified}"
    return slug


# ---------------------------------------------------------------------------- YAML


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
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000)


# --------------------------------------------------------------------- frontmatter


def split_frontmatter(text: str) -> tuple[dict, str, list[str]]:
    """Split ``---`` YAML frontmatter from a Markdown body: ``(meta, body, errors)``.

    A malformed header degrades to empty metadata plus an error, never an exception,
    so one bad hand edit cannot take down lookups of every other record.

    >>> split_frontmatter("no frontmatter here")
    ({}, 'no frontmatter here', ['no --- frontmatter block at the top of the file'])
    """
    text = normalize_newlines(text)
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


def blank_frontmatter(text: str) -> str:
    """The text with its frontmatter lines emptied, so line numbers still match the file.

    >>> blank_frontmatter("---\\nname: Ada\\n---\\nbody\\n")
    '\\n\\n\\nbody\\n'
    """
    text = normalize_newlines(text)
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return text
    return "\n" * text[: match.start("body")].count("\n") + match.group("body")


# --------------------------------------------------------------- sections and items


def sections(body: str) -> dict[str, str]:
    """``## Title`` blocks of a Markdown body, in order, as ``{normalized title: text}``.

    Deeper headings stay inside their section; headings inside fenced code are not headings.

    >>> sections("intro\\n## Who\\nAda\\n### Detail\\nmore\\n## Now:\\n- busy\\n")
    {'Who': 'Ada\\n### Detail\\nmore\\n', 'Now': '- busy\\n'}
    """
    result: dict[str, list[str]] = {}
    title, in_fence = None, False
    for line in normalize_newlines(body).split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING_RE.match(line)
        if heading and len(heading.group("hashes")) == 2:
            title = normalize_title(heading.group("title"))
            result.setdefault(title, [])
        elif title is not None:
            result[title].append(line)
    return {t: ("\n".join(lines).strip("\n") + "\n") if "".join(lines).strip() else "" for t, lines in result.items()}


def sectioned_items(text: str) -> list[tuple[str | None, int, str]]:
    """``(section, line, item)`` for every item of a Markdown document.

    An item is a top-level bullet (``-``, ``*``, ``+``, ``1.``) together with its
    wrapped and nested lines, or a paragraph. Blank lines, headings, thematic breaks,
    HTML comments and fenced code are not items. ``section`` is the enclosing ``##``
    title (normalized), ``None`` before the first one or after a ``#`` heading.
    Blank the frontmatter first (:func:`blank_frontmatter`) if the text has one.

    >>> sectioned_items(blank_frontmatter("---\\nname: Ada\\n---\\n# Ada\\n## Write to them:\\n- Short. [source: operator]\\n### Detail\\n- More.\\n"))
    [('Write to them', 6, 'Short. [source: operator]'), ('Write to them', 8, 'More.')]
    """
    visible = _COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), normalize_newlines(text))
    found: list[tuple[str | None, int, str]] = []
    section: str | None = None
    current: list | None = None
    in_fence = False

    def close() -> None:
        nonlocal current
        if current is not None:
            found.append((current[0], current[1], " ".join(current[2])))
        current = None

    for number, line in enumerate(visible.split("\n"), start=1):
        if _FENCE_RE.match(line):
            close()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.strip() or _THEMATIC_BREAK_RE.match(line):
            close()
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            close()
            depth = len(heading.group("hashes"))
            if depth == 2:
                section = normalize_title(heading.group("title"))
            elif depth == 1:
                section = None
            continue
        bullet = _BULLET_RE.match(line)
        if bullet and len(bullet.group("indent").expandtabs(4)) < 2:
            close()
            current = [section, number, [bullet.group("text").strip()]]
        elif current is not None:
            current[2].append(line.strip())
        else:
            current = [section, number, [line.strip()]]
    close()
    return found


def items(text: str) -> list[tuple[int, str]]:
    """``(line, item)`` for every item, where an item is a bullet with its wrapped and nested lines, or a paragraph.

    >>> doc = "- one\\n  continued\\n  - nested\\n\\nA paragraph\\nwrapped.\\n```\\n- code, not an item\\n```\\n+ two\\n3. three\\n"
    >>> items(doc)
    [(1, 'one continued - nested'), (5, 'A paragraph wrapped.'), (10, 'two'), (11, 'three')]
    """
    return [(number, item) for _, number, item in sectioned_items(text)]


# --------------------------------------------------------------------- source tags


def source_refs(line: str) -> list[str]:
    """Every ``[source: …]`` reference in a piece of text, stripped.

    >>> source_refs("- Short replies. [source: log/2026-09.md#e03] [source: operator]")
    ['log/2026-09.md#e03', 'operator']
    """
    return [match.group("ref").strip() for match in _SOURCE_TAG_RE.finditer(line)]


def source_kind(ref: str) -> str:
    """Classify one source reference.

    One of ``url``, ``file``, ``self``, ``operator``, ``none-located``, ``other``
    (free text: accepted, not checkable), or a defect: ``self-unquoted``,
    ``placeholder``, ``date-only``, ``empty``.

    >>> [source_kind(r) for r in ["https://example.org/x", "log/2026-09.md#e01", 'self: "email me the files"',
    ...     "self, it's what they're like", "operator", "none located", "11/09/2026", "Sept 11, 2026 10:00",
    ...     "unknown", "", "call with the team"]]
    ['url', 'file', 'self', 'self-unquoted', 'operator', 'none-located', 'date-only', 'date-only', 'placeholder', 'empty', 'other']
    """
    ref = " ".join(ref.split())
    lowered = ref.lower()
    if not ref:
        return "empty"
    if re.match(r"https?://\S+", ref):
        return "url"
    if lowered.startswith(NONE_LOCATED):
        return "none-located"
    if lowered.strip(" .!") in _PLACEHOLDERS or re.match(r"(inferred|guess|assumed)\b", lowered):
        return "placeholder"
    if not _DATE_NOISE_RE.sub("", ref).strip():
        return "date-only"
    if re.match(r"self\b", lowered):
        return "self" if _QUOTE_RE.search(ref) else "self-unquoted"
    if re.match(r"operator\b", lowered):
        return "operator"
    if re.match(r"[\w./-]+\.(md|yaml|yml|txt)(#\S+)?$", ref):
        return "file"
    return "other"


_VALID_SOURCES = {"url", "file", "self", "operator", "none-located", "other"}


def source_problem(text: str) -> str | None:
    """Why a preference-bearing item is not sourced, or ``None`` when it is.

    A source is a permalink, a file anchor (``log/2026-09.md#e03``), the person's own
    words (``self: "…"``), the operator's statement (``operator``), or an explicit
    ``none located``. A date alone is not a source, and neither is a placeholder.

    >>> source_problem("- Prefers calls.")
    'no [source: …] tag'
    >>> source_problem('- Prefers calls. [source: self: "call me, never email"]') is None
    True
    >>> source_problem("- Prefers calls. [source: self, 2026-09-01]")
    'self-stated sources need the quoted words: [source: self: "…"]'
    >>> source_problem("- Prefers calls. [source: TODO]")
    "'TODO' is a placeholder, not a source: write none located if you looked and found nothing; an inference goes under Hypotheses with its evidence"
    """
    refs = source_refs(text)
    if not refs:
        return "no [source: …] tag"
    kinds = [source_kind(ref) for ref in refs]
    if any(kind in _VALID_SOURCES for kind in kinds):
        return None
    if "placeholder" in kinds:
        return (
            f"{refs[kinds.index('placeholder')]!r} is a placeholder, not a source: write none located "
            "if you looked and found nothing; an inference goes under Hypotheses with its evidence"
        )
    if "self-unquoted" in kinds:
        return 'self-stated sources need the quoted words: [source: self: "…"]'
    if "date-only" in kinds:
        return "a date alone is not a source"
    return "empty [source: ] tag"


# ------------------------------------------------------------------------------ log


def parse_log(text: str) -> list[dict]:
    """Entries of an append-only ``log/YYYY-MM.md`` file, oldest first.

    Headings may use ``·``, ``-`` or ``|`` between their parts; an escaped prose line
    (a leading backslash, see :func:`format_log_entry`) is unescaped.

    >>> entry = format_log_entry("e01", "2026-09-11", "observation", "- kind: rule, they said",
    ...                          source="https://example.org/thread/1")
    >>> parse_log(entry)
    [{'id': 'e01', 'date': '2026-09-11', 'kind': 'observation', 'text': '- kind: rule, they said', 'source': 'https://example.org/thread/1'}]
    """
    text = normalize_newlines(text)
    found = list(_LOG_HEADING_RE.finditer(text))
    entries = []
    for match, following in zip(found, found[1:] + [None]):
        end = following.start() if following else len(text)
        entry = {key: match.group(key) for key in ("id", "date", "kind")}
        prose, fields = [], {}
        for line in text[match.end() : end].strip("\n").split("\n"):
            field = _LOG_FIELD_RE.match(line)
            if field:
                fields[field.group("key")] = field.group("value").strip()
            elif line.strip():
                prose.append((line[1:] if line.startswith("\\") else line).rstrip())
        entries.append({**entry, "text": "\n".join(prose), **fields})
    return entries


def next_log_id(text: str) -> str:
    """The next free entry id in a log, counting every ``## eNN`` heading however it is written.

    >>> next_log_id("## e01 · 2026-09-01 · observation\\nx\\n## e07 - 2026-09-02 - note\\ny\\n")
    'e08'
    >>> next_log_id("")
    'e01'
    """
    numbers = [int(n) for n in _LOG_ID_RE.findall(normalize_newlines(text))]
    return f"e{max(numbers, default=0) + 1:02d}"


def format_log_entry(
    entry_id: str, date: str, kind: str, text: str, *, source: str | None = None, **fields: str
) -> str:
    """One log entry: a ``## id · date · kind`` heading, the observation on one line, then ``- key: value`` fields.

    An observation that would read as a field, a heading or a list item is escaped with a
    leading backslash, so captured text can never forge an entry or change its kind.
    """
    line = " ".join(text.split())
    if _NEEDS_ESCAPE_RE.match(line):
        line = "\\" + line
    lines = [f"## {entry_id} · {date} · {kind}", line]
    if source is not None:
        lines.append(f"- source: {' '.join(source.split())}")
    lines += [f"- {key}: {' '.join(str(value).split())}" for key, value in fields.items() if value]
    return "\n".join(lines) + "\n"
