---
name: acquaint-sync
description: Set up, use and check private sync of the acquaint profile store through a private GitHub repository. Use when asked to "sync my profiles", "back up my acquaint store", "set up profiles on the server", "use my profiles on another machine", "is my profile store private", "push/pull profiles", or when acquaint sync status reports a problem. Covers what the visibility guard does and, plainly, what it does not protect, plus the git-remote-gcrypt upgrade.
metadata:
  audience: users
---

# acquaint-sync — one private repository, guarded

## What `sync init` does

```bash
acquaint sync init --repo <owner>/<name> --dry-run    # print the plan, run nothing
acquaint sync init --repo <owner>/<name>
```

1. Creates the repository through `gh` as **private** if it does not exist (`--existing-only` refuses to create).
2. **Refuses to continue** unless `gh repo view --json visibility` reports `PRIVATE`.
3. Makes the data root a git checkout with that repository as `origin`, and records the repository and URL in its git config.
4. Installs a **pre-push hook** that allows a push only through `origin`, only to the URL recorded at init (no `pushurl` override), only when that URL names the checked repository, and only while `gh` still reports it `PRIVATE`; it fails closed otherwise. The repository's `core.hooksPath` points at the hook by absolute path, so linked worktrees are guarded and a global `core.hooksPath` cannot silently skip it. Only GitHub remotes are accepted, so the repository whose visibility is checked is always the one that receives the data.
5. Commits and pushes the store.

## Daily use

```bash
acquaint sync status     # synced? uncommitted changes, ahead/behind, hook intact, live visibility
acquaint sync push       # commit everything, rebase onto the remote, push (re-checks visibility)
acquaint sync pull       # rebase local work onto the remote
```

`status` exits 1 if visibility is not `PRIVATE` or the hook is missing or changed. Treat either as an incident: stop pushing, tell the operator.

## A second machine (for example a server)

```bash
gh auth login
gh repo clone <owner>/<name> ~/.local/share/acquaint          # or any path…
export ACQUAINT_DATA_DIR=~/.local/share/acquaint              # …named here or in ~/.config/acquaint/config.toml
acquaint sync init --repo <owner>/<name> --existing-only      # re-installs the guard in this clone
acquaint sync status
```

A fresh clone has **no hook** until `sync init` runs in it: hooks are not part of a repository. The same goes for a data root you have moved: the hook path is absolute, so run `sync init --existing-only` again (`sync push` refuses until you do).

## What this does not protect — say it plainly when asked

- **A private repository is access control, not encryption.** The host, and anyone with access to the account, can read every file.
- **`git push --no-verify` skips the hook.** It is a seatbelt, not a lock.
- **Whoever controls this repository's git config, global URL rewriting, or the `gh` on `PATH` controls what the guard sees.**
- **File names and commit messages contain people's names** (`people/<given-family>/`).
- **Deleting a folder does not delete it from history**, from other clones, or from backups. `acquaint forget` prints the history-rewrite steps; forks and copies elsewhere are beyond its reach.
- Changing the repository to public through the GitHub website is caught at the next push or `status`, not before.

## The encryption upgrade

`git-remote-gcrypt` encrypts contents, file names and history on the remote (GPG-based; it force-pushes, so always pull first). Install it, then:

```bash
acquaint sync init --repo <owner>/<name> --remote-url "gcrypt::git@github.com:<owner>/<name>.git"
```

The visibility guard still applies to the repository.

## Never

- Change the repository's visibility, or push with `--no-verify`.
- Put the data root inside a Dropbox, iCloud or other synced folder, or inside any code repository.
- Copy profile files into another repository, issue, pull request or shared document.
