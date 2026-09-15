# What this store may hold

This folder holds the operator's working notes about people and what they are involved in. Its purpose is **communication assistance only**: reaching the right person on the right channel, and writing and reading messages well. It is never used to screen, rank, evaluate or persuade people.

## The test for every line

**Would this line survive being handed to the person it is about?** People can generally ask to see notes and opinions recorded about them. Write observable behaviour ("replies in one or two lines; answers only the first question"), never judgements ("difficult").

## Every preference, view and rule carries its source

End the bullet with a source tag: `[source: https://…]` (a permalink), `[source: log/2026-09.md#e03]` (the observation it came from), `[source: self: "their own words"]`, `[source: operator]`, or `[source: none located]` when you looked and found nothing. **A date alone is not a source.** A nested bullet is its own line and needs its own source. `acquaint lint` fails on violations.

An unsourced claim recorded with a date is worse than no record: the date makes it look observed.

## Never record

1. Special-category data, stated **or inferred**: health, ethnicity, religion or philosophy, political opinions, trade-union membership, sex life or sexual orientation, genetic or biometric data.
2. Government ID numbers, financial account numbers, criminal history, immigration status.
3. Credentials of any kind.
4. Personality labels (DISC, MBTI, Big Five) as facts. Record the behaviour you saw instead, with its source.
5. Moods, transient emotional states, gossip.
6. Whole message bodies. Keep a short quote and a link to the source.
7. Anything learned in confidence that the person would not expect the operator's tools to keep.

A self-stated form of address may be recorded, because courtesy needs it. It is never inferred.

## How records change

- During any task, agents only **append** observations (`acquaint remember`). They change rules only when the person or the operator states the rule.
- Turning observations into profile lines is a separate, reviewed pass. A style note needs two or more independent observations. Superseded lines are marked, not deleted.
- Identities are never merged on a single shared attribute. Record "not the same person" when you learn it.
- `Now` entries carry an `(until: YYYY-MM-DD)` and expire.

## Who may be told what

**Only the operator grants trust. A tier records a consequence, not a judgement:** it says what happens to messages, never what the person is like, so it passes the test above.

- **Tiers**, in `trust.yaml` beside a person's entry file: `open` (may hear about the operator's other work), `involved`, `need-to-know` (the default), or `reviewed` (every message to them is approved first). Each entry has `valid_from`, `valid_to`, `recorded` and a `source` that is `operator` or the person's own quoted words (`self: "…"`). `open` and `involved` need a `review_by`, and count as `need-to-know` once it passes. A changed tier is a new entry; the old one keeps its `valid_to`.
- **Labels, seals and vocabulary**, in any record's frontmatter: `label` (`red` > `amber` > `green` > `clear`; projects, orgs and groups default to `amber`, people to `green`), `sealed_from` (ids of people who must hear nothing about it, whatever their tier), `vocabulary` (codenames and internal terms beyond `name` and `aka`), `clearance` (orgs and groups: what members who cannot be listed may hear) and `default_tier` (orgs and projects: the tier of people linked only through them). A label, seal, clearance or default tier needs `label_source: operator`.
- **Facts**: one line may carry `[label: amber]` or `[sealed-from: ada-lovelace]` beside its source tag. An untagged line has its record's label.

`acquaint lint` fails on a tier or label the operator did not set, an unknown value, a permissive tier without a review date, a seal naming nobody, and a malformed tag. It warns on a lapsed tier, a project listed in a public repository whose label is not `clear`, and a seal on someone linked to the sealed record.

## Legitimate interest

<!-- The operator's one-page note: the professional interest served, why these notes are needed for it, and why keeping them does not override the people's own interests. Write it before the store holds people other than yourself. -->

## Forgetting

`acquaint forget <id> --confirm` removes the folder and writes a hashed tombstone, so the person is not silently re-created. Deleting a folder does not remove it from git history; the command prints the history-rewrite steps.

## What syncing does not protect

A private GitHub repository is access control, not encryption: the host can read everything. A pre-push hook is skipped by `git push --no-verify`. File names and commit messages contain people's names. `git-remote-gcrypt` encrypts contents, names and history, and is the upgrade when this matters.
