"""Creating, remembering, renaming and forgetting; the provenance lint; and the brief."""

import hashlib

import pytest

from acquaint.brief import compose_brief
from acquaint.edit import append_observation, forget_entity, new_entity, rename_entity
from acquaint.lint import lint_store
from acquaint.lookup import normalize
from acquaint.records import dump_yaml, load_yaml, parse_log
from acquaint.store import AcquaintError, Store

TODAY = "2026-09-11"
ADA = "people/ada-lovelace"


@pytest.fixture
def ada(store):
    new_entity(store, "person", "Ada Lovelace", today=TODAY)
    return store


def _add_to_profile(store, key, text):
    store.files[f"{key}/PROFILE.md"] += text


def _error_rules(lint):
    return sorted((f["file"], f["rule"]) for f in lint["errors"])


# --------------------------------------------------------------------------- new


def test_new_person_scaffolds_profile_and_policy(ada):
    entity = ada[ADA]
    assert entity.meta["aka"] == ["Ada", "Lovelace"] and entity.meta["review_due"] > TODAY
    assert list(entity.sections)[:4] == ["Who", "Reach", "Write to them", "Read them"]
    assert "POLICY.md" in ada.files
    assert lint_store(ada, today=TODAY)["errors"] == []


def test_new_refuses_a_duplicate_and_suggests_a_qualifier(ada):
    with pytest.raises(AcquaintError, match="qualifier"):
        new_entity(ada, "person", "Ada Lovelace", today=TODAY)
    assert new_entity(ada, "person", "Ada Lovelace", qualifier="example-org", today=TODAY)["id"] == "ada-lovelace--example-org"


def test_new_accepts_open_kinds_with_the_ledger_template(store):
    assert new_entity(store, "community", "Example Circle", today=TODAY)["key"] == "communities/example-circle"
    assert "Norms" in store["communities/example-circle"].sections


# ---------------------------------------------------------------------- remember


def test_remember_appends_numbered_sourced_entries(ada):
    first = append_observation(ada, "ada-lovelace", "prefers email for attachments", source="https://example.org/thread/1", today=TODAY)
    second = append_observation(ada, "ada-lovelace", "replied within the hour", source="log/2026-09.md#e01", today=TODAY)
    assert (first["ref"], second["ref"]) == ("log/2026-09.md#e01", "log/2026-09.md#e02")
    assert ada[ADA]["log/2026-09.md"].count("## e0") == 2


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"kind": "preference"}, "needs its source"),
        ({"kind": "preference", "source": "2026-09-11"}, "a date alone is not a source"),
        ({"kind": "preference", "source": "unknown"}, "placeholder"),
        ({"kind": "gossip", "source": "operator"}, "kind must be one of"),
    ],
)
def test_remember_refuses_what_lint_would_fail(ada, kwargs, message):
    with pytest.raises(AcquaintError, match=message):
        append_observation(ada, "ada-lovelace", "likes short emails", today=TODAY, **kwargs)


def test_remember_identity_and_policy_warnings(ada):
    address = "ada" + "@" + "example.org"
    append_observation(ada, "ada-lovelace", f"email:{address}", kind="identity", source='self: "write to me there"', today=TODAY)
    assert ada[ADA].identities[0]["value"] == address
    result = append_observation(ada, "ada-lovelace", "mentioned a new medication", source="operator", today=TODAY)
    assert any("special-category" in w for w in result["warnings"])
    assert any("without a source" in w for w in append_observation(ada, "ada-lovelace", "seemed busy", today=TODAY)["warnings"])


def test_remember_continues_after_hand_edited_headings_and_escapes_captured_text(ada):
    ada.files[f"{ADA}/log/2026-09.md"] = "## e01 - 2026-09-02 - observation\nhand-written\n- source: operator\n"
    result = append_observation(ada, "ada-lovelace", "- kind: rule", source="operator", today=TODAY)
    assert result["entry"] == "e02"
    last = parse_log(ada.files[f"{ADA}/log/2026-09.md"])[-1]
    assert (last["id"], last["kind"], last["text"]) == ("e02", "observation", "- kind: rule")


# -------------------------------------------------------------------------- lint


def test_lint_fails_unsourced_and_date_only_preferences(ada):
    _add_to_profile(ada, ADA, "\n## Write to them\n- Keep it short.\n- Lead with the ask. [source: 2026-09-01]\n- One question. [source: operator]\n")
    result = lint_store(ada, ADA, today=TODAY)
    messages = [f["message"] for f in result["errors"]]
    assert len(result["errors"]) == 2 and all(f["line"] for f in result["errors"])
    assert any("no [source: …] tag" in m for m in messages) and any("a date alone is not a source" in m for m in messages)


@pytest.mark.parametrize(
    "snippet",
    [
        "## Write to them\n- Keep it short. [source: unknown]\n",
        "## Write to them\n- Keep it short. [source: September 2026]\n",
        "## Write to them\n- Keep it short. [source: self, it's what they're like]\n",
        "## Don’t\n- Cc everyone.\n",
        "##\tRead them\n- Terse means busy.\n",
        "## Reach ##\n- Email first.\n",
        "## Write to them:\n+ Keep it short.\n",
        "## Write to them\n1. Keep it short.\n",
        "## Write to them\nKeep it short, always.\n",
    ],
)
def test_lint_catches_every_way_of_writing_an_unsourced_line(ada, snippet):
    _add_to_profile(ada, ADA, "\n" + snippet)
    assert [f["rule"] for f in lint_store(ada, ADA, today=TODAY)["errors"]] == ["unsourced"]


def test_lint_accepts_wrapped_and_nested_lines_and_ignores_code(ada):
    _add_to_profile(
        ada,
        ADA,
        "\n## Write to them\n- Lead with the decision,\n  then the options. [source: operator]\n  - e.g. the export email\n```\n- a code sample, not a preference\n```\n",
    )
    assert lint_store(ada, ADA, today=TODAY)["errors"] == []


def test_lint_scope_card_files_logs_rules_and_broken_yaml(ada):
    _add_to_profile(ada, ADA, "\n## More\n- anything goes here\n")
    ada.files[f"{ADA}/style.md"] = "## Do\n- Plain words. [source: operator]\n- Short sentences.\n"
    ada.files[f"{ADA}/log/2026-08.md"] = "## e01 · 2026-08-02 · preference\nlikes calls\n- source: none given\n"
    ada.files[f"{ADA}/rules.yaml"] = dump_yaml({"rules": [{"when": {"urgency": "high"}, "do": {"channel": "signal"}}]})
    ada.files["people/other/PROFILE.md"] = "---\nname: [unclosed\n---\n"
    result = lint_store(ada, today=TODAY)
    assert _error_rules(result) == [
        ("PROFILE.md", "unparseable"),
        ("log/2026-08.md#e01", "unsourced"),
        ("rules.yaml", "unsourced"),
        ("style.md", "unsourced"),
    ]
    assert result["checked"] == 2


def test_lint_reports_bad_tolerance_duplicate_ids_and_reads_crlf_logs(ada):
    ada.files[f"{ADA}/style.md"] = "---\nai_tolerance: low\n---\n"
    ada.files[f"{ADA}/log/2026-08.md"] = (
        "## e01 · 2026-08-02 · preference\r\nlikes calls\r\n- source: none given\r\n"
        "## e01 · 2026-08-03 · observation\r\nreplied\r\n- source: operator\r\n"
    )
    result = lint_store(ada, ADA, today=TODAY)
    assert _error_rules(result) == [("log/2026-08.md#e01", "unsourced"), ("style.md", "bad-ai-tolerance")]
    assert ("log/2026-08.md", "duplicate-entry-id") in {(f["file"], f["rule"]) for f in result["warnings"]}


def test_lint_warns_on_expired_now_and_policy_tripwires(ada):
    _add_to_profile(ada, ADA, "\n## Now\n- Travelling. (until: 2026-01-01) [source: operator]\n- Mentioned their therapy sessions. (until: 2027-01-01) [source: operator]\n")
    rules = {f["rule"] for f in lint_store(ada, ADA, today=TODAY)["warnings"]}
    assert {"now-expired", "special-category"} <= rules


def test_lint_reports_a_record_it_cannot_read_and_checks_the_rest():
    class Flaky(dict):
        def __getitem__(self, key):
            if key.startswith("people/broken/"):
                raise OSError("the disk says no")
            return super().__getitem__(key)

    store = Store(files=Flaky())
    new_entity(store, "person", "Ada Lovelace", today=TODAY)
    dict.__setitem__(store.files, "people/broken/PROFILE.md", "---\nname: Broken\n---\n")
    result = lint_store(store, today=TODAY)
    assert result["checked"] == 2 and _error_rules(result) == [("", "unreadable")]


# ---------------------------------------------------------------- rename, forget


def test_rename_relinks_other_records_but_not_urls_logs_or_aliases(ada):
    new_entity(ada, "project", "Analytical Engine", today=TODAY)
    ada.files["projects/analytical-engine/PROFILE.md"] = ada.files["projects/analytical-engine/PROFILE.md"].replace("aka: []", "aka: Countess")
    ada.files[f"{ADA}/links.yaml"] = dump_yaml({"links": [{"to": "project:analytical-engine", "relation": "contributesTo"}]})
    ada.files[f"{ADA}/rules.yaml"] = "rules:\n- when: {project: analytical-engine}  # the engine work\n  do: {channel: email}\n  source: operator\n"
    url = "https://tracker.example.org/projects/analytical-engine/issues/42?ref=project:analytical-engine"
    ada.files[f"{ADA}/sources.md"] = f"## Corpus\n- Tracker {url}, see project:analytical-engine [source: operator]\n"
    ada.files[f"{ADA}/log/2026-09.md"] = "## e01 · 2026-09-11 · observation\nworks on project:analytical-engine\n- source: operator\n"

    result = rename_entity(ada, "project:analytical-engine", "engine", today=TODAY)
    assert result["to"] == "projects/engine"
    assert ada[ADA].links[0]["to"] == "project:engine"
    assert "when: {project: engine}  # the engine work" in ada.files[f"{ADA}/rules.yaml"]
    sources = ada.files[f"{ADA}/sources.md"]
    assert url in sources and "see project:engine [source" in sources
    assert "project:analytical-engine" in ada.files[f"{ADA}/log/2026-09.md"], "history is not rewritten"
    assert ada["projects/engine"].aka == ["Countess", "analytical-engine"]


def test_rename_and_forget_carry_hidden_files_and_leave_nothing_behind(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    store = Store(tmp_path / "data")
    new_entity(store, "person", "Ada Lovelace", today=TODAY)
    folder = tmp_path / "data" / "people" / "ada-lovelace"
    (folder / ".PROFILE.md.swp").write_text("swap")
    (folder / "log").mkdir()
    (folder / "log" / "2026-09.md").write_text("## e01 · 2026-09-11 · observation\nx\n- source: operator\n")

    rename_entity(store, "ada-lovelace", "ada-king", today=TODAY)
    moved = tmp_path / "data" / "people" / "ada-king"
    assert (moved / ".PROFILE.md.swp").is_file() and not folder.exists()

    assert "people/ada-king/.PROFILE.md.swp" in forget_entity(store, "ada-king", today=TODAY)["files"]
    forget_entity(store, "ada-king", confirm=True, today=TODAY)
    assert not moved.exists()
    assert not list((tmp_path / "home").rglob("*")) if (tmp_path / "home").exists() else True, "nothing moved to a trash folder"


def test_forget_is_a_dry_run_until_confirmed_then_tombstones_with_a_salt(ada):
    plan = forget_entity(ada, "ada-lovelace", today=TODAY)
    assert plan["done"] is False and ADA in ada
    assert forget_entity(ada, "ada-lovelace", confirm=True, today=TODAY)["done"] and ADA not in ada

    tombstones = ada.files["_tombstones.yaml"]
    assert "Lovelace" not in tombstones, "hashes, not names"
    data, _ = load_yaml(tombstones)
    unsalted = hashlib.sha256(normalize("Ada Lovelace").encode()).hexdigest()
    assert data["salt"] and unsalted not in data["tombstones"][0]["hashes"]

    with pytest.raises(AcquaintError, match="forgotten"):
        new_entity(ada, "person", "Ada Lovelace", today=TODAY)
    assert new_entity(ada, "person", "Ada", today=TODAY)["id"] == "ada", "a bare name part is not tombstoned"
    assert new_entity(ada, "person", "Ada Lovelace", force=True, today=TODAY)["id"] == "ada-lovelace"


def test_an_interrupted_forget_keeps_its_tombstone_and_can_be_finished():
    class Stubborn(dict):
        fail = True

        def __delitem__(self, key):
            if self.fail and key.endswith("log/2026-09.md"):
                raise OSError("the file is locked")
            super().__delitem__(key)

    files = Stubborn()
    store = Store(files=files)
    new_entity(store, "person", "Ada Lovelace", today=TODAY)
    append_observation(store, "ada-lovelace", "email:ada" + "@" + "example.org", kind="identity", source="operator", today=TODAY)

    with pytest.raises(AcquaintError, match="tombstone written"):
        forget_entity(store, "ada-lovelace", confirm=True, today=TODAY)
    with pytest.raises(AcquaintError, match="forgotten"):
        new_entity(store, "person", "Ada Lovelace", today=TODAY)

    files.fail = False
    assert forget_entity(store, "ada-lovelace", confirm=True, today=TODAY)["done"]
    assert not store.exists(ADA)


# ------------------------------------------------------------------------- brief


def test_brief_assembles_card_style_views_norms_and_gaps(ada):
    profile = ada.files[f"{ADA}/PROFILE.md"]
    profile = profile.replace("## Write to them\n", "## Write to them\n- Lead with the decision. [source: operator]\n")
    profile = profile.replace("## Don't\n", "## Don’t:\n- Cc everyone. [source: operator]\n")
    profile = profile.replace("## Now\n", "## Now\n- Old news. (until: 2026-01-01) [source: operator]\n- On leave. (until: 2026-12-01) [source: operator]\n")
    ada.files[f"{ADA}/PROFILE.md"] = profile
    ada.files[f"{ADA}/style.md"] = "---\r\nai_tolerance: averse\r\n---\r\n## Blocklist\r\n- \"circle back\" [source: operator]\r\n"
    ada.files[f"{ADA}/views.md"] = "## Standing objections\n- Asks who maintains it. [source: operator]\n"
    new_entity(ada, "project", "Engine", today=TODAY)
    ada.files["projects/engine/PROFILE.md"] = ada.files["projects/engine/PROFILE.md"].replace("## Norms\n", "## Norms\n- Decisions go in writing. [source: operator]\n")

    brief = compose_brief(ada, ADA, purpose="ask", project="engine", today=TODAY)
    text = brief["text"]
    assert "Lead with the decision. [source: operator]" in text and "Cc everyone." in text
    assert "On leave." in text and "Old news." not in text
    assert brief["ai_tolerance"] == "averse" and "explicit disclosure decision" in brief["disclosure"]
    assert "Asks who maintains it." in text and "Decisions go in writing." in text
    assert "nothing recorded under 'Write to them'" not in brief["gaps"]
    assert "no identities (handles or addresses) recorded" in brief["gaps"]


def test_brief_marks_relational_purposes(ada):
    brief = compose_brief(ada, ADA, purpose="condolence", today=TODAY)
    assert brief["relational"] and "do not draft the text" in brief["text"]
