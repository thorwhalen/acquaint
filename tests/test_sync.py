"""Sync to a private repository, tested without GitHub: ``gh`` is scripted, ``git`` is real, the remote is a local bare repository.

No real repository is created. The user's global git configuration is isolated so a
global ``core.hooksPath`` or commit signing cannot change what is being tested.
"""

import os
import shutil
import subprocess
import sys

import pytest

from acquaint import sync
from acquaint.store import AcquaintError

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="the pre-push guard is a POSIX shell script calling a scripted gh")
REPO = "example/profiles"


@pytest.fixture(autouse=True)
def isolated_git(tmp_path, monkeypatch):
    empty = tmp_path / "empty-gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "acquaint tests")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "tests" + "@" + "example.org")


class FakeGh:
    """Answers ``gh repo view`` and ``gh repo create``; passes ``git`` through to the real runner."""

    def __init__(self, visibility="PRIVATE", exists=True):
        self.visibility, self.exists, self.calls = visibility, exists, []

    def __call__(self, args, *, cwd=None):
        args = list(args)
        if args[0] != "gh":
            return sync.run_command(args, cwd=cwd)
        self.calls.append(args)
        done = lambda code, out="": subprocess.CompletedProcess(args, code, out, "" if code == 0 else "not found")  # noqa: E731
        if args[1:3] == ["repo", "create"]:
            assert "--private" in args, "a profile repository is only ever created private"
            self.exists = True
            return done(0)
        if args[1:3] == ["repo", "view"]:
            if not self.exists:
                return done(1)
            return done(0, self.visibility + "\n") if "-q" in args else done(0, "{}")
        raise AssertionError(f"unexpected gh call {args}")


def _git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


@pytest.fixture
def bare(tmp_path):
    path = tmp_path / "remote.git"
    assert _git("init", "-q", "--bare", str(path)).returncode == 0
    return path


@pytest.fixture
def scripted_gh(tmp_path, monkeypatch):
    """A ``gh`` executable for the hook, whose answer the test can change."""
    answer = tmp_path / "visibility"
    answer.write_text("PRIVATE")
    script = tmp_path / "fake-gh"
    script.write_text(f'#!/bin/sh\ncat "{answer}"\n')
    script.chmod(0o755)
    monkeypatch.setenv(sync.GH_ENVVAR, str(script))
    return answer


@pytest.fixture
def store_root(tmp_path):
    root = tmp_path / "data"
    (root / "people" / "ada-lovelace").mkdir(parents=True)
    (root / "people" / "ada-lovelace" / "PROFILE.md").write_text("---\nname: Ada Lovelace\n---\n")
    return root


def test_dry_run_plans_and_touches_nothing(store_root):
    def refuse(*args, **kwargs):
        raise AssertionError("a dry run runs nothing")

    result = sync.init(store_root, REPO, dry_run=True, run=refuse)
    assert result["dry_run"] and any("PRIVATE" in step for step in result["plan"])
    assert not (store_root / ".git").exists()


def test_refuses_a_repository_that_is_not_private(store_root, bare):
    with pytest.raises(AcquaintError, match="not PRIVATE"):
        sync.init(store_root, REPO, remote_url=str(bare), run=FakeGh(visibility="PUBLIC"))
    assert not (store_root / ".git").exists(), "refused before the store became a repository"


def test_rejects_a_malformed_repo_name(store_root):
    with pytest.raises(AcquaintError, match="owner/name"):
        sync.init(store_root, "profiles", dry_run=True)


def test_status_of_a_store_that_is_not_synced(store_root):
    assert sync.status(store_root, run=FakeGh())["synced"] is False


@posix_only
def test_init_creates_private_pushes_and_guards(store_root, bare, scripted_gh):
    gh = FakeGh(exists=False)
    result = sync.init(store_root, REPO, remote_url=str(bare), run=gh)
    assert result["pushed"] and result["visibility"] == "PRIVATE"
    assert ["gh", "repo", "create", REPO, "--private", "--description", "acquaint profile store (private)"] in gh.calls
    assert "people/ada-lovelace/PROFILE.md" in _git("--git-dir", str(bare), "ls-tree", "-r", "--name-only", "main").stdout
    assert _git("config", "core.hooksPath", cwd=store_root).stdout.strip() == ".git/hooks"

    status = sync.status(store_root, run=gh)
    assert (status["hook_installed"], status["visibility"], status["ahead"], status["behind"]) == (True, "PRIVATE", 0, 0)


@posix_only
def test_push_and_pull_round_trip(tmp_path, store_root, bare, scripted_gh):
    gh = FakeGh()
    sync.init(store_root, REPO, remote_url=str(bare), run=gh)
    (store_root / "people" / "ada-lovelace" / "PROFILE.md").write_text("---\nname: Ada Lovelace\naka: [Ada]\n---\n")
    assert sync.push(store_root, run=gh)["committed"]

    other = tmp_path / "other-clone"
    assert _git("clone", "-q", "--branch", "main", str(bare), str(other)).returncode == 0
    (other / "people" / "grace-example").mkdir(parents=True)
    (other / "people" / "grace-example" / "PROFILE.md").write_text("---\nname: Grace Example\n---\n")
    _git("add", "-A", cwd=other), _git("commit", "-q", "-m", "elsewhere", cwd=other)
    assert _git("push", "-q", "origin", "main", cwd=other).returncode == 0

    assert sync.pull(store_root, run=gh)["pulled"]
    assert (store_root / "people" / "grace-example" / "PROFILE.md").is_file()


@posix_only
def test_the_hook_refuses_when_visibility_changes_or_the_remote_differs(tmp_path, store_root, bare, scripted_gh):
    sync.init(store_root, REPO, remote_url=str(bare), run=FakeGh())
    (store_root / "note.md").write_text("change\n")
    _git("add", "-A", cwd=store_root), _git("commit", "-q", "-m", "change", cwd=store_root)

    scripted_gh.write_text("PUBLIC")
    refused = _git("push", "origin", "HEAD:main", cwd=store_root)
    assert refused.returncode != 0 and "not PRIVATE" in refused.stderr

    scripted_gh.write_text("PRIVATE")
    elsewhere = tmp_path / "elsewhere.git"
    _git("init", "-q", "--bare", str(elsewhere))
    wrong_remote = _git("push", str(elsewhere), "HEAD:main", cwd=store_root)
    assert wrong_remote.returncode != 0 and "syncs only to" in wrong_remote.stderr


@posix_only
def test_push_rechecks_visibility_and_origin_in_python(tmp_path, store_root, bare, scripted_gh):
    sync.init(store_root, REPO, remote_url=str(bare), run=FakeGh())
    with pytest.raises(AcquaintError, match="not PRIVATE"):
        sync.push(store_root, run=FakeGh(visibility="PUBLIC"))
    _git("remote", "set-url", "origin", str(tmp_path / "somewhere-else.git"), cwd=store_root)
    with pytest.raises(AcquaintError, match="refusing"):
        sync.push(store_root, run=FakeGh())
