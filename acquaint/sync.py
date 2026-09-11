"""Private-repository sync for the data root: create the repository private, refuse anything else, guard every push.

``init`` creates the GitHub repository through ``gh`` as **private**, refuses to
continue unless ``gh repo view --json visibility`` reports ``PRIVATE``, makes the data
root its checkout, and installs a ``pre-push`` hook. The hook, and ``push`` and ``pull``
in Python, re-check that:

- the push goes through ``origin``, which has exactly one URL, the one recorded at init;
- no ``pushurl`` differs from it, and no ``url.*.pushInsteadOf`` rewrites it;
- that URL is one of the forms that name the recorded repository on github.com
  (:func:`github_urls`, the same list the hook spells out);
- ``gh`` reports the repository, on github.com whatever ``GH_HOST`` says, as private.

The hook is installed in the repository's shared hooks folder, executable, and
``core.hooksPath`` points at it by absolute path, so linked worktrees are guarded too and
a global ``core.hooksPath`` cannot silently disable it. ``init`` takes over only an empty
folder, or a clone of that same repository; it refuses any other existing repository.

What this does **not** protect, stated plainly:

- a private repository is access control, not encryption: the host can read it all;
- ``git push --no-verify`` skips the hook;
- whoever can change this repository's git config, or which ``gh`` runs on ``PATH``,
  controls what the guard sees;
- moving the data root breaks the absolute hook path until ``sync init
  --existing-only`` runs again (``sync push`` refuses in that state; a raw ``git push``
  does not);
- file names and commit messages carry people's names;
- deleting a folder does not remove it from history, other clones, or backups.

``git-remote-gcrypt``, which would encrypt contents, names and history, is not supported
yet: the guard does not recognise its internal push, so ``init`` refuses ``gcrypt::`` URLs.

Every ``git`` and ``gh`` call goes through ``run``, so tests can script ``gh`` while
``git`` runs for real.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acquaint.resources import data_text
from acquaint.store import AcquaintError

__all__ = ["BRANCH", "GITHUB_HOST", "github_urls", "init", "pull", "push", "run_command", "status", "visibility"]

BRANCH = "main"
GITHUB_HOST = "github.com"
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$")
_GITIGNORE = "# generated, never synced\n_index/\n.DS_Store\n"
_GITATTRIBUTES = "# one line-ending convention on every machine, so records parse the same everywhere\n* text=auto eol=lf\n"

Runner = Callable[..., Any]


def github_urls(repo: str) -> list[str]:
    """Every remote URL accepted for a GitHub repository. The pre-push hook spells out the same six forms.

    >>> github_urls("example/profiles")
    ['git@github.com:example/profiles.git', 'git@github.com:example/profiles', 'ssh://git@github.com/example/profiles.git', 'ssh://git@github.com/example/profiles', 'https://github.com/example/profiles.git', 'https://github.com/example/profiles']
    """
    return [
        f"git@github.com:{repo}.git",
        f"git@github.com:{repo}",
        f"ssh://git@github.com/{repo}.git",
        f"ssh://git@github.com/{repo}",
        f"https://github.com/{repo}.git",
        f"https://github.com/{repo}",
    ]


def _same_repo(url: str, repo: str) -> bool:
    return url.strip().lower() in {form.lower() for form in github_urls(repo)}


def run_command(args: Sequence[str], *, cwd: str | os.PathLike | None = None) -> subprocess.CompletedProcess:
    """Run ``git`` or ``gh`` (``gh`` pinned to github.com), capturing text output."""
    args = list(args)
    env = {**os.environ, "GH_HOST": GITHUB_HOST} if args and args[0] == "gh" else None
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)
    except FileNotFoundError as error:
        raise AcquaintError(f"{args[0]} is not installed or not on PATH ({error})") from error


def _ok(run: Runner, args: Sequence[str], *, cwd=None, what: str) -> str:
    result = run(args, cwd=cwd)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise AcquaintError(f"{what} failed: {' '.join(args)}: {detail[-1] if detail else 'no output'}")
    return (result.stdout or "").strip()


def _lines(root: Path, run: Runner, *args: str) -> list[str]:
    """Non-empty output lines of a git command; a missing config value is simply no lines."""
    return [line for line in (run(["git", *args], cwd=root).stdout or "").splitlines() if line.strip()]


def visibility(repo: str, *, run: Runner = run_command) -> str:
    """``PRIVATE``, ``PUBLIC`` or ``INTERNAL``, as ``gh`` reports it now for the repository on github.com."""
    return _ok(run, ["gh", "repo", "view", repo, "--json", "visibility", "-q", ".visibility"], what="reading visibility").upper()


def _require_private(repo: str, run: Runner) -> str:
    seen = visibility(repo, run=run)
    if seen != "PRIVATE":
        raise AcquaintError(f"{repo} is {seen or 'of unknown visibility'}, not PRIVATE: refusing to put profile data in it")
    return seen


def _configured(root: Path, run: Runner) -> tuple[str, str]:
    if not (root / ".git").exists():
        raise AcquaintError(f"{root} is not a synced store yet: run `acquaint sync init --repo <owner>/<name>` first")
    repo = next(iter(_lines(root, run, "config", "--get", "acquaint.repo")), "")
    remote = next(iter(_lines(root, run, "config", "--get", "acquaint.remote")), "")
    if not repo or not remote:
        raise AcquaintError(f"{root} is a git repository but was not set up by `acquaint sync init`")
    if not _same_repo(remote, repo):
        raise AcquaintError(f"the recorded remote {remote!r} is not a url of the GitHub repository {repo}; refusing")
    urls = _lines(root, run, "config", "--get-all", "remote.origin.url")
    if urls != [remote]:
        raise AcquaintError(f"origin must have exactly one url, {remote!r}, but has {urls}; refusing")
    pushurls = _lines(root, run, "config", "--get-all", "remote.origin.pushurl")
    if pushurls not in ([], [remote]):
        raise AcquaintError(f"origin has a pushurl {pushurls} that differs from {remote!r}; refusing")
    fetching = _lines(root, run, "remote", "get-url", "--all", "origin")
    pushing = _lines(root, run, "remote", "get-url", "--push", "--all", "origin")
    if pushing != fetching:
        raise AcquaintError(f"git would push origin to {pushing} but fetch from {fetching} (a url.*.pushInsteadOf rewrite?); refusing")
    return repo, remote


def _hook_path(root: Path, run: Runner) -> Path:
    effective = Path(_ok(run, ["git", "rev-parse", "--git-path", "hooks/pre-push"], cwd=root, what="locating the hook"))
    return effective if effective.is_absolute() else root / effective


def _hook_active(root: Path, run: Runner) -> bool:
    """Whether git will run the shipped guard here: the effective hook path holds it, unchanged and executable."""
    hook = _hook_path(root, run)
    if not hook.is_file() or hook.read_text(encoding="utf-8") != data_text("hooks/pre-push"):
        return False
    return sys.platform == "win32" or os.access(hook, os.X_OK)


def _install_hook(root: Path, run: Runner) -> Path:
    common = Path(_ok(run, ["git", "rev-parse", "--git-common-dir"], cwd=root, what="locating the repository"))
    hooks = (common if common.is_absolute() else root / common).resolve() / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-push"
    hook.write_text(data_text("hooks/pre-push"), encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    # Absolute on purpose: a relative core.hooksPath is not found from a linked worktree.
    _ok(run, ["git", "config", "core.hooksPath", hooks.as_posix()], cwd=root, what="pointing git at the pre-push guard")
    return hook


def _check_existing_checkout(root: Path, repo: str, run: Runner) -> None:
    """Refuse to take over a repository that is neither this store nor a clone of ``repo``."""
    if not (root / ".git").exists():
        return
    recorded = next(iter(_lines(root, run, "config", "--get", "acquaint.repo")), "")
    if recorded:
        if recorded.lower() != repo.lower():
            raise AcquaintError(f"{root} already syncs to {recorded}; refusing to point it at {repo}")
        return
    origins = _lines(root, run, "config", "--get-all", "remote.origin.url")
    if not (len(origins) == 1 and _same_repo(origins[0], repo)):
        found = f"origin {', '.join(origins)}" if origins else "no origin"
        raise AcquaintError(
            f"{root} is already a git repository ({found}); acquaint takes over only an empty folder or a clone of {repo}"
        )


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
    if remote_url is not None:
        if remote_url.strip().lower().startswith("gcrypt::"):
            raise AcquaintError(
                "gcrypt remotes are not supported yet: the pre-push guard does not recognise git-remote-gcrypt's own push"
            )
        if not _same_repo(remote_url, repo):
            raise AcquaintError(
                f"--remote-url {remote_url!r} is not a url of the GitHub repository {repo} (one of: {', '.join(github_urls(repo))}); "
                "the visibility check must cover the repository that receives the data"
            )
    root = Path(root)
    _check_existing_checkout(root, repo, run)
    plan = [
        f"gh repo view {repo} (create it with `gh repo create {repo} --private` if missing)" if create else f"gh repo view {repo}",
        f"refuse unless gh reports {repo} on github.com as PRIVATE",
        f"git init {root} (branch {BRANCH}), or adopt an existing clone of {repo}; origin = {remote_url or 'the repository SSH URL from gh'}",
        "record acquaint.repo and acquaint.remote in the repository's git config",
        "install the pre-push guard (absolute core.hooksPath); commit and push the current store",
    ]
    if dry_run:
        return {"repo": repo, "root": str(root), "dry_run": True, "plan": plan}

    exists = run(["gh", "repo", "view", repo, "--json", "visibility"]).returncode == 0
    if not exists:
        if not create:
            raise AcquaintError(f"{repo} does not exist (drop --existing-only to create it, private)")
        _ok(run, ["gh", "repo", "create", repo, "--private", "--description", "acquaint profile store (private)"], what="creating the repository")
    seen = _require_private(repo, run)
    url = remote_url or _ok(run, ["gh", "repo", "view", repo, "--json", "sshUrl", "-q", ".sshUrl"], what="reading the SSH URL")
    if not _same_repo(url, repo):
        raise AcquaintError(f"gh reported {url!r} as the URL of {repo}; refusing")

    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        _ok(run, ["git", "init", "-q"], cwd=root, what="git init")
        _ok(run, ["git", "symbolic-ref", "HEAD", f"refs/heads/{BRANCH}"], cwd=root, what="setting the branch")
    if _lines(root, run, "config", "--get-all", "remote.origin.url"):
        run(["git", "config", "--unset-all", "remote.origin.url"], cwd=root)
        _ok(run, ["git", "config", "remote.origin.url", url], cwd=root, what="setting origin")
    else:
        _ok(run, ["git", "remote", "add", "origin", url], cwd=root, what="adding origin")
    run(["git", "config", "--unset-all", "remote.origin.pushurl"], cwd=root)
    _ok(run, ["git", "config", "acquaint.repo", repo], cwd=root, what="recording the repository")
    _ok(run, ["git", "config", "acquaint.remote", url], cwd=root, what="recording the remote")
    for name, text in ((".gitignore", _GITIGNORE), (".gitattributes", _GITATTRIBUTES)):
        if not (root / name).exists():
            (root / name).write_text(text, encoding="utf-8", newline="\n")
    hook = _install_hook(root, run)
    try:
        pushed = push(root, message="acquaint: initialise store", run=run)
    except AcquaintError as error:
        raise AcquaintError(f"the store is set up for {repo}, but the first push failed: {error}. Fix that, then run `acquaint sync push`") from error
    return {"repo": repo, "root": str(root), "remote": url, "visibility": seen, "hook": str(hook), **{k: pushed[k] for k in ("committed", "pushed")}}


def push(root: str | os.PathLike, *, message: str | None = None, dry_run: bool = False, run: Runner = run_command) -> dict[str, Any]:
    """Commit everything, rebase onto the remote, and push, after re-checking the remote, the guard and the visibility."""
    root = Path(root)
    repo, remote = _configured(root, run)
    changed = [line for line in _ok(run, ["git", "status", "--porcelain"], cwd=root, what="git status").splitlines() if line]
    if dry_run:
        return {"repo": repo, "dry_run": True, "would_commit": len(changed)}
    if not _hook_active(root, run):
        raise AcquaintError(
            f"the pre-push guard is not active in {root} (moved data root, a changed core.hooksPath, or a hook that is not executable); "
            f"run `acquaint sync init --repo {repo} --existing-only` first"
        )
    _require_private(repo, run)
    committed = False
    if changed:
        _ok(run, ["git", "add", "-A"], cwd=root, what="git add")
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        _ok(run, ["git", "commit", "-q", "-m", message or f"acquaint: sync {stamp} ({len(changed)} files)"], cwd=root, what="git commit")
        committed = True
    if run(["git", "rev-parse", "--verify", "HEAD"], cwd=root).returncode != 0:
        return {"repo": repo, "committed": False, "pushed": False, "note": "nothing to push yet"}
    if run(["git", "fetch", "-q", "origin", BRANCH], cwd=root).returncode == 0:
        _ok(run, ["git", "rebase", "-q", f"origin/{BRANCH}"], cwd=root, what="rebasing onto the remote")
    _ok(run, ["git", "push", "-q", "-u", "origin", f"HEAD:{BRANCH}"], cwd=root, what="git push (the pre-push guard may have refused)")
    return {"repo": repo, "remote": remote, "committed": committed, "changed_files": len(changed), "pushed": True}


def pull(root: str | os.PathLike, *, dry_run: bool = False, run: Runner = run_command) -> dict[str, Any]:
    """Re-check the remote and its visibility, then rebase local work onto it (uncommitted edits are stashed and restored)."""
    root = Path(root)
    repo, remote = _configured(root, run)
    if dry_run:
        return {"repo": repo, "dry_run": True, "plan": [f"git pull --rebase --autostash origin {BRANCH}"]}
    _require_private(repo, run)
    _ok(run, ["git", "pull", "-q", "--rebase", "--autostash", "origin", BRANCH], cwd=root, what="git pull")
    head = _ok(run, ["git", "rev-parse", "--short", "HEAD"], cwd=root, what="git rev-parse")
    return {"repo": repo, "remote": remote, "pulled": True, "head": head}


def status(root: str | os.PathLike, *, check_visibility: bool = True, run: Runner = run_command) -> dict[str, Any]:
    """Whether the store is synced, where to, uncommitted changes, ahead/behind, the guard, and live visibility."""
    root = Path(root)
    if not (root / ".git").exists():
        return {"synced": False, "root": str(root), "note": "not set up: acquaint sync init --repo <owner>/<name>"}
    repo, remote = _configured(root, run)
    dirty = [line for line in _ok(run, ["git", "status", "--porcelain"], cwd=root, what="git status").splitlines() if line]
    result: dict[str, Any] = {
        "synced": True,
        "root": str(root),
        "repo": repo,
        "remote": remote,
        "uncommitted": len(dirty),
        "hook_installed": _hook_active(root, run),
    }
    if check_visibility:
        result["visibility"] = visibility(repo, run=run)
        if run(["git", "fetch", "-q", "origin", BRANCH], cwd=root).returncode == 0:
            counts = _ok(run, ["git", "rev-list", "--left-right", "--count", f"HEAD...origin/{BRANCH}"], cwd=root, what="comparing with the remote")
            ahead, behind = (int(n) for n in counts.split())
            result.update(ahead=ahead, behind=behind)
    return result
