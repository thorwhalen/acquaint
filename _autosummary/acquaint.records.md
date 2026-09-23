# acquaint.records

The text formats acquaint stores, as pure functions: frontmatter, sections, items, source tags, slugs, log entries.

Nothing here touches a filesystem. A record is text in and data out, so the same
rules hold whether the text came from disk, a `dict` or a remote store. Every parser
accepts `\r\n` line endings and a leading byte-order mark, because a store edited on
Windows will have them.

The formats are deliberately hand-editable Markdown: YAML frontmatter for what a
machine looks up, `## Sections` of items for what a person writes, and an inline
`[source: …]` tag on every item that states a preference, a view or a rule (beside it, a
fact may carry `[label: …]` and `[sealed-from: …]`, read by the same tag reader). Sections,
items and code blocks follow CommonMark’s rules closely enough that what a reader sees
as one line under a heading is what the lint checks.

```pycon
>>> slugify("Ada Lovelace")
'ada-lovelace'
>>> meta, body, errors = split_frontmatter("\ufeff---\r\nname: Ada\r\n---\r\n## Who\r\n- a mathematician\r\n")
>>> meta, list(sections(body)), errors
({'name': 'Ada'}, ['Who'], [])
>>> source_problem("- Prefers email. [source: https://example.org/thread/1]") is None
True
>>> source_problem("- Prefers email. [source: 11th September 2026]")
'a date alone is not a source'
```

### Module Attributes

| [`NONE_LOCATED`](#acquaint.records.NONE_LOCATED)   | The words that say "no primary source was found", out loud.   |
|-----------------------------------------------------------------|---------------------------------------------------------------|

### Functions

| [`blank_frontmatter`](#acquaint.records.blank_frontmatter)(text)                          | The text with its frontmatter lines emptied, so line numbers still match the file.                                           |
|---------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| [`disclosed_refs`](#acquaint.records.disclosed_refs)(value)                            | The record references a log entry's `disclosed:` field lists, lowercased: `project:heron, org:example` or `[project:heron]`. |
| [`dump_yaml`](#acquaint.records.dump_yaml)(data)                                  | Write YAML the way a person would: keys in order, short lists inline, unicode kept.                                          |
| [`fact_tags`](#acquaint.records.fact_tags)(text)                                  | The label and seals one fact carries, and what is wrong with how they are written.                                           |
| [`format_log_entry`](#acquaint.records.format_log_entry)(entry_id, date, kind, text, \*) | One log entry: a `## id · date · kind` heading, the observation on one line, then `- key: value` fields.                     |
| [`item_blocks`](#acquaint.records.item_blocks)(text)                                | `(section, first_line, last_line, item)` for every item of a Markdown document.                                              |
| [`items`](#acquaint.records.items)(text)                                      | `(line, item)` for every item: each bullet with its wrapped lines, or a paragraph.                                           |
| [`join_frontmatter`](#acquaint.records.join_frontmatter)(meta, body)                     | The inverse of [`split_frontmatter()`](#acquaint.records.split_frontmatter).                                         |
| [`load_yaml`](#acquaint.records.load_yaml)(text)                                  | Parse YAML into JSON-ready data, returning `(data, errors)` instead of raising: these files are hand-edited.                 |
| [`next_log_id`](#acquaint.records.next_log_id)(text)                                | The next free entry id in a log, counting every `## eNN` heading however it is written.                                      |
| [`normalize_newlines`](#acquaint.records.normalize_newlines)(text)                         | `\r\n` and lone `\r` as `\n`, without a leading byte-order mark.                                                             |
| [`normalize_title`](#acquaint.records.normalize_title)(title)                           |                                                                                                                              |
| [`parse_log`](#acquaint.records.parse_log)(text)                                  | Entries of an append-only `log/YYYY-MM.md` file, oldest first.                                                               |
| [`sectioned_items`](#acquaint.records.sectioned_items)(text)                            | `(section, line, item)` for every item: see [`item_blocks()`](#acquaint.records.item_blocks).                  |
| [`sections`](#acquaint.records.sections)(body)                                   | `## Title` blocks of a Markdown body, in order, as `{normalized title: text}`.                                               |
| [`slugify`](#acquaint.records.slugify)(name, \*[, qualifier])                   | A readable, ASCII-folded, lowercase id: `given-family`, plus `--qualifier` on a collision.                                   |
| [`source_kind`](#acquaint.records.source_kind)(ref)                                 | Classify one source reference.                                                                                               |
| [`source_problem`](#acquaint.records.source_problem)(text)                             | Why a preference-bearing item is not sourced, or `None` when it is.                                                          |
| [`source_refs`](#acquaint.records.source_refs)(line)                                | Every `[source: …]` reference in a piece of text, stripped.                                                                  |
| [`split_frontmatter`](#acquaint.records.split_frontmatter)(text)                          | Split `---` YAML frontmatter from a Markdown body: `(meta, body, errors)`.                                                   |
| [`tags`](#acquaint.records.tags)(text)                                       | Every `[source: …]`, `[label: …]` and `[sealed-from: …]` tag in a piece of text: `(name, value)`, in order.                  |

### acquaint.records.NONE_LOCATED *= ('none located', 'no primary source located', 'no source located')*

The words that say “no primary source was found”, out loud.

### acquaint.records.blank_frontmatter(text)

The text with its frontmatter lines emptied, so line numbers still match the file.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> blank_frontmatter("---\nname: Ada\n---\nbody\n")
'\n\n\nbody\n'
```

### acquaint.records.disclosed_refs(value)

The record references a log entry’s `disclosed:` field lists, lowercased: `project:heron, org:example` or `[project:heron]`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> disclosed_refs("[project:heron, Org:Example-Client]"), disclosed_refs(""), disclosed_refs(["project:heron"])
(['project:heron', 'org:example-client'], [], ['project:heron'])
```

### acquaint.records.dump_yaml(data)

Write YAML the way a person would: keys in order, short lists inline, unicode kept.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> print(dump_yaml({"name": "Ada", "aka": ["Ada", "Lovelace"], "links": [{"to": "org:x"}]}), end="")
name: Ada
aka: [Ada, Lovelace]
links:
- to: org:x
```

### acquaint.records.fact_tags(text)

The label and seals one fact carries, and what is wrong with how they are written.

`{"label": str | None, "sealed_from": [ids], "problems": [messages]}`. The label is
returned lowercased and unchecked: which labels exist is [`acquaint.trust`](acquaint.trust.md#module-acquaint.trust)’s
business. A tag that starts like `[label` or `[sealed from` but is not written
`[label: <label>]` or `[sealed-from: <id>, <id>]` is a problem, never ignored.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> fact_tags("- Cy is changing jobs. [label: red] [sealed-from: bram, person:dee] [source: operator]")
{'label': 'red', 'sealed_from': ['bram', 'person:dee'], 'problems': []}
>>> for problem in fact_tags("- Heron slips. [label amber] [sealed_from: bram] [source: operator]")["problems"]:
...     print(problem)
'[label amber]' is not a tag acquaint reads; write [label: <label>]
'[sealed_from: bram]' is not a tag acquaint reads; write [sealed-from: <id>, <id>]
```

### acquaint.records.format_log_entry(entry_id, date, kind, text, , source=None, \*\*fields)

One log entry: a `## id · date · kind` heading, the observation on one line, then `- key: value` fields.

An observation that would read as a field, a heading or a list item is escaped with a
leading backslash, so captured text can never forge an entry or change its kind.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### acquaint.records.item_blocks(text)

`(section, first_line, last_line, item)` for every item of a Markdown document.

An item is one bullet (`-`, `*`, `+`, `1.`) at any depth, together with the
wrapped lines under it, or a paragraph. A nested bullet is an item of its own, so it
needs its own source. Blank lines, headings, thematic breaks, HTML comments and fenced
code are not items. `section` is the enclosing `##` title (normalized), `None`
before the first one or after a `#` heading. Blank the frontmatter first
([`blank_frontmatter()`](#acquaint.records.blank_frontmatter)) if the text has one.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None), [`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### acquaint.records.items(text)

`(line, item)` for every item: each bullet with its wrapped lines, or a paragraph.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

```pycon
>>> doc = "- one\n  continued\n  - nested\n\nA paragraph\nwrapped.\n```\n- code, not an item\n```\n+ two\n3. three\n"
>>> items(doc)
[(1, 'one continued'), (3, 'nested'), (5, 'A paragraph wrapped.'), (10, 'two'), (11, 'three')]
```

### acquaint.records.join_frontmatter(meta, body)

The inverse of [`split_frontmatter()`](#acquaint.records.split_frontmatter).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> join_frontmatter({"name": "Ada"}, "## Who\n")
'---\nname: Ada\n---\n\n## Who\n'
```

### acquaint.records.load_yaml(text)

Parse YAML into JSON-ready data, returning `(data, errors)` instead of raising: these files are hand-edited.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

```pycon
>>> load_yaml("a: [1, 2]\nb: !!set {x: null}")
({'a': [1, 2], 'b': ['x']}, [])
>>> data, errors = load_yaml("a: [1, 2")
>>> data, bool(errors)
(None, True)
```

### acquaint.records.next_log_id(text)

The next free entry id in a log, counting every `## eNN` heading however it is written.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> next_log_id("## e01 · 2026-09-01 · observation\nx\n## e07 - 2026-09-02 - note\ny\n")
'e08'
>>> next_log_id("")
'e01'
```

### acquaint.records.normalize_newlines(text)

`\r\n` and lone `\r` as `\n`, without a leading byte-order mark.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> normalize_newlines("\ufeffa\r\nb\rc")
'a\nb\nc'
```

### acquaint.records.normalize_title(title)

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

A heading as written, minus decoration: closing 

```
``
```

#\`\`s, a trailing colon, typographic apostrophes, extra space.

```pycon
>>> normalize_title("  Don’t:  ## ")
"Don't"
```

### acquaint.records.parse_log(text)

Entries of an append-only `log/YYYY-MM.md` file, oldest first.

Headings may use `·`, `-` or `|` between their parts; an escaped prose line
(a leading backslash, see [`format_log_entry()`](#acquaint.records.format_log_entry)) is unescaped.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

```pycon
>>> entry = format_log_entry("e01", "2026-09-11", "observation", "- kind: rule, they said",
...                          source="https://example.org/thread/1")
>>> parse_log(entry)
[{'id': 'e01', 'date': '2026-09-11', 'kind': 'observation', 'text': '- kind: rule, they said', 'source': 'https://example.org/thread/1'}]
```

### acquaint.records.sectioned_items(text)

`(section, line, item)` for every item: see [`item_blocks()`](#acquaint.records.item_blocks).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None), [`int`](https://docs.python.org/3/builtins/functions.html#int), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

```pycon
>>> sectioned_items(blank_frontmatter("---\nname: Ada\n---\n# Ada\n## Write to them:\n- Short. [source: operator]\n### Detail\n- More.\n"))
[('Write to them', 6, 'Short. [source: operator]'), ('Write to them', 8, 'More.')]
```

### acquaint.records.sections(body)

`## Title` blocks of a Markdown body, in order, as `{normalized title: text}`.

A `#` heading ends the current section; deeper headings stay inside it; headings
inside fenced code and HTML comments are not headings (and comments are left out).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> sections("intro\n## Who\nAda\n### Detail\nmore\n# Aside\nnot in Who\n## Now:\n- busy\n")
{'Who': 'Ada\n### Detail\nmore\n', 'Now': '- busy\n'}
```

### acquaint.records.slugify(name, , qualifier=None)

A readable, ASCII-folded, lowercase id: `given-family`, plus `--qualifier` on a collision.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> slugify("Zoë Ångström")
'zoe-angstrom'
>>> slugify("John Smith", qualifier="Example Org")
'john-smith--example-org'
```

### acquaint.records.source_kind(ref)

Classify one source reference.

One of `url`, `file`, `self`, `operator`, `none-located`, `other`
(free text: accepted, not checkable), or a defect: `self-unquoted`,
`placeholder`, `date-only`, `empty`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> [source_kind(r) for r in ["https://example.org/x", "log/2026-09.md#e01", "self: 'don't email me'",
...     "self, it's what they're like", 'self: " "', "operator", "none located", "2026-09-01T10:00Z",
...     "last Tuesday", "todo: find link", "", "email to Ada on 2026-09-01"]]
['url', 'file', 'self', 'self-unquoted', 'self-unquoted', 'operator', 'none-located', 'date-only', 'date-only', 'placeholder', 'empty', 'other']
```

### acquaint.records.source_problem(text)

Why a preference-bearing item is not sourced, or `None` when it is.

A source is a permalink, a file anchor (`log/2026-09.md#e03`), the person’s own
words (`self: "…"`), the operator’s statement (`operator`), or an explicit
`none located`. A date alone is not a source, and neither is a placeholder.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> source_problem("- Prefers calls.")
'no [source: …] tag'
>>> source_problem('- Prefers calls. [source: self: "call me, never email"]') is None
True
>>> source_problem("- Prefers calls. [source: self, 2026-09-01]")
'self-stated sources need the quoted words: [source: self: "…"]'
>>> source_problem("- Prefers calls. [source: TODO]")
"'TODO' is a placeholder, not a source: write none located if you looked and found nothing; an inference goes under Hypotheses with its evidence"
```

### acquaint.records.source_refs(line)

Every `[source: …]` reference in a piece of text, stripped.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> source_refs("- Short replies. [source: log/2026-09.md#e03] [source: operator]")
['log/2026-09.md#e03', 'operator']
```

### acquaint.records.split_frontmatter(text)

Split `---` YAML frontmatter from a Markdown body: `(meta, body, errors)`.

A malformed header degrades to empty metadata plus an error, never an exception,
so one bad hand edit cannot take down lookups of every other record.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

```pycon
>>> split_frontmatter("no frontmatter here")
({}, 'no frontmatter here', ['no --- frontmatter block at the top of the file'])
```

### acquaint.records.tags(text)

Every `[source: …]`, `[label: …]` and `[sealed-from: …]` tag in a piece of text: `(name, value)`, in order.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

```pycon
>>> tags("- Heron ships in October [label: amber] [Sealed-From: bram] [source: operator 2026-09-15]")
[('label', 'amber'), ('sealed-from', 'bram'), ('source', 'operator 2026-09-15')]
```
