---
name: acquaint-profile
description: Build, research, update or consolidate a profile in acquaint — gather a person's own writing, extract observable communication habits with evidence, and write sourced lines into their entry file, writing card and views. Use when asked to "make a profile of X", "research how X writes", "update X's profile", "what do we know about how X communicates", "consolidate X's observations", "turn these notes into a profile", or before a high-stakes message to someone whose record is thin. Runs parallel profile-reader agents on one extraction brief. Records behaviour with sources, never personality labels or sensitive categories.
metadata:
  audience: users
---

# acquaint-profile — evidence in, sourced profile out

A profile is the operator's view of a person, written so that it would survive being handed to that person. It is built from **evidence** (their own writing, what they told the operator, what happened) and every line points back to it.

## Invariants

1. **Behaviour, not typology.** Record what they do, with counts: "replies in one or two lines (14 of 16 emails)". Never "introverted", never a DISC or Big Five label, never mood.
2. **Every preference, view and rule has a source.** A permalink, a log anchor, their own words (`self: "…"`), `operator`, or `none located`. A date is not a source. An inference is marked as one and lives under *Hypotheses*.
3. **Their words beat inference, and newer beats older.** When evidence conflicts, keep both: mark the old line superseded, don't delete it. "Preferred calls until 2026-02" is itself useful.
4. **Scope your negative results.** "Found no statement about AI" means "in these sources, over these dates". Write the scope into `sources.md`; a null result from the wrong place is how false preferences get recorded.
5. **Never record** what the store's `POLICY.md` forbids, including by inference.

## Step 0 — set up

```bash
acquaint who "<name>"                    # does a record exist? under which id?
acquaint new person "<Given Family>"     # if not; add --qualifier on a name collision
```

Read the store's `POLICY.md` once per session.

## Step 1 — the corpus

Collect writing **verifiably by them**: bylined articles, posts from their own accounts, messages they sent the operator, their comments on issues and pull requests. Exclude anything ghostwritten, quoted by others, or of unclear authorship. Record in `sources.md`, one bullet per source: where it lives, how authorship was verified, the date range, the number of items, and when it was mined.

Rough minimums before a habit is worth recording (heuristics, not thresholds from a paper): ~20 messages per channel for length and layout; 10–20 for greetings and sign-offs; ~10 requests before describing how they ask; one explicit statement for a stated preference.

## Step 2 — extraction, in parallel

Split the corpus into batches of similar size. Spawn one **profile-reader** agent per batch, in parallel, each given the batch (paths or links, not pasted text) and the extraction brief below, unchanged. One brief for all readers is what makes their outputs comparable.

### Extraction brief

For each item, report evidence rows. Each row: `dimension | observation | quote (≤ 25 words) | anchor or permalink | date`.

Dimensions to extract:

1. **Length and layout** — words per message, paragraphs, lists, headings, by channel.
2. **Openers and closers** — greetings, sign-offs, use of names, thanks.
3. **Register** — formality, contractions, how technical.
4. **Directness and asks** — where the ask sits (first line, last line), one ask or many, hedged or imperative.
5. **Punctuation and formatting** — em dashes, exclamation marks, emoji, capitalisation.
6. **Vocabulary** — terms they use unprompted; **their coinages and signature phrases** (candidates for the writing card's blocklist: things never to echo back at them).
7. **Stated preferences** — anything they say about length, format, channel, timing, tone, or AI-written text. Quote it exactly.
8. **Positions and standing objections** — work-relevant views they have stated, and the objections they raise again and again.
9. **What they assume vs. explain** — expertise signals: terms used correctly without explanation, terms they asked about.
10. **How to read them** — phrases whose intensity differs from their surface ("interesting" meaning no; mild wording carrying strong criticism), with the evidence that shows it.

Do **not** extract: personality traits, mood, health, religion, politics, ethnicity, sexuality, family details, or anything about third parties. Do not summarise the person; return rows. Mark any row you inferred rather than read as `inferred`.

## Step 3 — synthesis

- Pool the rows. A **style or reading note needs two or more independent observations**; a single one stays in the log or under *Hypotheses*.
- A **stated preference needs one explicit statement**, quoted; the newest statement wins.
- Contradictions: keep both lines, mark the older `superseded (until YYYY-MM)`.
- Positions and objections go to `views.md`, each with its quote and anchor.

## Step 4 — where each thing goes

| What | File, section |
|---|---|
| Who they are to the operator | `PROFILE.md` · Who |
| Channel defaults in prose | `PROFILE.md` · Reach (the evaluated rules go in `rules.yaml`, only when the person or the operator stated them) |
| How to write to them | `PROFILE.md` · Write to them (the few that matter most) and `style.md` (the full card) |
| How to interpret them | `PROFILE.md` · Read them |
| What to avoid | `PROFILE.md` · Don't |
| Positions, premises, standing objections | `views.md` |
| Handles and addresses | `identities.yaml`, with evidence |
| Where their writing lives, how verified | `sources.md` |

Keep `PROFILE.md` under 120 lines; link the rest from *More*. Every bullet ends with its source tag.

### Writing card format (`style.md`)

```markdown
---
ai_tolerance: unknown     # tolerant | neutral | averse; averse only on explicit evidence
disclosure: ""            # the operator's decision, for averse readers
---
## Register
- Plain, first person, no exclamation marks. (n=18) [source: sources.md#corpus-2026]
## Do
- Open with the decision, then the options. [source: self: "give me the recommendation first"]
## Don't
- No headers or bold in email. (never used, 0 of 30) [source: sources.md#corpus-2026]
## Blocklist
- "their coined phrase" [source: https://example.org/their-post]
## Exemplars
- The operator's own past message to them that worked, linked, with why. [source: log/2026-08.md#e02]
## Hypotheses (never act on these alone)
- Possibly prefers calls for disagreements. (inferred, n=2) [source: log/2026-07.md#e01]
```

Exemplars are the **operator's** messages to this person, never theirs: the voice stays the operator's.

### Identity evidence

| Level | Evidence |
|---|---|
| E1 | They told the operator, or wrote from it in a thread with known identifiers |
| E2 | A two-way self-published link (their site links the profile and back) |
| E3 | The same unique identifier in two sources |
| E4 | Name + organisation + location match — never merge on this alone |
| E5 | Name only — a candidate, nothing more |

Never merge two records on one shared attribute. When two records turn out to be different people, say so in both (`not_same_as`).

## Step 5 — verify and hand over

```bash
acquaint lint <id>          # must pass: no unsourced lines, nothing forbidden, under budget
acquaint brief <id>         # read it as the next agent will
```

Then spot-check three lines against their sources by opening the source, not by trusting the row. Show the operator the diff whenever it adds or changes a rule, merges identities, or removes anything.

## Consolidating observations

Agents append observations with `acquaint remember` during ordinary work. To turn them into profile lines: read the log entries since the last consolidation, and for each decide **add**, **update**, **supersede** or **leave**. Never delete an observation. Promote only what meets the Step 3 rules. Afterwards run `acquaint lint <id>`, and note in `PROFILE.md` frontmatter (`consolidated_through: log/2026-09.md#e07`) how far you got.
