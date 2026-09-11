"""Sync to a private repository, tested without GitHub.

``gh`` is scripted: a fake runner answers Python's calls, and a fake ``gh`` first on
``PATH`` answers the hook. ``git`` is real. The GitHub URLs are redirected to local bare
repositories with ``url.<bare>.insteadOf`` in an isolated global git config, which is also
how a user's own URL rewriting behaves. No real repository is created.
"""

import os
import shutil
import subprocess
import sys

import pytest

from acquaint import sync
from acquaint.resources import data_text
from acquaint.store import AcquaintError

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="the pre-push guard and the fake gh are POSIX shell scripts")
REPO = "example/profiles"
URL = "git@github.com:example/profiles.git"
OTHER_URL = "git@github.com:example/elsewhere.git"


def _git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


@pytest.fixture(autouse=True)
def gitconfig(tmp_path, monkeypatch):
    config = tmp_path / "gitconfig"
    config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "acquaint tests")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "tests" + "@" + "example.org")
    return config


def _bare(path):
    assert _git("init", "-q", "--bare", str(path)).returncode == 0
    return path


@pytest.fixture
def github(tmp_path, gitconfig):
    """The two GitHub URLs reach local bare repositories: ``{URL: bare, OTHER_URL: bare}``."""
    remotes = {URL: _bare(tmp_path / "profiles.git"), OTHER_URL: _bare(tmp_path / "elsewhere.git")}
    for url, bare in remotes.items():
        _git("config", "--file", str(gitconfig), f"url.{bare.as_posix()}.insteadOf", url)
    return remotes


@pytest.fixture
def scripted_gh(tmp_path, monkeypatch):
    """A ``gh`` executable first on PATH, for the hook; the test can change its answer."""
    answer = tmp_path / "visibility"
    answer.write_text("PRIVATE")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "gh"
    script.write_text(f'#!/bin/sh\ncat "{answer}"\n')
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return answer


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
            if ".sshUrl" in args:
                return done(0, URL + "\n")
            return done(0, self.visibility + "\n") if "-q" in args else done(0, "{}")
        raise AssertionError(f"unexpected gh call {args}")


@pytest.fixture
def store_root(tmp_path):
    root = tmp_path / "data"
    (root / "people" / "ada-lovelace").mkdir(parents=True)
    (root / "people" / "ada-lovelace" / "PROFILE.md").write_text("---\nname: Ada Lovelace\n---\n")
    return root


def _commit(folder, name="note.md"):
    (folder / name).write_text("change\n")
    _git("add", "-A", cwd=folder)
    _git("commit", "-q", "-m", "change", cwd=folder)


def _reached(bare, ref="main"):
    return _git("--git-dir", str(bare), "rev-parse", "--verify", ref).returncode == 0


# --------------------------------------------------------------- everywhere


def test_dry_run_plans_and_touches_nothing(store_root):
    def refuse(*args, **kwargs):
        raise AssertionError("a dry run runs nothing")

    result = sync.init(store_root, REPO, dry_run=True, run=refuse)
    assert result["dry_run"] and any("PRIVATE" in step for step in result["plan"])
    assert not (store_root / ".git").exists()


def test_refuses_a_repository_that_is_not_private(store_root):
    with pytest.raises(AcquaintError, match="not PRIVATE"):
        sync.init(store_root, REPO, remote_url=URL, run=FakeGh(visibility="PUBLIC"))
    assert not (store_root / ".git").exists(), "refused before the store became a repository"


@pytest.mark.parametrize(
    "remote",
    [
        OTHER_URL,
        "git@gitlab.com:example/profiles.git",
        "/srv/git/profiles.git",
        "https://github.com/example/profiles.git/",
        "git@github.com/example/profiles.git",
    ],
)
def test_the_remote_must_be_a_url_of_the_repository_whose_visibility_is_checked(store_root, remote):
    with pytest.raises(AcquaintError, match="is not a url of the GitHub repository"):
        sync.init(store_root, REPO, remote_url=remote, run=FakeGh())
    assert not (store_root / ".git").exists()


def test_gcrypt_remotes_are_refused_until_the_guard_supports_them(store_root):
    with pytest.raises(AcquaintError, match="not supported yet"):
        sync.init(store_root, REPO, remote_url="gcrypt::" + URL, dry_run=True)


def test_the_hook_accepts_exactly_the_url_forms_python_does():
    hook = data_text("hooks/pre-push")
    for form in sync.github_urls("$repo"):
        assert f'"{form}"' in hook, form


def test_init_refuses_to_take_over_an_unrelated_repository(store_root):
    assert _git("init", "-q", cwd=store_root).returncode == 0
    _git("remote", "add", "origin", "git@github.com:example/some-app.git", cwd=store_root)
    with pytest.raises(AcquaintError, match="already a git repository"):
        sync.init(store_root, REPO, remote_url=URL, run=FakeGh())
    assert _git("config", "--get-all", "remote.origin.url", cwd=store_root).stdout.split() == ["git@github.com:example/some-app.git"]


def test_rejects_a_malformed_repo_name(store_root):
    with pytest.raises(AcquaintError, match="owner/name"):
        sync.init(store_root, "profiles", dry_run=True)


def test_status_of_a_store_that_is_not_synced(store_root):
    assert sync.status(store_root, run=FakeGh())["synced"] is False


# ------------------------------------------------------------------ POSIX


@posix_only
def test_gh_is_pinned_to_github_com(scripted_gh, monkeypatch):
    scripted_gh.parent.joinpath("bin", "gh").write_text('#!/bin/sh\necho "$GH_HOST"\n')
    monkeypatch.setenv("GH_HOST", "enterprise.example.org")
    assert sync.run_command(["gh", "repo", "view"]).stdout.strip() == "github.com"


@posix_only
def test_init_creates_private_pushes_and_guards(store_root, github, scripted_gh):
    gh = FakeGh(exists=False)
    result = sync.init(store_root, REPO, run=gh)
    assert result["pushed"] and result["visibility"] == "PRIVATE" and result["remote"] == URL
    assert ["gh", "repo", "create", REPO, "--private", "--description", "acquaint profile store (private)"] in gh.calls
    assert "people/ada-lovelace/PROFILE.md" in _git("--git-dir", str(github[URL]), "ls-tree", "-r", "--name-only", "main").stdout
    assert os.path.isabs(_git("config", "core.hooksPath", cwd=store_root).stdout.strip())
    assert (store_root / ".gitattributes").is_file()

    status = sync.status(store_root, run=gh)
    assert (status["hook_installed"], status["visibility"], status["ahead"], status["behind"]) == (True, "PRIVATE", 0, 0)


@posix_only
def test_a_clone_of_the_same_repository_can_be_adopted(tmp_path, store_root, github, scripted_gh):
    sync.init(store_root, REPO, run=FakeGh())
    server = tmp_path / "server-data"
    assert _git("clone", "-q", "--branch", "main", URL, str(server)).returncode == 0
    assert sync.init(server, REPO, create=False, run=FakeGh())["pushed"]
    assert sync.status(server, run=FakeGh())["hook_installed"]


@posix_only
def test_push_and_pull_round_trip(tmp_path, store_root, github, scripted_gh):
    gh = FakeGh()
    sync.init(store_root, REPO, run=gh)
    (store_root / "people" / "ada-lovelace" / "PROFILE.md").write_text("---\nname: Ada Lovelace\naka: [Ada]\n---\n")
    assert sync.push(store_root, run=gh)["committed"]

    other = tmp_path / "other-clone"
    assert _git("clone", "-q", "--branch", "main", URL, str(other)).returncode == 0
    (other / "people" / "grace-example").mkdir(parents=True)
    _commit(other / "people" / "grace-example", "PROFILE.md")
    assert _git("push", "-q", "origin", "main", cwd=other).returncode == 0

    assert sync.pull(store_root, run=gh)["pulled"]
    assert (store_root / "people" / "grace-example" / "PROFILE.md").is_file()


@posix_only
def test_the_hook_refuses_every_other_destination_and_lost_privacy(store_root, github, scripted_gh):
    sync.init(store_root, REPO, run=FakeGh())
    _commit(store_root)

    scripted_gh.write_text("PUBLIC")
    refused = _git("push", "origin", "HEAD:main", cwd=store_root)
    assert refused.returncode != 0 and "not PRIVATE" in refused.stderr
    scripted_gh.write_text("PRIVATE")

    to_url = _git("push", str(github[OTHER_URL]), "HEAD:main", cwd=store_root)
    assert to_url.returncode != 0 and "origin only" in to_url.stderr

    _git("remote", "add", "mirror", OTHER_URL, cwd=store_root)
    to_other_remote = _git("push", "mirror", "HEAD:main", cwd=store_root)
    assert to_other_remote.returncode != 0 and "origin only" in to_other_remote.stderr

    _git("config", "remote.origin.pushurl", OTHER_URL, cwd=store_root)
    via_pushurl = _git("push", "origin", "HEAD:main", cwd=store_root)
    assert via_pushurl.returncode != 0 and "pushurl" in via_pushurl.stderr
    _git("config", "--unset-all", "remote.origin.pushurl", cwd=store_root)

    _git("remote", "set-url", "origin", OTHER_URL, cwd=store_root)
    _git("config", "acquaint.remote", OTHER_URL, cwd=store_root)
    repointed = _git("push", "origin", "HEAD:main", cwd=store_root)
    assert repointed.returncode != 0 and "is not a url of the GitHub repository" in repointed.stderr
    assert not _reached(github[OTHER_URL]), "nothing reached the other repository"


@posix_only
def test_a_second_origin_url_is_refused_by_the_hook_and_by_python(store_root, github, scripted_gh):
    sync.init(store_root, REPO, run=FakeGh())
    _commit(store_root)
    _git("config", "--unset-all", "remote.origin.url", cwd=store_root)
    _git("config", "--add", "remote.origin.url", OTHER_URL, cwd=store_root)
    _git("config", "--add", "remote.origin.url", URL, cwd=store_root)

    refused = _git("push", "origin", "HEAD:main", cwd=store_root)
    assert refused.returncode != 0 and "exactly one url" in refused.stderr
    with pytest.raises(AcquaintError, match="exactly one url"):
        sync.push(store_root, run=FakeGh())
    assert not _reached(github[OTHER_URL]), "nothing reached the other repository"


@posix_only
def test_a_push_insteadof_redirect_is_refused_by_the_hook_and_by_python(store_root, github, gitconfig, scripted_gh):
    sync.init(store_root, REPO, run=FakeGh())
    _commit(store_root)
    _git("config", "--file", str(gitconfig), f"url.{github[OTHER_URL].as_posix()}.pushInsteadOf", URL)

    refused = _git("push", "origin", "HEAD:main", cwd=store_root)
    assert refused.returncode != 0 and "pushInsteadOf" in refused.stderr
    with pytest.raises(AcquaintError, match="pushInsteadOf"):
        sync.push(store_root, run=FakeGh())
    assert not _reached(github[OTHER_URL])


@posix_only
def test_a_linked_worktree_is_guarded_too(tmp_path, store_root, github, scripted_gh):
    sync.init(store_root, REPO, run=FakeGh())
    worktree = tmp_path / "worktree"
    assert _git("worktree", "add", "-q", "-b", "side", str(worktree), cwd=store_root).returncode == 0
    _commit(worktree)

    to_url = _git("push", str(github[OTHER_URL]), "HEAD:refs/heads/side", cwd=worktree)
    assert to_url.returncode != 0 and "origin only" in to_url.stderr
    scripted_gh.write_text("PUBLIC")
    refused = _git("push", "origin", "HEAD:refs/heads/side", cwd=worktree)
    assert refused.returncode != 0 and "not PRIVATE" in refused.stderr


@posix_only
def test_python_push_and_pull_recheck_everything(tmp_path, store_root, github, scripted_gh):
    sync.init(store_root, REPO, run=FakeGh())
    with pytest.raises(AcquaintError, match="not PRIVATE"):
        sync.push(store_root, run=FakeGh(visibility="PUBLIC"))
    with pytest.raises(AcquaintError, match="not PRIVATE"):
        sync.pull(store_root, run=FakeGh(visibility="PUBLIC"))

    _git("config", "core.hooksPath", str(tmp_path / "some-other-hooks"), cwd=store_root)
    with pytest.raises(AcquaintError, match="guard is not active"):
        sync.push(store_root, run=FakeGh())
    sync.init(store_root, REPO, create=False, run=FakeGh())

    hook = sync._hook_path(store_root, FakeGh())
    hook.chmod(0o644)
    assert sync.status(store_root, run=FakeGh())["hook_installed"] is False
    with pytest.raises(AcquaintError, match="guard is not active"):
        sync.push(store_root, run=FakeGh())
    hook.chmod(0o755)
    assert sync.push(store_root, run=FakeGh())["pushed"]

    _git("config", "remote.origin.pushurl", OTHER_URL, cwd=store_root)
    with pytest.raises(AcquaintError, match="pushurl"):
        sync.push(store_root, run=FakeGh())
    _git("config", "--unset-all", "remote.origin.pushurl", cwd=store_root)

    _git("remote", "set-url", "origin", OTHER_URL, cwd=store_root)
    with pytest.raises(AcquaintError, match="refusing"):
        sync.push(store_root, run=FakeGh())
