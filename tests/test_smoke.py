"""The one-command test: the whole path, end to end, on the CLI, against a temporary data directory.

This is the definition of v0.1, and it must keep passing after every later change::

    acquaint new person "Ada Lovelace" \\
      && acquaint remember ada-lovelace "prefers email for anything with attachments" \\
           --source "https://example.org/thread/1" \\
      && acquaint who ada -f aka \\
      && acquaint brief ada-lovelace --purpose ask
"""

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ONE_COMMAND = (
    'acquaint new person "Ada Lovelace"'
    ' && acquaint remember ada-lovelace "prefers email for anything with attachments"'
    ' --source "https://example.org/thread/1"'
    " && acquaint who ada -f aka"
    " && acquaint brief ada-lovelace --purpose ask"
)


def _env(data_dir: Path) -> dict:
    return {**os.environ, "ACQUAINT_DATA_DIR": str(data_dir), "PYTHONIOENCODING": "utf-8"}


def _acquaint(args: list[str], data_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "acquaint", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_env(data_dir),
    )


def _assert_useful_brief(brief: str) -> None:
    assert "# Brief: Ada Lovelace (person:ada-lovelace)" in brief
    assert "prefers email for anything with attachments" in brief
    assert "https://example.org/thread/1" in brief, "the observation's source travels with it"
    assert "One ask per message" in brief, "guidance for the stated purpose"
    assert "Not known (ask, don't guess)" in brief, "gaps are stated, not filled in"


def test_one_command_path(tmp_path):
    steps = [
        ["new", "person", "Ada Lovelace"],
        ["remember", "ada-lovelace", "prefers email for anything with attachments", "--source", "https://example.org/thread/1"],
        ["who", "ada", "-f", "aka"],
        ["brief", "ada-lovelace", "--purpose", "ask"],
    ]
    outputs = []
    for step in steps:
        result = _acquaint(step, tmp_path)
        assert result.returncode == 0, (step, result.stdout, result.stderr)
        outputs.append(result.stdout)

    assert outputs[2].split() == ["Ada", "Lovelace"]
    _assert_useful_brief(outputs[3])
    assert (tmp_path / "people" / "ada-lovelace" / "PROFILE.md").is_file()
    assert (tmp_path / "people" / "ada-lovelace" / "log").is_dir()
    assert (tmp_path / "POLICY.md").is_file()


def _console_script_is_this_install() -> bool:
    script = shutil.which("acquaint")
    return bool(script) and Path(script).resolve().parent == Path(sys.executable).resolve().parent


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell line")
@pytest.mark.skipif(not _console_script_is_this_install(), reason="the acquaint console script on PATH is not this interpreter's")
def test_one_command_as_the_shell_line(tmp_path):
    result = subprocess.run(ONE_COMMAND, shell=True, capture_output=True, text=True, encoding="utf-8", env=_env(tmp_path))
    assert result.returncode == 0, result.stderr
    _assert_useful_brief(result.stdout)


def test_a_failed_lookup_exits_nonzero_with_a_reason(tmp_path):
    result = _acquaint(["who", "nobody"], tmp_path)
    assert result.returncode == 1
    assert "no entity named 'nobody'" in result.stderr


def test_reach_exit_status_tells_a_matched_rule_without_an_address_apart(tmp_path):
    """Issue #14: 3 when a matched rule's channel has no address (with or without --json), 1 when no rule names a channel, 0 once the suggested line is run."""
    for kind in ("person", "org"):  # two records share the slug, so the suggested line must name the kind
        assert _acquaint(["new", kind, "Ada Lovelace"], tmp_path).returncode == 0
    rules = "rules:\n- when: {urgency: high}\n  do: {channel: pager}\n  set_by: self\n  source: operator\n"
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(rules, encoding="utf-8")

    unmatched = _acquaint(["reach", "person:ada-lovelace"], tmp_path)
    assert unmatched.returncode == 1 and "no matching rule names a channel" in unmatched.stderr, unmatched.stderr

    matched = _acquaint(["reach", "person:ada-lovelace", "--urgency", "high"], tmp_path)
    assert matched.returncode == 3, (matched.stdout, matched.stderr)
    assert matched.stdout.strip() == "1. pager  [self]  (no pager address recorded)"
    assert "no usable address is recorded for pager" in matched.stderr and "no active identit" not in matched.stderr
    assert _acquaint(["reach", "person:ada-lovelace", "--urgency", "high", "--json"], tmp_path).returncode == 3

    advice = re.search(r"`acquaint (remember [^`]+)`", matched.stderr).group(1)
    args = [a.replace("<address>", "example-rotation").replace("<source>", "operator") for a in shlex.split(advice)]
    followed = _acquaint(args, tmp_path)
    assert followed.returncode == 0, (advice, followed.stderr)
    reached = _acquaint(["reach", "person:ada-lovelace", "--urgency", "high"], tmp_path)
    assert reached.returncode == 0 and "pager → pager:example-rotation" in reached.stdout, (reached.stdout, reached.stderr)


def test_remember_refuses_an_identity_equal_to_an_inactive_one_until_reactivated(tmp_path):
    """Issue #17: refused with exit 1 and the entry named, not "recorded"; the printed command reactivates it."""
    assert _acquaint(["new", "person", "Ada Lovelace"], tmp_path).returncode == 0
    handle = ["remember", "ada-lovelace", "pager:example-rotation", "--kind", "identity"]
    assert _acquaint([*handle, "--source", "operator"], tmp_path).returncode == 0
    identities = tmp_path / "people" / "ada-lovelace" / "identities.yaml"
    identities.write_text(identities.read_text(encoding="utf-8").replace("status: active", "status: stale"), encoding="utf-8")

    refused = _acquaint([*handle, "--source", "https://example.org/roster"], tmp_path)
    assert refused.returncode == 1 and "already recorded for person:ada-lovelace as stale" in refused.stderr, refused.stderr
    assert "recorded identity" not in refused.stdout + refused.stderr
    assert _acquaint(["resolve", "pager:example-rotation"], tmp_path).returncode == 1, "still inactive"

    command = shlex.split(refused.stderr[refused.stderr.index("acquaint remember"):])
    assert command[0] == "acquaint" and command[-3:] == ["--reactivate", "--source", "https://example.org/roster"], command
    reactivated = _acquaint(command[1:], tmp_path)
    assert reactivated.returncode == 0, reactivated.stderr
    assert "reactivated identity pager:example-rotation (was stale) for ada-lovelace" in reactivated.stdout
    assert _acquaint(["resolve", "pager:example-rotation"], tmp_path).returncode == 0


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell")
def test_the_printed_reactivate_command_is_safe_to_paste_into_a_shell(tmp_path):
    """The refusal's command survives a POSIX shell: no redirection, one argument per word, with or without a source."""
    data, cwd = tmp_path / "data", tmp_path / "cwd"
    data.mkdir()
    cwd.mkdir()
    assert _acquaint(["new", "person", "Ada Lovelace"], data).returncode == 0
    handle = ["remember", "ada-lovelace", "pager:example rotation", "--kind", "identity"]
    assert _acquaint([*handle, "--source", "operator"], data).returncode == 0
    identities = data / "people" / "ada-lovelace" / "identities.yaml"
    identities.write_text(identities.read_text(encoding="utf-8").replace("status: active", "status: stale"), encoding="utf-8")
    for source in ([], ["--source", 'self: "it is $HOME `now`"']):
        refused = _acquaint([*handle, *source], data)
        assert refused.returncode == 1, refused.stderr
        command = refused.stderr[refused.stderr.index("acquaint remember"):].strip()
        echoed = subprocess.run("printf '%s\\n' " + command.removeprefix("acquaint "), shell=True, capture_output=True, text=True, cwd=cwd)
        assert (echoed.returncode, echoed.stderr) == (0, ""), command
        assert echoed.stdout.splitlines() == shlex.split(command)[1:]
    assert list(cwd.iterdir()) == [], "nothing was redirected into a file"
