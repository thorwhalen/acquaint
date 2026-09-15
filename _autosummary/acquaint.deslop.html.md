# acquaint.deslop

The deterministic half of deslop: find the patterns that make prose read as machine-written, scaled to the reader.

How strict the check is depends on the recipient’s tolerance of AI-sounding text,
recorded as `ai_tolerance` in their `style.md` (`tolerant`, `neutral`,
`averse`; anything else counts as unknown, which is neutral):

- **tolerant** enforces tier E only, with looser counts;
- **neutral** enforces E and W;
- **averse** enforces E, W and S, with the tightest counts.

Findings outside the enforced tiers are still reported, marked `enforced: False`.
The catalogue is data (`acquaint/data/deslop/tells.yaml`) and a keyword argument,
so a list derived from the operator’s own writing can replace it without code changes.

```pycon
>>> result = lint_text("Great question! This robust tool serves as a bridge.", tolerance="neutral")
>>> sorted({f["rule"] for f in result["findings"] if f["enforced"]})
['ai-vocabulary', 'chat-leftover', 'copula-avoidance']
>>> lint_text("Sending the export on Friday. Two sites, not five.")["ok"]
True
```

### Functions

| [`lint_text`](#acquaint.deslop.lint_text)(text, \*[, tolerance, blocklist, ...])   | Check a draft against the tells catalogue at a reader's tolerance: `{"ok", "findings", "metrics", "relational"}`.   |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| [`normalize_tolerance`](#acquaint.deslop.normalize_tolerance)(value)                         | A recorded `ai_tolerance` as one of `TOLERANCES`, with a warning when it was something else.                        |
| [`recipient_card`](#acquaint.deslop.recipient_card)(entity)                             | What the check needs from a recipient's writing card (`style.md`): tolerance, disclosure, blocklist, warnings.      |
| [`text_metrics`](#acquaint.deslop.text_metrics)(text)                                 | Counts the checks use: words, sentences, sentence-length variation, em-dash rate, headers, bold.                    |

### acquaint.deslop.lint_text(text, , tolerance='neutral', blocklist=(), catalog=None)

Check a draft against the tells catalogue at a reader’s tolerance: `{"ok", "findings", "metrics", "relational"}`.

`blocklist` holds phrases this recipient’s card says never to use; each hit is
tier E. `catalog` replaces the shipped catalogue (same schema as `tells.yaml`).
An unrecognised `tolerance` is an error here; normalise recorded values first
with [`normalize_tolerance()`](#acquaint.deslop.normalize_tolerance).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### acquaint.deslop.normalize_tolerance(value)

A recorded `ai_tolerance` as one of `TOLERANCES`, with a warning when it was something else.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]

```pycon
>>> normalize_tolerance("Averse"), normalize_tolerance(None)
(('averse', None), ('unknown', None))
>>> normalize_tolerance("low")[0]
'unknown'
```

### acquaint.deslop.recipient_card(entity)

What the check needs from a recipient’s writing card (`style.md`): tolerance, disclosure, blocklist, warnings.

`ai_tolerance` and `disclosure` come from the card’s frontmatter. Blocklist
phrases are the items of its `## Blocklist` section: the quoted phrase when an item
quotes one, else the item without its source tag.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### acquaint.deslop.text_metrics(text)

Counts the checks use: words, sentences, sentence-length variation, em-dash rate, headers, bold.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> text_metrics("One two three. Four five!")["sentences"]
2
```
