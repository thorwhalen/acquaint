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
    assert "no match for 'nobody'" in result.stderr
