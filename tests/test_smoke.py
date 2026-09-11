"""The one-command test: the whole path, end to end, on the CLI, against a temporary data directory.

This is the definition of v0.1, and it must keep passing after every later change::

    acquaint new person "Ada Lovelace" \\
      && acquaint remember ada-lovelace "prefers email for anything with attachments" \\
           --source "https://example.org/thread/1" \\
      && acquaint who ada -f aka \\
      && acquaint brief ada-lovelace --purpose ask
"""

import os
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
    """Issue #14: 0 reachable, 1 nothing recorded, 3 a rule matched but its channel has no address (with or without --json)."""
    assert _acquaint(["new", "person", "Ada Lovelace"], tmp_path).returncode == 0
    nothing = _acquaint(["reach", "ada-lovelace"], tmp_path)
    assert nothing.returncode == 1 and "no active identities or rules recorded" in nothing.stderr

    rules = "rules:\n- when: {urgency: high}\n  do: {channel: pager}\n  set_by: self\n  source: operator\n"
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(rules, encoding="utf-8")
    matched = _acquaint(["reach", "ada-lovelace", "--urgency", "high"], tmp_path)
    assert matched.returncode == 3, (matched.stdout, matched.stderr)
    assert matched.stdout.strip() == "1. pager  [self]  (no pager address recorded)"
    assert "no usable address is recorded for pager" in matched.stderr and "no active identities" not in matched.stderr
    assert _acquaint(["reach", "ada-lovelace", "--urgency", "high", "--json"], tmp_path).returncode == 3

    added = _acquaint(["remember", "ada-lovelace", "pager:example-rotation", "--kind", "identity", "--source", "operator"], tmp_path)
    assert added.returncode == 0, added.stderr
    reached = _acquaint(["reach", "ada-lovelace", "--urgency", "high"], tmp_path)
    assert reached.returncode == 0 and "pager → pager:example-rotation" in reached.stdout, (reached.stdout, reached.stderr)
