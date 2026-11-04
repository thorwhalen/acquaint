# acquaint.digests

Digests: what a conversation with an entity said, written up through a watermark.

A digest is one Markdown file per conversation, in the entity’s folder
(`people/<id>/digests/<name>.md`, and the same under projects, orgs and groups). Its
frontmatter is the state of the processing, and its body is the notes:

```yaml
schema: acquaint/digest/v1
ref: whatsapp:ada-lovelace        # the correspond conversation reference: the SSOT
archive: correspond               # where the raw messages live (never this store)
through:                          # the watermark, per scope: processed up to this time
  content: '2026-11-03T19:37:47+01:00'
  style: '2026-06-21T19:27:45+02:00'
updated: '2026-11-04'
```

`through` answers “from which date and time is this conversation new?”: hand it to
`correspond read <ref> --since <through>` to get what has not been processed. Two scopes
exist because a conversation can be mined for how someone writes (`style`, the
**acquaint-profile** skill) separately from what it said (`content`, the
**acquaint-digest** skill).

The body has five sections: *Orientation* (who is in it, what it is for, its span),
*Takeaways* (decisions, agreements, asks, facts the operator will need), *Themes* (the
recurring subjects, each with where it comes up), *Index* (the conversation cut into
dated sections so an agent can go straight to one) and *Open threads* (what is waiting on
whom). Every item in those sections carries an anchor, `[at: <ISO time>]` (a message time
in the archive: `rg -n '^2026-07-03T14:02' <transcript>`) or a `[source: …]`; the
messages themselves stay in the archive, never here (`POLICY.md`: no whole message
bodies).

```pycon
>>> digest_name("whatsapp:ada-lovelace"), digest_name("github:example/demo#12")
('digests/whatsapp-ada-lovelace.md', 'digests/github-example-demo-12.md')
```

### Module Attributes

| [`SCOPES`](#acquaint.digests.SCOPES)            | what the conversation said, and how its author writes.                |
|--------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`ANCHORED_SECTIONS`](#acquaint.digests.ANCHORED_SECTIONS) | Sections whose every item needs an `[at: …]` or `[source: …]` anchor. |

### Functions

| [`digest_name`](#acquaint.digests.digest_name)(ref)                              | The digest's file name inside the entity's folder, derived from the reference.                           |
|------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------|
| [`digest_problems`](#acquaint.digests.digest_problems)(text)                         | `(severity, line, rule, message)` for one digest file: frontmatter shape, unanchored items, long quotes. |
| [`digests`](#acquaint.digests.digests)(entity)                               | Every digest of the entity: its reference, file and watermarks.                                          |
| [`find_digest`](#acquaint.digests.find_digest)(entity, ref)                      | The digest of one conversation, found by the `ref` in its frontmatter (else by file name).               |
| [`mark_digest`](#acquaint.digests.mark_digest)(entity, ref, through, \*[, ...])  | Move the watermark of `scope` to `through`.                                                              |
| [`new_digest`](#acquaint.digests.new_digest)(entity, ref, \*[, archive, today]) | Create the digest of `ref` from its template, with no watermark yet.                                     |

### acquaint.digests.ANCHORED_SECTIONS *= ('Takeaways', 'Themes', 'Index', 'Open threads')*

Sections whose every item needs an `[at: …]` or `[source: …]` anchor.

### acquaint.digests.SCOPES *= ('content', 'style')*

what the conversation said, and how its author writes.

* **Type:**
  What a watermark can cover

### acquaint.digests.digest_name(ref)

The digest’s file name inside the entity’s folder, derived from the reference.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### acquaint.digests.digest_problems(text)

`(severity, line, rule, message)` for one digest file: frontmatter shape, unanchored items, long quotes.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`int`](https://docs.python.org/3/builtins/functions.html#int) | [`None`](https://docs.python.org/3/builtins/constants.html#None), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### acquaint.digests.digests(entity)

Every digest of the entity: its reference, file and watermarks.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### acquaint.digests.find_digest(entity, ref)

The digest of one conversation, found by the `ref` in its frontmatter (else by file name).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### acquaint.digests.mark_digest(entity, ref, through, , scope='content', force=False, today=None)

Move the watermark of `scope` to `through`. Moving it back needs `force`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### acquaint.digests.new_digest(entity, ref, , archive='correspond', today=None)

Create the digest of `ref` from its template, with no watermark yet. Refuses when one exists.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
