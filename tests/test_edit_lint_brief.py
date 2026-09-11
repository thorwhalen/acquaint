"""Creating, remembering, renaming and forgetting; the provenance lint; and the brief."""

import hashlib
import os
import sys

import pytest

from acquaint import tools
from acquaint.brief import compose_brief
from acquaint.edit import append_observation, forget_entity, new_entity, rename_entity
from acquaint.lint import lint_store
from acquaint.lookup import normalize
from acquaint.records import dump_yaml, load_yaml, parse_log
from acquaint.store import AcquaintError, Store

TODAY = "2026-09-11"
ADA = "people/ada-lovelace"
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")


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


def _identities(store):
    return load_yaml(store.files[f"{ADA}/identities.yaml"])[0]["identities"]


def _mark_first_identity(store, status):
    data = load_yaml(store.files[f"{ADA}/identities.yaml"])[0]
    data["identities"][0]["status"] = status
    store.files[f"{ADA}/identities.yaml"] = dump_yaml(data)


@pytest.mark.parametrize("status", ["stale", "retracted", "former"])
def test_remember_refuses_an_identity_equal_to_an_inactive_one_and_writes_nothing(ada, status):
    """Issue #17: this used to log "recorded identity" and leave the entry inactive."""
    append_observation(ada, "ada-lovelace", "pager:example-rotation", kind="identity", source="operator", today=TODAY)
    _mark_first_identity(ada, status)
    before = dict(ada.files)
    with pytest.raises(AcquaintError) as refused:
        append_observation(ada, "ada-lovelace", "pager:example-rotation", kind="identity", source="https://example.org/roster", today=TODAY)
    message = str(refused.value)
    assert f"pager:example-rotation is already recorded for person:ada-lovelace as {status}" in message
    assert "source: operator" in message and "people/ada-lovelace/identities.yaml" in message
    assert message.endswith(
        "run: acquaint remember person:ada-lovelace pager:example-rotation --kind identity --source https://example.org/roster --reactivate"
    )
    assert dict(ada.files) == before, "nothing was written"


def test_remember_reactivate_makes_an_inactive_identity_active_with_the_new_source(ada):
    append_observation(ada, "ada-lovelace", "pager:example-rotation", kind="identity", source="operator", today=TODAY)
    _mark_first_identity(ada, "stale")
    result = append_observation(
        ada, "ada-lovelace", "pager:example-rotation", kind="identity", source="https://example.org/roster", reactivate=True, today=TODAY
    )
    assert result["identity"] == {"handle": "pager:example-rotation", "change": "reactivated", "previous_status": "stale"}
    [entry] = _identities(ada)
    assert (entry["status"], entry["source"], entry["previous_status"], entry["previous_source"], entry["reactivated"]) == (
        "active", "https://example.org/roster", "stale", "operator", TODAY
    )
    assert parse_log(ada.files[f"{ADA}/log/2026-09.md"])[-1]["id"] == result["entry"] == "e02"


def test_remember_reactivate_needs_a_source_and_an_identity(ada):
    append_observation(ada, "ada-lovelace", "pager:example-rotation", kind="identity", source="operator", today=TODAY)
    _mark_first_identity(ada, "stale")
    before = dict(ada.files)
    with pytest.raises(AcquaintError, match="needs --source"):
        append_observation(ada, "ada-lovelace", "pager:example-rotation", kind="identity", reactivate=True, today=TODAY)
    with pytest.raises(AcquaintError, match="--reactivate applies to --kind identity only"):
        append_observation(ada, "ada-lovelace", "likes short emails", source="operator", reactivate=True, today=TODAY)
    assert dict(ada.files) == before


def test_remember_an_identity_that_is_already_active_changes_only_the_log(ada):
    append_observation(ada, "ada-lovelace", "pager:example-rotation", kind="identity", source="operator", today=TODAY)
    identities = ada.files[f"{ADA}/identities.yaml"]
    result = append_observation(ada, "ada-lovelace", "pager:example-rotation", kind="identity", source="https://example.org/roster", today=TODAY)
    assert (result["identity"]["change"], result["entry"]) == ("already_active", "e02")
    assert ada.files[f"{ADA}/identities.yaml"] == identities


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
        "## Don't\n- Topics to avoid. [source: operator]\n  - Never mention their family.\n",
        "   ## Don't\n- Cc everyone.\n",
    ],
)
def test_lint_catches_every_way_of_writing_an_unsourced_line(ada, snippet):
    _add_to_profile(ada, ADA, "\n" + snippet)
    assert [f["rule"] for f in lint_store(ada, ADA, today=TODAY)["errors"]] == ["unsourced"]


def test_lint_accepts_wrapped_lines_and_sourced_nested_bullets_and_ignores_code(ada):
    _add_to_profile(
        ada,
        ADA,
        "\n## Write to them\n- Lead with the decision,\n  then the options. [source: operator]\n  - e.g. the export email [source: log/2026-09.md#e01]\n"
        "```text\n~~~\n- a code sample, not a preference\n```\n",
    )
    assert lint_store(ada, ADA, today=TODAY)["errors"] == []


def test_lint_and_brief_agree_that_a_top_level_heading_ends_a_section(ada):
    _add_to_profile(ada, ADA, "\n## Write to them\n- Short. [source: operator]\n# Important\n- Never cc their manager.\n")
    assert lint_store(ada, ADA, today=TODAY)["errors"] == []
    assert "Never cc their manager." not in compose_brief(ada, ADA, today=TODAY)["text"]


def test_lint_scope_card_files_logs_rules_and_broken_yaml(ada):
    _add_to_profile(ada, ADA, "\n## More\n- anything goes here\n")
    ada.files[f"{ADA}/style.md"] = "## Do\n- Plain words. [source: operator]\n- Short sentences.\n"
    ada.files[f"{ADA}/log/2026-08.md"] = "## e01 · 2026-08-02 · preference\nlikes calls\n- source: none given\n"
    ada.files[f"{ADA}/rules.yaml"] = dump_yaml({"rules": [{"when": {"urgency": "high"}, "do": {"channel": ["signal", "email"]}}]})
    ada.files["people/other/PROFILE.md"] = "---\nname: [unclosed\n---\n"
    result = lint_store(ada, today=TODAY)
    assert _error_rules(result) == [
        ("PROFILE.md", "unparseable"),
        ("log/2026-08.md#e01", "unsourced"),
        ("rules.yaml", "bad-channel"),
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


def test_lint_checks_links_without_searching_the_store_per_link(store, monkeypatch):
    for n in range(12):
        new_entity(store, "person", f"Member {n}", today=TODAY)
        store.files[f"people/member-{n}/links.yaml"] = dump_yaml({"links": [{"to": f"member-{(n + 1) % 12}"}, {"to": "org:missing"}]})

    def refuse(*args, **kwargs):
        raise AssertionError("lint must not call Store.find for each link")

    monkeypatch.setattr(Store, "find", refuse)
    warnings = lint_store(store, today=TODAY)["warnings"]
    assert [w["rule"] for w in warnings].count("unknown-link") == 12


def test_a_broken_tombstone_file_stops_new_and_forget_and_lint_reports_it(ada):
    ada.files["_tombstones.yaml"] = "salt: [oops\n"
    with pytest.raises(AcquaintError, match="does not parse"):
        new_entity(ada, "person", "Grace Example", today=TODAY)
    with pytest.raises(AcquaintError, match="does not parse"):
        forget_entity(ada, "ada-lovelace", confirm=True, today=TODAY)
    assert ("_tombstones.yaml", "unparseable") in _error_rules(lint_store(ada, today=TODAY))

    ada.files["_tombstones.yaml"] = "tombstones:\n- kind: person\n  hashes: [abc]\n"
    with pytest.raises(AcquaintError, match="no salt"):
        new_entity(ada, "person", "Grace Example", today=TODAY)
    assert ADA in ada, "nothing was forgotten"


def test_lint_on_a_data_dir_that_does_not_exist_is_not_ok(tmp_path):
    result = tools.lint(data_dir=str(tmp_path / "typo"))
    assert result["ok"] is False and "no store" in result["summary"]
    assert not (tmp_path / "typo").exists()


# ---------------------------------------------------------------- rename, forget


def test_rename_relinks_other_records_but_not_urls_logs_or_aliases(ada):
    new_entity(ada, "project", "Analytical Engine", today=TODAY)
    ada.files["projects/analytical-engine/PROFILE.md"] = ada.files["projects/analytical-engine/PROFILE.md"].replace("aka: []", "aka: Countess")
    ada.files[f"{ADA}/links.yaml"] = dump_yaml({"links": [{"to": "project:analytical-engine", "relation": "contributesTo"}]})
    ada.files[f"{ADA}/rules.yaml"] = (
        "rules:\n- when: {project: analytical-engine}  # the engine work\n  do: {channel: email}\n  source: operator\n"
        "- when: {project: [analytical-engine, other]}\n  do: {channel: email}\n  source: operator\n"
        "- when:\n    project:\n    - other\n    - analytical-engine\n  do: {channel: email}\n  source: operator\n"
    )
    url = "https://tracker.example.org/projects/analytical-engine/issues/42?ref=project:analytical-engine"
    ada.files[f"{ADA}/sources.md"] = f"## Corpus\n- Tracker {url}, see project:analytical-engine [source: operator]\n- Earlier: {url}\nprojects:analytical-engine on the next line [source: operator]\n"
    ada.files[f"{ADA}/log/2026-09.md"] = "## e01 · 2026-09-11 · observation\nworks on project:analytical-engine\n- source: operator\n"

    result = rename_entity(ada, "project:analytical-engine", "engine", today=TODAY)
    assert result["to"] == "projects/engine"
    entity = ada[ADA]
    assert entity.links[0]["to"] == "project:engine"
    assert [rule["when"]["project"] for rule in entity.rules] == ["engine", ["engine", "other"], ["other", "engine"]]
    assert f"{ADA}/rules.yaml" in result["yaml_comments_dropped"]
    sources = ada.files[f"{ADA}/sources.md"]
    assert sources.count(url) == 2 and "see project:engine [source" in sources and "projects:engine on the next line" in sources
    assert "project:analytical-engine" in ada.files[f"{ADA}/log/2026-09.md"], "history is not rewritten"
    assert ada["projects/engine"].aka == ["Countess", "analytical-engine"]


def test_renaming_a_person_follows_the_plural_reference_form_too(ada):
    new_entity(ada, "person", "Grace Example", today=TODAY)
    ada.files["people/grace-example/links.yaml"] = dump_yaml({"links": [{"to": "people:ada-lovelace"}, {"to": "person:ada-lovelace"}]})
    rename_entity(ada, "ada-lovelace", "ada-king", today=TODAY)
    assert [link["to"] for link in ada["people/grace-example"].links] == ["people:ada-king", "person:ada-king"]


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
    home = tmp_path / "home"
    assert not home.exists() or not list(home.rglob("*")), "nothing moved to a trash folder"


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


def test_forget_reports_the_records_that_still_mention_the_person(ada):
    new_entity(ada, "person", "Grace Example", today=TODAY)
    ada.files["people/grace-example/links.yaml"] = dump_yaml({"links": [{"to": "person:ada-lovelace"}]})
    ada.files["people/grace-example/log/2026-09.md"] = "## e01 · 2026-09-11 · observation\nhad lunch with Ada Lovelace\n- source: operator\n"
    plan = forget_entity(ada, "ada-lovelace", today=TODAY)
    mentions = {ref["file"]: ref["mentions"] for ref in plan["references"]}
    assert set(mentions) == {"people/grace-example/links.yaml", "people/grace-example/log/2026-09.md"}
    assert "person:ada-lovelace" in mentions["people/grace-example/links.yaml"]
    assert "Ada Lovelace" in mentions["people/grace-example/log/2026-09.md"]
    done = forget_entity(ada, "ada-lovelace", confirm=True, today=TODAY)
    assert done["done"] and done["references"] == plan["references"], "the other records are reported, not edited"
    assert "had lunch with Ada Lovelace" in ada.files["people/grace-example/log/2026-09.md"]


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


@posix_only
def test_forget_refuses_a_linked_folder_before_writing_anything(tmp_path):
    outside = tmp_path / "outside" / "ada"
    outside.mkdir(parents=True)
    (outside / "PROFILE.md").write_text("---\nname: Ada\n---\n")
    (tmp_path / "data" / "people").mkdir(parents=True)
    os.symlink(outside, tmp_path / "data" / "people" / "ada")
    store = Store(tmp_path / "data")
    with pytest.raises(AcquaintError, match="is a link"):
        forget_entity(store, "people/ada", confirm=True, today=TODAY)
    assert not (tmp_path / "data" / "_tombstones.yaml").exists() and (outside / "PROFILE.md").is_file()


# ------------------------------------------------------------------------- brief


def test_brief_assembles_card_style_views_norms_and_gaps(ada):
    profile = ada.files[f"{ADA}/PROFILE.md"]
    profile = profile.replace("## Write to them\n", "## Write to them\n- Lead with the decision. [source: operator]\n")
    profile = profile.replace("## Don't\n", "## Don’t:\n- Cc everyone. [source: operator]\n")
    profile = profile.replace(
        "## Now\n",
        "## Now\n- Travelling for a long stretch\n  and offline. (until: 2026-01-01) [source: operator]\n- On leave. (until: 2026-12-01) [source: operator]\n",
    )
    ada.files[f"{ADA}/PROFILE.md"] = profile
    ada.files[f"{ADA}/style.md"] = "---\r\nai_tolerance: averse\r\n---\r\n## Blocklist\r\n- \"circle back\" [source: operator]\r\n"
    ada.files[f"{ADA}/views.md"] = "## Standing objections\n- Asks who maintains it. [source: operator]\n"
    new_entity(ada, "project", "Engine", today=TODAY)
    ada.files["projects/engine/PROFILE.md"] = ada.files["projects/engine/PROFILE.md"].replace("## Norms\n", "## Norms\n- Decisions go in writing. [source: operator]\n")

    brief = compose_brief(ada, ADA, purpose="ask", project="engine", today=TODAY)
    text = brief["text"]
    assert "Lead with the decision. [source: operator]" in text and "Cc everyone." in text
    assert "On leave." in text and "Travelling" not in text and "and offline" not in text
    assert brief["ai_tolerance"] == "averse" and "explicit disclosure decision" in brief["disclosure"]
    assert "Asks who maintains it." in text and "Decisions go in writing." in text
    assert "nothing recorded under 'Write to them'" not in brief["gaps"]
    assert "no identities (handles or addresses) recorded" in brief["gaps"]


def test_brief_marks_relational_purposes(ada):
    brief = compose_brief(ada, ADA, purpose="condolence", today=TODAY)
    assert brief["relational"] and "do not draft the text" in brief["text"]
