"""Shipped skills and agents: spec-valid, bridged into ``.claude/``, pointing at sections and commands that exist."""

import os
import re
import sys
from pathlib import Path

import pytest
import yaml

from acquaint.resources import data_path
from acquaint.tools import TOOLS

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "acquaint" / "data" / "skills"
AGENTS = REPO / "acquaint" / "data" / "agents"
EXPECTED_SKILLS = {"acquaint", "acquaint-profile", "acquaint-write", "acquaint-read", "deslop", "acquaint-sync"}
EXPECTED_AGENTS = {"profile-reader", "recipient-reader"}
#: Top-level keys the Agent Skills specification allows.
SPEC_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEADING_RE = re.compile(r"^#+\s+(.+?)\s*$", re.M)


def _split(path: Path) -> tuple[dict, str]:
    match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", path.read_text(encoding="utf-8"), re.S)
    assert match, f"{path} has no frontmatter"
    return yaml.safe_load(match.group(1)), match.group(2)


def test_exactly_the_expected_skills_and_agents_ship():
    assert {p.name for p in SKILLS.iterdir() if p.is_dir()} == EXPECTED_SKILLS
    assert {p.stem for p in AGENTS.glob("*.md")} == EXPECTED_AGENTS
    assert data_path("skills", "acquaint", "SKILL.md").is_file(), "skills are package data"


@pytest.mark.parametrize("name", sorted(EXPECTED_SKILLS))
def test_skill_is_spec_valid(name):
    meta, body = _split(SKILLS / name / "SKILL.md")
    assert set(meta) <= SPEC_KEYS, f"non-spec keys: {set(meta) - SPEC_KEYS}"
    assert meta["name"] == name and NAME_RE.match(name) and len(name) <= 64
    assert 0 < len(meta["description"]) <= 1024
    assert meta["metadata"]["audience"] in {"users", "developers", "both"}
    assert len(body.splitlines()) < 500


@pytest.mark.skipif(not (REPO / ".claude").is_dir(), reason="not a checkout (sdists leave .claude out)")
@pytest.mark.skipif(sys.platform == "win32", reason="git checks symlinks out as plain files on Windows by default")
def test_claude_code_bridges_are_relative_symlinks():
    for name in EXPECTED_SKILLS:
        link = REPO / ".claude" / "skills" / name
        assert link.is_symlink() and os.readlink(link) == f"../../acquaint/data/skills/{name}", name
        assert (link / "SKILL.md").is_file()
    for name in EXPECTED_AGENTS:
        link = REPO / ".claude" / "agents" / f"{name}.md"
        assert link.is_symlink() and os.readlink(link) == f"../../acquaint/data/agents/{name}.md", name


@pytest.mark.parametrize("name", sorted(EXPECTED_AGENTS))
def test_agents_point_at_skill_sections_instead_of_repeating_them(name):
    meta, body = _split(AGENTS / f"{name}.md")
    assert meta["name"] == name and meta["description"]
    [method] = re.findall(r"^Method: (.+)$", body, re.M)
    for pointer in (p.strip() for p in method.split(";")):
        skill, _, section = pointer.partition(" § ")
        headings = set(HEADING_RE.findall((SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")))
        assert section in headings, f"{name} points at {skill} § {section!r}, which does not exist"
    assert len(body.splitlines()) < 30, "an agent's body points at its skill; it does not duplicate it"


def test_skills_only_mention_commands_the_cli_has():
    commands = {t.__name__.replace("_", "-") for t in TOOLS if not t.__name__.startswith("sync_")} | {"sync"}
    sync_commands = {t.__name__.removeprefix("sync_") for t in TOOLS if t.__name__.startswith("sync_")}
    for skill in SKILLS.glob("*/SKILL.md"):
        text = skill.read_text(encoding="utf-8")
        # Commands appear in fenced code blocks or inline code; prose ("acquaint keeps…") is not a command.
        code = "\n".join(re.findall(r"^```[^\n]*\n(.*?)^```", text, re.M | re.S))
        mentions = re.findall(r"^\s*acquaint ([a-z][a-z-]*)", code, re.M) + re.findall(r"`acquaint ([a-z][a-z-]*)", text)
        for command in mentions:
            assert command in commands, f"{skill.parent.name} mentions `acquaint {command}`"
        for command in re.findall(r"acquaint sync ([a-z]+)", code + "\n" + "\n".join(re.findall(r"`([^`]+)`", text))):
            assert command in sync_commands, f"{skill.parent.name} mentions `acquaint sync {command}`"
