---
name: deslop
description: Write and edit prose that carries no machine-writing tells and sounds like its author, calibrated to the reader. Use whenever drafting or editing text a person will read — emails, messages, READMEs, docs, posts, pitches, reports — and whenever the user mentions AI slop, AI tells, "sounds like AI", "make it sound human", "my voice", or asks to de-AI a draft; also whenever another skill asks for it (acquaint-write does). Runs the deterministic acquaint style-lint check at the reader's tolerance of AI-sounding text, then judgment passes for rhythm, specificity and ownership. Never fakes humanity and never invents specifics.
metadata:
  audience: users
---

# deslop — prose without the machine accent

## The goal, stated correctly

The goal is not to evade detectors. It is writing a careful reader would not clock, because it is good: specific, in its author's voice, alive in its rhythm, and owned. Two failures, both mandatory to fix:

1. **Tells present** — recognisable model patterns (the check and the catalogue below).
2. **Tell-free blandness** — no tells, and still obviously synthetic because nothing in it could only have been written by this author about this subject.

Fixing the first without the second produces laundered slop. Voice and concrete content do most of the work; removing tells is the smaller part.

## Calibrate to the reader first

How strict to be depends on the reader's tolerance of AI-sounding text, recorded as `ai_tolerance` in their acquaint writing card (`acquaint brief <id>` shows it). Unknown counts as neutral.

| | Tolerant | Neutral (default) | Averse, or high stakes |
|---|---|---|---|
| Check enforces | tier E | tiers E and W | tiers E, W and S |
| "Not X but Y" constructions | up to 2 | at most 1 | none, unless the author's own writing has them |
| Headers, bullets, bold | channel norms | only if the author used them with this reader, or for 3+ enumerable items | only if the author used them with this reader |
| Who approves | the author reviews | the author approves before sending | the author approves, and makes an explicit disclosure decision |

A reader is averse only on explicit evidence or the author's say-so. Condolences, apologies, conflict, performance feedback and declines are written by the author: supply facts, not sentences.

## Voice anchoring

The author's own writing outranks every rule here. Before drafting, read one or two samples: the author's past messages to this reader (the *Exemplars* in the reader's writing card), or samples the author provides. Match sentence-length spread, how they open, how much first person, their connectives. If a "tell" is in their samples, it is voice: keep it. With no samples, ask for one to three, or proceed and say the ownership pass will be heavier.

## Step 1 — the deterministic check

```bash
acquaint style-lint --recipient <id> -        # draft on stdin; tolerance and blocklist from their card
acquaint style-lint --tolerance averse -      # no recipient on record
```

Tiers: **E** near-certain artifacts (assistant chatter, unfilled `[ASK: …]` placeholders, disclaimers, throat-clearing, summary closers, anything on the reader's blocklist), always fixed; **W** likely patterns (overused vocabulary, empty transitions, "serves as", "not X but Y", trailing "-ing" commentary, inflation, vague attribution, flattery, em-dash density, formatting in a short message); **S** common in human writing too (lists of three, hedge stacks, exclamation marks, uniform sentence length), fixed when they cluster or the reader is averse. Findings outside the enforced tiers are still listed; read them.

## Step 2 — what a regular expression cannot see

- **Agreeing with the reader's position** because it is theirs. Positions come from the author.
- **Fabricated or vague specifics**: numbers, dates, "experts say". Every specific traces to the author or becomes `[ASK: …]`.
- **False balance**: "while X has benefits, it also has drawbacks" where the author holds a view. Concede the one true thing, specifically.
- **Argument turned into a bold-term list**, and headers on a piece short enough not to need them. Formatting follows channel and purpose: an action message may want numbered questions; an argument wants prose.
- **Over-explanation**: more words than the facts need. Uniformly perfect formality in a casual channel.
- **A closing paragraph that restates the message.** End on the last real point.

## Step 3 — rhythm

Read it aloud (simulate it). Wherever the rhythm is metronomic, break it: one sentence long enough to need its commas, then a short one. Starting with And or But is fine. Cut throat-clearing openers.

## Step 4 — specificity

For each paragraph: **what here could only this author have written?** A number they measured, a failure they had, a decision they made, a date, an opinion that costs something. If nothing, cut the paragraph or insert `[ASK: the concrete detail]`. Never invent it: a placeholder beats a plausible fabrication, always.

## Step 5 — targeted rewrite

Rewrite only the flagged spans, then run the check again. Stop after two rounds; unbounded rewriting drifts into a different kind of generic. The deslopped version is usually shorter; it may grow only when a fact the reader needs was missing.

## Step 6 — ownership handoff

Hand it over as a draft, never as finished human writing. Name the two or three places the author most needs to rewrite in their own hand (usually the opening, the opinions, any anecdote), list any remaining `[ASK: …]`, and state the disclosure stance that applies.

## Never

- Fake humanity: no inserted typos, forced slang or performed quirks. Overcorrection is its own tell.
- Pad, or sand off a strong claim. Blandness, not boldness, is the machine accent.
- Use this to mislead a reader about who wrote something or what the author knows.
