# The operator-views brief: profiling the operator's own positions

The extraction brief in `SKILL.md` reads a **recipient**: how they write, so the operator can write to them. This variant reads the **operator**, the person whose agents these are, for a different purpose: a sourced record of their positions, preferences and standing objections, so that an agent can predict which recommendations they would disagree with, and why (acquaint-write § Mode C — decision verdict). Steps 0, 1, 4 and 5 of the skill apply unchanged; this file replaces the extraction brief (Step 2) and adds rules to the synthesis (Step 3).

## The corpus

The operator's own words, in three tiers of weight:

1. **What they typed to their agents**: the prompt history, from every machine they work on. Drop the agent-written dispatch briefs and the slash commands first (for example, penlike's `history` sourcer reads Claude Code's history files and does both). Corrections and repeated complaints here are the strongest evidence there is.
2. **Notes their agents wrote about them**: agent memory files and similar records of a correction. Second tier: an agent's paraphrase, not their words.
3. **Their older writing**: essays, posts, talks. Third tier, and dated: a position from years ago may have moved.

Rules the operator wrote into agent configuration (CLAUDE.md, skills) are not evidence of a position on their own: the operator rewrites them often, and an agent may have drafted them. A line resting only on such a rule is `[weight: low]`.

**Screen before batching.** A typed-prompt history holds whatever was pasted into it, credentials included. Scan the corpus for secrets before splitting it, never quote one in an evidence row, and delete the corpus and batch files once the evidence rows exist; keep the rows.

## Extraction brief (hand this to every profile-reader, unchanged)

You are reading one batch of a person's own words: what they typed to their coding agents, notes their agents wrote down about their corrections, or essays they published. The person is the operator of these agents. The goal is a sourced record of their **positions, preferences and standing objections**, so that a later agent can predict which recommendations they would disagree with, and why.

Return **evidence rows only**, one per line, pipe-separated:

`dimension | observation | quote (<= 25 words, verbatim) | anchor | date`

The anchor is the item's id (a host label and timestamp for a typed prompt, such as `laptop:2026-03-04T10:22:01Z`; the file name for a memory note; a permalink for an essay). Never summarise the person; never paraphrase a quote; return rows.

Dimensions:

1. **design**: code and API design preferences (abstractions, defaults, argument style, error handling, naming, what counts as a hack versus a solution). Record how they specify, not only what.
2. **architecture**: package boundaries, where things live, reuse versus new code, a new package versus extending one, storage, which interfaces to build first.
3. **process**: how they want work done: research first, plan then build, landing branches, tests, reviews, when to ask and when to decide, one-off versus reusable, what they delegate and what they keep.
4. **communication**: how they want to be told things: length, links, format, what to show them, what not to bother them with, where documents go, tones they dislike (including AI-sounding text).
5. **business**: cost, spending, paid services, licences, publishing, release cadence, what is worth building, priorities.
6. **people**: how they want others (clients, collaborators, partners) handled: drafts before sending, channels, tone toward people. Nothing about the third parties themselves.
7. **privacy-legal**: private versus public data, secrets, provenance, licences, what may be committed or published.
8. **tooling**: their preferences about agents and their setup: skills, hooks, models and effort, sessions, memory, what agents should learn from.
9. **objection**: a correction or complaint, above all a repeated one ("I already said", "why did you", "as always", "again"). Record what was wrong and what they wanted instead. These rows carry the most weight.
10. **read-them**: how to read their messages: words whose intensity differs from the surface ("obviously", "I'm not sure", "perhaps", "please"), how they signal a decision versus a thought, what a short "yes" or "ok" covers.
11. **delegation**: what they want to decide themselves and what agents may decide; what needs their approval.

Rules:

- Quote exactly, at most 25 words; cut with `…` when needed. One row per distinct observation; a message may yield several rows or none.
- Mark a row you inferred rather than read as `inferred`, at the end of the observation.
- Skip pure task instructions with no preference in them ("add a test for X"), pasted logs, greetings, and anything about a third party's personal life, health, politics, religion or family. Skip opinions about named people; keep opinions about how to work with people.
- Skip any message that is itself a briefing written for an agent (it opens "You are …" or lists skills to load); it was meant to be filtered out upstream.
- Never copy a password, key, token or other secret into a row, even inside a quote.
- Record the date of every row: the synthesis decides what superseded what.
- Precision over coverage: a row must be defensible from its quote alone.

End with one line: `rows: N · messages read: M`.

## Synthesis (Step 3, with these additions)

Pool the rows, then write `views.md` lines under the skill's Step 3 rules, plus:

1. **A position line needs two or more independent observations** (different messages, ideally different dates or machines) **or one explicit statement**, quoted. A single non-explicit observation goes under *Hypotheses*.
2. **Every line carries its sources**, at least the two strongest: `[source: self: "<quote, at most 20 words>" (anchor, YYYY-MM)]`, then `(n=<supporting rows>)`.
3. **Weight tags by tier.** A line resting only on rows marked `inferred` or on agent notes is `[weight: medium]`; only on older writing, `[weight: medium, pre-YYYY]`; only on a configuration rule without the operator's own words, `[weight: low]`. Untagged lines rest on the operator's own typed words.
4. **Newer beats older; keep both.** When two observations conflict, write both lines and mark the older `superseded (until YYYY-MM)`.
5. **Write the position, then the how.** "Prefers X" is weak; "wants X done by Y; corrected agents that did Z (three times: dates)" is what a verdict needs.
6. **Standing objections get their own section**, ranked by recurrence, each with its dates and what was wanted instead. They are the most valuable lines in the record.
7. **Scope the silences.** When the evidence says nothing on a dimension you expected (say, marketing), write one line under *Not covered*, sourced to the corpus it was absent from (`[source: sources.md#<corpus>]`) or `[source: none located]`. A verdict on a silent dimension is an extrapolation, and the reader must be able to see that.
8. **Every line carries a source**, *Hypotheses* and *Not covered* included: `acquaint lint` fails an unsourced line, and a brief over a record with lint errors tells every reader not to rely on it.

The shape of `views.md` for an operator record:

```markdown
## <theme>                      (3 to 8 themes, 2 to 8 lines each)
- <position line>. (n=K) [source: self: "…" (laptop:2026-05-02T…, 2026-05)] [source: self: "…" (server:…, 2026-06)]
## Standing objections          (ranked; what went wrong → what they want; dates)
## Hypotheses (never act on these alone)
## Not covered
```

How to read them goes to `PROFILE.md` · Read them, as for any record. Keep each file within the lint budget; prefer fewer, stronger lines.
