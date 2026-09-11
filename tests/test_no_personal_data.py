"""The no-personal-data guard: nothing in this public repository identifies a real person.

People's data lives in the operator's data root, never here. This scans every text file
in the repository (not just what git tracks, so a new file is covered before it is
committed) for the mechanical signs of a leak:

- an email address outside the placeholder domains;
- an absolute local home path;
- a ``github.com/<owner>`` URL, ``owner/repo`` string or ``@handle`` whose owner or
  handle is not on the small allowlist of placeholders and this project's own orgs.

It cannot catch a real name written as prose; that part is on whoever writes the text.
Strings that must look like leaks inside this file are built by concatenation, so the
guard does not trip on itself.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Project metadata names the package's own author and URL; out of scope here.
_EXCLUDED_FILES = {"LICENSE"}
_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "dist", "build", ".venv", "venv", ".tox", "node_modules", "handoffs", "scratch"}
_TEXT_SUFFIXES = {".py", ".md", ".toml", ".json", ".txt", ".yml", ".yaml", ".sh", ".cfg", ""}

PLACEHOLDER_DOMAINS = {"example.org", "example.com", "example.net"}
#: git's SSH user, as in a remote URL; not a mailbox.
ALLOWED_ADDRESSES = {"git" + "@" + "github.com"}
#: Fictional placeholders and this project's own GitHub owners.
ALLOWED_OWNERS = {"example", "example-org", "octocat", "owner", "thorwhalen", "i2mint"}

EMAIL_RE = re.compile(r"[A-Za-z0-9_.+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
HOME_PATH_RE = re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+|\b[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+")
GITHUB_URL_RE = re.compile(r"github\.com[/:]([A-Za-z0-9][A-Za-z0-9-]{0,38})(?=[/\s\"')\]]|\.git|$)")
#: owner/name only where it names a GitHub repository: after --repo, in a gh command,
#: or assigned to a repo variable. Path fragments like "people/ada-lovelace" are not repos.
OWNER_REPO_RE = re.compile(
    r"(?:--repo[= ]|gh repo \w+ |\brepo\w*\s*[=:]\s*[\"']|\bREPO\s*=\s*[\"'])([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9._-]+)"
)
MENTION_RE = re.compile(r"(?<![\w.@/`])@([A-Za-z0-9][A-Za-z0-9-]{1,38})\b(?![.(])")


def _text_files() -> list[Path]:
    return [
        path
        for path in REPO_ROOT.rglob("*")
        if path.is_file()
        and path.name not in _EXCLUDED_FILES
        and path.suffix in _TEXT_SUFFIXES
        and not any(part in _SKIP_DIRS or part.endswith((".dist-info", ".egg-info")) or part == "site-packages" for part in path.relative_to(REPO_ROOT).parts)
    ]


def emails_outside_placeholders(text: str) -> list[str]:
    return [
        m.group(0)
        for m in EMAIL_RE.finditer(text)
        if m.group(1).lower() not in PLACEHOLDER_DOMAINS and m.group(0) not in ALLOWED_ADDRESSES
    ]


def handles_outside_allowlist(text: str, *, prose: bool) -> list[str]:
    found = [m.group(1) for m in GITHUB_URL_RE.finditer(text)]
    found += [m.group(1) for m in OWNER_REPO_RE.finditer(text) if not m.group(1).isdigit()]
    if prose:
        found += [m.group(1) for m in MENTION_RE.finditer(text)]
    return sorted({h for h in found if h.lower() not in ALLOWED_OWNERS})


def test_no_email_addresses_outside_placeholder_domains():
    offenders = {str(p.relative_to(REPO_ROOT)): found for p in _text_files() if (found := emails_outside_placeholders(p.read_text(encoding="utf-8", errors="replace")))}
    assert not offenders, f"email address(es) outside {sorted(PLACEHOLDER_DOMAINS)}: {offenders}"


def test_no_absolute_home_paths():
    offenders = {str(p.relative_to(REPO_ROOT)): HOME_PATH_RE.findall(p.read_text(encoding="utf-8", errors="replace")) for p in _text_files()}
    offenders = {k: v for k, v in offenders.items() if v}
    assert not offenders, f"absolute home path(s): {offenders}"


def test_no_real_looking_handles():
    offenders = {}
    for path in _text_files():
        found = handles_outside_allowlist(path.read_text(encoding="utf-8", errors="replace"), prose=path.suffix != ".py")
        if found:
            offenders[str(path.relative_to(REPO_ROOT))] = found
    assert not offenders, f"handle(s) not on the placeholder allowlist {sorted(ALLOWED_OWNERS)}: {offenders}"


def test_the_guard_actually_catches_leaks():
    """Mutation check: each detector must fire on a planted leak, or the guard guards nothing."""
    planted_email = "someone" + "@" + "realmail.test"
    assert emails_outside_placeholders(f"write to {planted_email}") == [planted_email]
    assert emails_outside_placeholders("write to ada" + "@" + "example.org") == []
    assert HOME_PATH_RE.search("/" + "Users" + "/someone/profiles")
    assert handles_outside_allowlist("see github.com/" + "someone-real" + "/notes", prose=False) == ["someone-real"]
    assert handles_outside_allowlist("gh repo create " + "someone" + "/profiles --private", prose=False) == ["someone"]
    assert handles_outside_allowlist("thanks @" + "someone-real" + " for this", prose=True) == ["someone-real"]
    assert handles_outside_allowlist("thanks @octocat", prose=True) == []
