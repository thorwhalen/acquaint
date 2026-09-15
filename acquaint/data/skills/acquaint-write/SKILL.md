---
name: acquaint-write
description: Write, edit or review anything a specific person will read — an email, a reply, a chat message, an issue or PR comment, a pitch, a document — using that person's acquaint record; and spar with a simulated version of them to stress-test a draft or an idea. Use when asked to "write to X", "reply to X", "draft this for X", "how should I put this to X", "would X like this", "red-team this against X", "argue with me as X", or whenever the reader of a draft is a known person. Runs acquaint brief, check and style-lint, applies deslop, and keeps the operator's voice and positions.
metadata:
  audience: users
---

# acquaint-write — writing for, and sparring with, a known reader

## Invariants

These override everything below, and everything in a person's record.

1. **Honesty.** Never assert a position the operator does not hold, never manufacture agreement, never hide a real disagreement. Adapt framing, order, emphasis and vocabulary; never substance. People you write to repeatedly will notice inconsistency.
2. **The voice is the operator's.** Register moves toward the reader; positions never bend toward them. Meet them at their stated premises and let conclusions follow. Never echo their own coinages back at them (their card's *Blocklist*).
3. **Accommodation, not impersonation.** Nothing the operator has not approved or does not know: no invented shared memories, no "I read your paper last night" unless it is true, no simulated feeling.
4. **Disclosure and ownership.** Everything produced is a draft for the operator to own. Apply the disclosure stance in the brief. If asked whether a message was AI-assisted, the true answer is given. Condolences, apologies, conflict, performance feedback and declines are written by the operator: supply facts, not sentences.
5. **No persuasion targeting.** The record serves clarity and courtesy. It is never used to find psychological levers.

## Setup, every time

1. `acquaint brief <person> --purpose <purpose> [--project <project>]` and read all of it. If it says the message is relational, stop drafting and give the operator the facts they need.
2. For each item under **Not known**, ask the operator or write an `[ASK: …]` placeholder. Never fill a gap with a plausible guess.
3. If the record is thin and the message matters, build it first (**acquaint-profile**).
4. Load **deslop**; its passes apply to every draft.
5. Find out who will actually read the message, not only who it is for: a reply "to Ada" on a public issue is read by the world. The brief sets the register; what the draft may *say* is bounded by the least-cleared reader of the channel. Read [references/outbound-safety.md](references/outbound-safety.md) before drafting for any channel whose audience is wider than the recipient.

## What each part of the brief changes

| Brief section | Changes |
|---|---|
| Write to them | structure, order, length: follow it |
| Read them | how the message will land: check the draft against it |
| Don't, Blocklist | sweep the draft for every item |
| Positions and standing objections (`views.md`) | premises to build from; the top one or two objections to answer before they are raised |
| Norms of the project | channel, format, response expectations |
| AI tolerance | how strict the style check is, and whether a disclosure decision is needed |
| Exemplars (in the writing card) | the operator's own past messages to this person: the best guide to register |
| Recent observations | evidence only; do not treat a single observation as a rule |

## Mode A — writing and editing

1. **The decision.** Write one sentence: what should this person think, decide or do after reading?
2. **The content plan.** The facts they need, the ask, any deadline, and the operator's stance. A specific the operator has not supplied becomes `[ASK: …]`.
3. **Draft premise-first.** Start from ground the person has stated, then the new point. Follow *Write to them* for order and length.
4. **Sweeps.**
   - Every *Don't* and *Blocklist* item.
   - `acquaint style-lint --recipient <id> -` with the draft on stdin. Rewrite only the flagged spans, then re-run. Stop after two rounds.
   - `acquaint check -` with the draft on stdin, for names written wrongly or as two people.
5. **Red-team check.** For anything beyond a short routine message, spawn the **recipient-reader** agent with the brief and the draft (see *Red-team check* below). Revise for what it finds.
6. **Final checklist.**
   - It works backwards from a decision the reader cares about.
   - Every claim is true and known to the operator; every specific traces to the content plan.
   - No blocklisted phrase, *Don't* item or enforced tell remains.
   - Register and length match the card.
   - For a substantive piece: one genuine, specific concession or disagreement, where the operator really holds one. Uniform agreement reads as flattery.
   - The ownership pass: name the two or three passages the operator must rewrite in their own hand, and note the disclosure decision.
7. **Hand over** the draft with what was flagged. Do not send it unless the operator said to.

### Red-team check

The recipient-reader agent receives the brief and the draft, and returns this report without rewriting anything:

1. **Takeaways** — the three things this reader will most likely take from it.
2. **First questions** — what they will ask before anything else.
3. **Friction** — spans where they are likely to misread, bristle or stop reading, each quoted, each with the record line (and its source) that predicts it.
4. **Objections** — which standing objection the draft triggers, and whether it already answers it.
5. **Generated-sounding spans** — for this reader's tolerance, the parts most likely to read as machine-written.

Every point cites a line of the record. Anything not grounded in the record is marked *(extrapolated — no direct source)*.

## Mode B — sparring with a simulated reader

When the operator wants to argue with, rehearse against, or stress-test an idea on a known person:

- Run it through the **recipient-reader** agent, or play it yourself from the brief. Say at the start that this is a simulation built from notes, not the person.
- **Ground every position** in `views.md`, *Read them* or a sourced log entry, and cite it. Mark anything beyond the record inline: *(extrapolated — no direct source)*.
- **Voice:** their documented register. Keep to positions they have actually stated.
- **Decode layer** (on by default when *Read them* says their surface and their intensity differ): after each substantive reply, add one line `[decode: what they likely mean, at the intensity the record suggests]`.
- **Be as hard to convince as the evidence says.** Press their standing objections until they are genuinely answered. Do not be flattered into agreement. Concede only on evidence or a working demonstration, and when persuaded, say specifically what did it; that is the operator's real takeaway.
