# acquaint.trust

The disclosure vocabulary: tiers on people; labels, seals and clearances on records; and which tier is in force.

What a reader may be told is decided by the operator and evaluated by code, so its words
are fixed here and nowhere else. Where they are written:

- `trust.yaml` beside a person’s entry file:
  `{tiers: [{tier, valid_from, valid_to, review_by, recorded, source, note}]}`;
- any record’s frontmatter: `label`, `sealed_from`, `vocabulary`, `clearance` (orgs
  and groups), `default_tier` (orgs and projects), and `label_source`;
- one fact line: `[label: …]` and `[sealed-from: …]` beside its `[source: …]`.

A tier records a disclosure consequence, never a judgement of the person. Only the
operator grants one. Nothing here reads a store: these are pure functions over parsed
records, and [`acquaint.lint`](acquaint.html.md#acquaint.lint) says what is wrong with them.

```pycon
>>> tiers = [
...     {"tier": "reviewed", "valid_from": "2026-01-01", "valid_to": "2026-09-01", "source": "operator"},
...     {"tier": "open", "valid_from": "2026-09-01", "review_by": "2026-11-01", "source": "operator"},
... ]
>>> tier_in_force(tiers, today="2026-09-15")["tier"], effective_tier(tiers, today="2026-09-15")
('open', ('open', False))
>>> effective_tier(tiers, today="2026-11-02")
('need-to-know', True)
>>> entity_label({}, "project"), entity_label({}, "person"), entity_label({"label": "red"}, "person")
('amber', 'green', 'red')
```

### Module Attributes

| [`TIERS`](#acquaint.trust.TIERS)               | One ordinal scale, most permissive first.                                                                                    |
|----------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| [`PERMISSIVE_TIERS`](#acquaint.trust.PERMISSIVE_TIERS)    | The tiers that need a `review_by` and lapse to [`DEFAULT_TIER`](#acquaint.trust.DEFAULT_TIER) once it passes. |
| [`DEFAULT_TIER`](#acquaint.trust.DEFAULT_TIER)        | The tier of anyone without one in force.                                                                                     |
| [`LABELS`](#acquaint.trust.LABELS)              | Traffic Light Protocol names, most restrictive first.                                                                        |
| [`TRUST_SOURCES`](#acquaint.trust.TRUST_SOURCES)       | the operator, or the person's own quoted words.                                                                              |
| [`OPERATOR_SET_FIELDS`](#acquaint.trust.OPERATOR_SET_FIELDS) | Frontmatter fields that need `label_source: operator`.                                                                       |

### Functions

| [`effective_tier`](#acquaint.trust.effective_tier)(tiers, \*, today)   | `(tier, lapsed)` for today: the tier in force, [`DEFAULT_TIER`](#acquaint.trust.DEFAULT_TIER) in place of a lapsed one.   |
|-------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| [`entity_label`](#acquaint.trust.entity_label)(meta, kind)           | A record's label: its frontmatter `label`, else `green` for a person and `amber` for anything else.                                      |
| [`fact_label`](#acquaint.trust.fact_label)(text, record_label)     | One fact's label: its own `[label: …]` tag, else the label of the record it sits in.                                                     |
| [`is_lapsed`](#acquaint.trust.is_lapsed)(entry, \*, today)        | Whether a permissive tier's review is overdue, or was never scheduled.                                                                   |
| [`tier_in_force`](#acquaint.trust.tier_in_force)(tiers, \*, today)    | The entry whose validity covers `today` (from `valid_from`, up to but not including `valid_to`).                                         |

### acquaint.trust.DEFAULT_TIER *= 'need-to-know'*

The tier of anyone without one in force.

### acquaint.trust.LABELS *= ('red', 'amber', 'green', 'clear')*

Traffic Light Protocol names, most restrictive first. Also the clearance values.

### acquaint.trust.OPERATOR_SET_FIELDS *= ('label', 'sealed_from', 'clearance', 'default_tier')*

Frontmatter fields that need `label_source: operator`.

### acquaint.trust.PERMISSIVE_TIERS *= ('open', 'involved')*

The tiers that need a `review_by` and lapse to [`DEFAULT_TIER`](#acquaint.trust.DEFAULT_TIER) once it passes.

### acquaint.trust.TIERS *= ('open', 'involved', 'need-to-know', 'reviewed')*

One ordinal scale, most permissive first.

### acquaint.trust.TRUST_SOURCES *= ('operator', 'self')*

the operator, or the person’s own quoted words.

* **Type:**
  The only sources a tier may have

### acquaint.trust.effective_tier(tiers, , today)

`(tier, lapsed)` for today: the tier in force, [`DEFAULT_TIER`](#acquaint.trust.DEFAULT_TIER) in place of a lapsed one.

`None` when no entry covers today (what applies then, a linked org’s
`default_tier` or the default, is the disclosure computation’s question). An
unknown tier value reads as `reviewed`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None), [`bool`](https://docs.python.org/3/builtins/functions.html#bool)]

```pycon
>>> effective_tier([{"tier": "trusted"}], today="2026-09-15"), effective_tier([], today="2026-09-15")
(('reviewed', False), (None, False))
```

### acquaint.trust.entity_label(meta, kind)

A record’s label: its frontmatter `label`, else `green` for a person and `amber` for anything else.

A label that is not one of [`LABELS`](#acquaint.trust.LABELS) reads as `red`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### acquaint.trust.fact_label(text, record_label)

One fact’s label: its own `[label: …]` tag, else the label of the record it sits in.

A malformed or unknown tag reads as `red`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> fact_label("- Heron ships in October. [label: amber] [source: operator]", "green")
'amber'
>>> fact_label("- Prefers email. [source: operator]", "green"), fact_label("- x [label: purple]", "green")
('green', 'red')
```

### acquaint.trust.is_lapsed(entry, , today)

Whether a permissive tier’s review is overdue, or was never scheduled. Restrictive tiers never lapse.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> is_lapsed({"tier": "involved"}, today="2026-09-15"), is_lapsed({"tier": "reviewed"}, today="2026-09-15")
(True, False)
```

### acquaint.trust.tier_in_force(tiers, , today)

The entry whose validity covers `today` (from `valid_from`, up to but not including `valid_to`).

Superseded entries stay in the file with their `valid_to`; when two still overlap,
the later `valid_from` wins, then the later entry.

* **Return type:**
  [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> tier_in_force([{"tier": "open", "valid_from": "2026-10-01"}], today="2026-09-15") is None
True
```
