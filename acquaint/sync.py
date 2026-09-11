"""Private-repository sync for the data root: create the repository private, refuse anything else, guard every push.

``init`` creates the GitHub repository through ``gh`` as **private**, refuses to
continue unless ``gh repo view --json visibility`` reports ``PRIVATE``, makes the data
root its checkout, and installs a ``pre-push`` hook that re-checks the remote URL and
the visibility on every push. ``push`` and ``pull`` re-check too. The repository's own
``core.hooksPath`` is pointed at that hook, because a global ``core.hooksPath`` would
otherwise make git skip it without a word.

What this does **not** protect, stated plainly:

- a private repository is access control, not encryption: the host can read it all;
- ``git push --no-verify`` skips the hook;
- file names and commit messages carry people's names;
- deleting a folder does not remove it from history, other clones, or backups.

``git-remote-gcrypt`` encrypts contents, names and history. Pass its URL
(``gcrypt::git@github.com:owner/name.git``) as ``remote_url`` to use it.

Every ``git`` and ``gh`` call goes through ``run``, so tests can script ``gh``
while ``git`` runs for real against a local bare repository.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acquaint.resources import data_text
from acquaint.store import AcquaintError

__all__ = ["init", "push", "pull", "status", "visibility", "run_command", "GH_ENVVAR"]

GH_ENVVAR = "ACQUAINT_GH"
BRANCH = "main"
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$")
_GITIGNORE = "# generated, never synced\n_index/\n.DS_Store\n"

Runner = Callable[..., Any]


def run_command(args: Sequence[str], *, cwd: str | os.PathLike | None = None) -> subprocess.CompletedProcess:
    """Run ``git`` or ``gh`` (``$ACQUAINT_GH`` overrides the ``gh`` executable), capturing text output."""
    args = list(args)
    if args and args[0] == "gh":
        args[0] = os.environ.get(GH_ENVVAR, "gh")
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise AcquaintError(f"{args[0]} is not installed or not on PATH ({error})") from error


def _ok(run: Runner, args: Sequence[str], *, cwd=None, what: str) -> str:
    result = run(args, cwd=cwd)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise AcquaintError(f"{what} failed: {' '.join(args)}: {detail[-1] if detail else 'no output'}")
    return (result.stdout or "").strip()


def visibility(repo: str, *, run: Runner = run_command) -> str:
    """``PRIVATE``, ``PUBLIC`` or ``INTERNAL``, as ``gh`` reports it now."""
    return _ok(run, ["gh", "repo", "view", repo, "--json", "visibility", "-q", ".visibility"], what="reading visibility").upper()


def _require_private(repo: str, run: Runner) -> str:
    seen = visibility(repo, run=run)
    if seen != "PRIVATE":
        raise AcquaintError(f"{repo} is {seen or 'of unknown visibility'}, not PRIVATE: refusing to put profile data in it")
    return seen


def _git_config(root: Path, key: str, run: Runner) -> str:
    return (run(["git", "config", "--get", key], cwd=root).stdout or "").strip()


def _configured(root: Path, run: Runner) -> tuple[str, str]:
    if not (root / ".git").exists():
        raise AcquaintError(f"{root} is not a synced store yet: run `acquaint sync init --repo <owner>/<name>` first")
    repo, remote = _git_config(root, "acquaint.repo", run), _git_config(root, "acquaint.remote", run)
    if not repo or not remote:
        raise AcquaintError(f"{root} is a git repository but was not set up by `acquaint sync init`")
    actual = _git_config(root, "remote.origin.url", run)
    if actual != remote:
        raise AcquaintError(f"origin is {actual!r} but this store syncs only to {remote!r}; refusing")
    return repo, remote


def _install_hook(root: Path) -> Path:
    hook = root / ".git" / "hooks" / "pre-push"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(data_text("hooks/pre-push"), encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    return hook


def init(
    root: str | os.PathLike,
    repo: str,
    *,
    remote_url: str | None = None,
    create: bool = True,
    dry_run: bool = False,
    run: Runner = run_command,
) -> dict[str, Any]:
    """Make ``root`` a checkout of the private GitHub repository ``repo``, creating it (private) if needed."""
    if not _REPO_RE.match(repo):
        raise AcquaintError(f"repo is written owner/name, got {repo!r}")
    root = Path(root)
    plan = [
        f"gh repo view {repo} (create it with `gh repo create {repo} --private` if missing)" if create else f"gh repo view {repo}",
        f"refuse unless gh reports {repo} as PRIVATE",
        f"git init {root} (branch {BRANCH}); origin = {remote_url or 'the repository SSH URL from gh'}",
        "record acquaint.repo and acquaint.remote in the repository's git config",
        "install the pre-push visibility guard; commit and push the current store",
    ]
    if dry_run:
        return {"repo": repo, "root": str(root), "dry_run": True, "plan": plan}

    exists = run(["gh", "repo", "view", repo, "--json", "visibility"]).returncode == 0
    if not exists:
        if not create:
            raise AcquaintError(f"{repo} does not exist (pass create to make it, private)")
        _ok(run, ["gh", "repo", "create", repo, "--private", "--description", "acquaint profile store (private)"], what="creating the repository")
    seen = _require_private(repo, run)
    url = remote_url or _ok(run, ["gh", "repo", "view", repo, "--json", "sshUrl", "-q", ".sshUrl"], what="reading the SSH URL")

    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        _ok(run, ["git", "init", "-q"], cwd=root, what="git init")
        _ok(run, ["git", "symbolic-ref", "HEAD", f"refs/heads/{BRANCH}"], cwd=root, what="setting the branch")
    if _git_config(root, "remote.origin.url", run):
        _ok(run, ["git", "remote", "set-url", "origin", url], cwd=root, what="setting origin")
    else:
        _ok(run, ["git", "remote", "add", "origin", url], cwd=root, what="adding origin")
    _ok(run, ["git", "config", "acquaint.repo", repo], cwd=root, what="recording the repository")
    _ok(run, ["git", "config", "acquaint.remote", url], cwd=root, what="recording the remote")
    if not (root / ".gitignore").exists():
        (root / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")
    hook = _install_hook(root)
    _ok(run, ["git", "config", "core.hooksPath", ".git/hooks"], cwd=root, what="pointing git at the pre-push guard")
    pushed = push(root, message="acquaint: initialise store", run=run)
    return {"repo": repo, "root": str(root), "remote": url, "visibility": seen, "hook": str(hook), **{k: pushed[k] for k in ("committed", "pushed")}}


def push(root: str | os.PathLike, *, message: str | None = None, dry_run: bool = False, run: Runner = run_command) -> dict[str, Any]:
    """Commit everything, rebase onto the remote, and push, after re-checking the remote and its visibility."""
    root = Path(root)
    repo, remote = _configured(root, run)
    changed = [line for line in _ok(run, ["git", "status", "--porcelain"], cwd=root, what="git status").splitlines() if line]
    if dry_run:
        return {"repo": repo, "dry_run": True, "would_commit": len(changed)}
    _require_private(repo, run)
    committed = False
    if changed:
        _ok(run, ["git", "add", "-A"], cwd=root, what="git add")
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        _ok(run, ["git", "commit", "-q", "-m", message or f"acquaint: sync {stamp} ({len(changed)} files)"], cwd=root, what="git commit")
        committed = True
    has_commits = run(["git", "rev-parse", "--verify", "HEAD"], cwd=root).returncode == 0
    if not has_commits:
        return {"repo": repo, "committed": False, "pushed": False, "note": "nothing to push yet"}
    if run(["git", "fetch", "-q", "origin", BRANCH], cwd=root).returncode == 0:
        _ok(run, ["git", "rebase", "-q", f"origin/{BRANCH}"], cwd=root, what="rebasing onto the remote")
    _ok(run, ["git", "push", "-q", "-u", "origin", f"HEAD:{BRANCH}"], cwd=root, what="git push (the pre-push guard may have refused)")
    return {"repo": repo, "remote": remote, "committed": committed, "changed_files": len(changed), "pushed": True}


def pull(root: str | os.PathLike, *, dry_run: bool = False, run: Runner = run_command) -> dict[str, Any]:
    """Fetch and rebase local work onto the remote (local uncommitted edits are stashed and restored)."""
    root = Path(root)
    repo, remote = _configured(root, run)
    if dry_run:
        return {"repo": repo, "dry_run": True, "plan": [f"git pull --rebase --autostash origin {BRANCH}"]}
    _ok(run, ["git", "pull", "-q", "--rebase", "--autostash", "origin", BRANCH], cwd=root, what="git pull")
    head = _ok(run, ["git", "rev-parse", "--short", "HEAD"], cwd=root, what="git rev-parse")
    return {"repo": repo, "remote": remote, "pulled": True, "head": head}


def status(root: str | os.PathLike, *, check_visibility: bool = True, run: Runner = run_command) -> dict[str, Any]:
    """Whether the store is synced, where to, uncommitted changes, ahead/behind, the hook, and live visibility."""
    root = Path(root)
    if not (root / ".git").exists():
        return {"synced": False, "root": str(root), "note": "not set up: acquaint sync init --repo <owner>/<name>"}
    repo, remote = _configured(root, run)
    dirty = [line for line in _ok(run, ["git", "status", "--porcelain"], cwd=root, what="git status").splitlines() if line]
    effective = Path(_ok(run, ["git", "rev-parse", "--git-path", "hooks/pre-push"], cwd=root, what="locating the hook"))
    hook = effective if effective.is_absolute() else root / effective
    result: dict[str, Any] = {
        "synced": True,
        "root": str(root),
        "repo": repo,
        "remote": remote,
        "uncommitted": len(dirty),
        "hook_installed": hook.is_file() and hook.read_text(encoding="utf-8") == data_text("hooks/pre-push"),
    }
    if check_visibility:
        result["visibility"] = visibility(repo, run=run)
        if run(["git", "fetch", "-q", "origin", BRANCH], cwd=root).returncode == 0:
            counts = _ok(run, ["git", "rev-list", "--left-right", "--count", f"HEAD...origin/{BRANCH}"], cwd=root, what="comparing with the remote")
            ahead, behind = (int(n) for n in counts.split())
            result.update(ahead=ahead, behind=behind)
    return result
