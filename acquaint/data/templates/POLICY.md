# What this store may hold

This folder holds the operator's working notes about people and what they are involved in. Its purpose is **communication assistance only**: reaching the right person on the right channel, and writing and reading messages well. It is never used to screen, rank, evaluate or persuade people.

## The test for every line

**Would this line survive being handed to the person it is about?** People can generally ask to see notes and opinions recorded about them. Write observable behaviour ("replies in one or two lines; answers only the first question"), never judgements ("difficult").

## Every preference, view and rule carries its source

End the bullet with a source tag: `[source: https://…]` (a permalink), `[source: log/2026-09.md#e03]` (the observation it came from), `[source: self: "their own words"]`, `[source: operator]`, or `[source: none located]` when you looked and found nothing. **A date alone is not a source.** `acquaint lint` fails on violations.

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

## Legitimate interest

<!-- The operator's one-page note: the professional interest served, why these notes are needed for it, and why keeping them does not override the people's own interests. Write it before the store holds people other than yourself. -->

## Forgetting

`acquaint forget <id> --confirm` removes the folder and writes a hashed tombstone, so the person is not silently re-created. Deleting a folder does not remove it from git history; the command prints the history-rewrite steps.

## What syncing does not protect

A private GitHub repository is access control, not encryption: the host can read everything. A pre-push hook is skipped by `git push --no-verify`. File names and commit messages contain people's names. `git-remote-gcrypt` encrypts contents, names and history, and is the upgrade when this matters.
