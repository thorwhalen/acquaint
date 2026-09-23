# acquaint.lookup

Finding the right record: exact references, handle resolution, the conflation check, and channel choice.

All functions take a [`Store`](acquaint.store.md#acquaint.store.Store) and return plain data. Matching is
deterministic normalisation (case, punctuation and accents ignored). Nothing here acts
on a partial match or picks between candidates: an id and another record’s exact alias
compete on equal terms, partials are offered as suggestions, and [`find_entity()`](#acquaint.lookup.find_entity)
refuses when more than one record fits. One unreadable record is reported and skipped;
it never takes a lookup down.

### Module Attributes

| [`TIERS`](#acquaint.lookup.TIERS)            | Who set a rule, most authoritative first.                                              |
|-------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| [`USABLE_STATUSES`](#acquaint.lookup.USABLE_STATUSES)  | An identity is usable only with one of these statuses (none recorded means active).    |
| [`INACTIVE_RULES`](#acquaint.lookup.INACTIVE_RULES)   | A rule is out of use with one of these statuses.                                       |
| [`NO_CHANNEL_NAMED`](#acquaint.lookup.NO_CHANNEL_NAMED) | What a channel entry is called when its rule named none, so no repr stands in for one. |

### Functions

| [`check_text`](#acquaint.lookup.check_text)(store, text)                         | Scan prose for people errors before it is published.                                                                                    |
|--------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| [`find_entity`](#acquaint.lookup.find_entity)(store, ref, \*[, names])            | The one store key a reference names, or an `AcquaintError` saying why not.                                                              |
| [`match`](#acquaint.lookup.match)(store, query)                             | Store keys matching a name, alias, handle, email or id: `{"exact": [...], "partial": [...], "unreadable": [...]}`.                      |
| [`normalise_handle`](#acquaint.lookup.normalise_handle)(platform, value)               | A handle's comparable form: an email lowercased, with Gmail dots and `+tags` folded; any other value lowercased, without a leading `@`. |
| [`normalize`](#acquaint.lookup.normalize)(text)                                 | Lowercase ASCII letters and digits only, for comparing names and handles.                                                               |
| [`reach_channels`](#acquaint.lookup.reach_channels)(store, key, \*[, defaults_text]) | Ordered channels for reaching one entity in a context (`purpose`, `urgency`, `project`, `message_type`, `topic`).                       |
| [`resolve_handle`](#acquaint.lookup.resolve_handle)(store, handle)                   | Who a channel handle belongs to, with the evidence: `{"platform", "matches", "inactive", "by_name", "unreadable"}`.                     |

### acquaint.lookup.INACTIVE_RULES *= {'dead', 'draft', 'expired', 'retracted', 'superseded'}*

A rule is out of use with one of these statuses.

### acquaint.lookup.NO_CHANNEL_NAMED *= '(no channel named)'*

What a channel entry is called when its rule named none, so no repr stands in for one.

### acquaint.lookup.TIERS *= ('self', 'operator', 'affiliation', 'observed', 'default')*

Who set a rule, most authoritative first. The operator’s instruction for the message
at hand outranks all of these; it belongs to the caller, not the store.

### acquaint.lookup.USABLE_STATUSES *= {'active', 'relay'}*

An identity is usable only with one of these statuses (none recorded means active).
Anything else (stale, former, unverified, retracted, dead, …) is reported, never acted on.

### acquaint.lookup.check_text(store, text)

Scan prose for people errors before it is published.

Reports the entities mentioned; **conflations** (one entity written as if it were two:
two different names for it joined by “or”, “and”, “/”, “,” …, citation order such as
“Lovelace, Ada” excepted); **ambiguous** forms shared by several entities; and
**unknown** name-like phrases that match nobody.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### acquaint.lookup.find_entity(store, ref, , names=True)

The one store key a reference names, or an `AcquaintError` saying why not.

`person:ada-lovelace` and `people/ada-lovelace` are exact and decide on their own.
A bare word is looked up as an id (in any kind, any case) and, with `names`, as an
exact name, alias, handle or email; it resolves only when exactly one record fits all
of these together. A partial match never counts; it is offered as a suggestion.
Operations that rewrite or remove records pass `names=False` and need the id.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### acquaint.lookup.match(store, query)

Store keys matching a name, alias, handle, email or id: `{"exact": [...], "partial": [...], "unreadable": [...]}`.

`partial` holds entities where the query is part of a longer form (three characters
or more): suggestions for a person, never something to act on.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)]

### acquaint.lookup.normalise_handle(platform, value)

A handle’s comparable form: an email lowercased, with Gmail dots and `+tags` folded; any other value lowercased, without a leading `@`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### acquaint.lookup.normalize(text)

Lowercase ASCII letters and digits only, for comparing names and handles.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> normalize("Zoë O'Example")
'zoeoexample'
```

### acquaint.lookup.reach_channels(store, key, , defaults_text='', \*\*context)

Ordered channels for reaching one entity in a context (`purpose`, `urgency`, `project`, `message_type`, `topic`).

Precedence: the person’s own stated rules > the operator’s rules about them > norms of
a project or affiliation > observed habits > global defaults. Within a tier the most
specific matching rule wins. Only usable addresses are offered; a rule value that is
not a channel name is skipped with a note. It returns addresses; it sends nothing.

Each channel carries `address_kind`: `stated` when a rule gave the address,
`identity` when it was built from one of the entity’s identities, `None` when
there is no address. The distinction matters because an identity-built address is a
*handle* (`github:ada`), and a channel addressed by conversation rather than by
person (GitHub, a web inbox, a chat channel) does not take one. Such a channel’s rule
states its address.

A channel’s **position** is decided by the best-placed rule that names it; its
**address** by the best-placed rule that states one, which may be a different rule. A
rule that names a channel without stating an address expresses no opinion about where
that channel goes, so it does not bury an address a lower-placed rule states; the note
says which rule file the address came from when the two differ.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### acquaint.lookup.resolve_handle(store, handle)

Who a channel handle belongs to, with the evidence: `{"platform", "matches", "inactive", "by_name", "unreadable"}`.

`github:octocat`, `email:ada@example.org` and `ada@example.org` name a platform;
`@octocat` does not, so it matches that handle on any platform. Only identities with
a usable status (see [`USABLE_STATUSES`](#acquaint.lookup.USABLE_STATUSES)) are matches; the rest are reported under
`inactive` with their status. A handle found in no identity file is matched against
names under `by_name`, which is never enough to act on.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
