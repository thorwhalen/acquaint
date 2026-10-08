---
name: acquaint-meeting-todos
description: Turn the todos from a meeting into GitHub issues for a company or project the operator works on — one manual-task issue per participant in the project's private meta repository, items copied verbatim, each linked to the notes and to the issue or page it concerns. Use when given meeting notes, minutes, a transcript, a Slack thread or an email with "next steps", "action items" or "todos" and asked to "put these in issues", "file the meeting todos", "make issues from the next steps", "assign the action items", or "track what everyone said they'd do". Checks first, through acquaint, that the project is unambiguous, that every participant is registered and belongs to it, and that its declared meta repository is private; when any of these fails, it tells the user what is missing and how to fix it, and files nothing.
metadata:
  audience: users
---

# acquaint-meeting-todos — a meeting's todos, filed where the team looks

The result: in the project's **meta repository**, one open `manual-task` issue per participant, assigned to them, listing their todos from the meeting **verbatim**, each todo linked to whatever helps act on it. The meta repository is private, so issues there may name people and internal matters; other repositories may not be.

## Step 1 — the inputs

You are given documents that contain todos. Typical sources, best first:

- meeting notes with a **"Next steps"** or **"Action items"** section (Gemini or Otter notes, minutes): the list is already written; copy it;
- a meeting transcript: todos are what someone says they will do ("I'll…", "can you…"); quote the speaker, and prefer the notes when both exist;
- a Slack thread, an email or an issue comment that ends with a list of who does what.

Find where the notes will live **on GitHub** (a committed copy in the project's knowledge repository, say), because every issue links to it. If the notes are not on GitHub yet, ask where they will go before filing; never link a local path, a Drive file only you can open, or a transcript.

## Step 2 — the three preconditions

Name the project and the people the todos belong to, then:

```bash
acquaint todo-preflight <project> "<person>, <person>"
```

It checks, against the store and the live repository:

1. **The project is 100 % clear**: exactly one `project` or `org` record matches. If the documents could belong to two of the operator's projects, ask; never pick.
2. **Every participant is registered and belongs to it**: each name resolves to one person whose `links.yaml` links them to that project or org.
3. **The project declares a meta repository and it is private now**: `meta_repo: owner/name` in the record's frontmatter (any repository, in the operator's own account or another org), or `github_org: <org>`, meaning `<org>/meta`.

If `ok` is false, **file nothing.** Show the user each problem with its `fix` (a command to run, or the line to add and where), and offer to apply the fixes that are store edits. Only the operator decides a project's meta repository and who belongs to it, so ask before writing those. Creating the meta repository needs their go-ahead too, and it is always created private (`gh repo create <owner>/meta --private`). Then run the check again.

A warning that someone has no GitHub identity means their issue cannot be assigned: say so, and either add the login (when the operator gives it) or file the issue unassigned and say who it is for in its first line.

## Step 3 — the todos, per person

- Copy each item **verbatim** from the source, in the source's order, as a task list (`- [ ] …`). Do not merge, reword, or "improve" items; the person must recognise what was agreed.
- Group by owner. A shared item goes to everyone it names. Leave out people the user excluded.
- Keep the source's item titles (bold labels and the like) if it has them.

## Step 4 — links that help

For each item, ask what someone would open first to act on it, and add it after the item: the relevant issue, discussion, decision record, file or earlier thread. Link GitHub items the standard way, `[owner/repo#123](https://github.com/owner/repo/issues/123)`.

- **A significant item gets an issue** in the repository where the work happens; the meta issue links to it. Search first (`gh search issues --repo <repo> "<keywords>"`, and the repository's discussions), so you never file a duplicate; if one exists, link it.
- If someone else owns an item's area (another session, another person), link their existing issue or the discussion it came from, and do not file in their place.
- Anything longer than a line (context, caveats, several links) goes in a **comment** on the meta issue, and the item links to that comment.
- Issues outside the meta repository may be public: there, write only what that repository's own rules allow (no names beyond GitHub handles, no meeting quotes, no local paths).

## Step 5 — filing

One issue per person in the meta repository:

```bash
gh label create manual-task --repo <meta repo> --color D93F0B --description "Needs a person, not an agent" 2>/dev/null
gh issue create --repo <meta repo> --label manual-task --assignee <github login> \
  --title "Meeting todos — <person>, <meeting title>, <YYYY-MM-DD>" --body-file <file>
```

The body opens with one line naming the meeting and its date, then **the link to the notes on GitHub**, then the task list. Before creating it, search the meta repository for an open issue from the same meeting for the same person, and edit that instead of opening a second one. Assigning the issue notifies the person; that is the only message this skill sends. Anything more (a Slack note, an email) needs the operator's go-ahead.

## Step 6 — report

Tell the user: the issues filed (links), the issues filed elsewhere for significant items, the items you linked to someone else's work, and anything you could not place.
