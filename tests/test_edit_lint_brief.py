"""Creating, remembering, renaming and forgetting; the provenance lint; and the brief."""

import pytest

from acquaint.brief import compose_brief
from acquaint.edit import append_observation, forget_entity, new_entity, rename_entity
from acquaint.lint import lint_store
from acquaint.records import dump_yaml
from acquaint.store import AcquaintError

TODAY = "2026-09-11"


@pytest.fixture
def ada(store):
    new_entity(store, "person", "Ada Lovelace", today=TODAY)
    return store


def _add_to_profile(store, key, text):
    store.files[f"{key}/PROFILE.md"] += text


# --------------------------------------------------------------------------- new


def test_new_person_scaffolds_profile_and_policy(ada):
    entity = ada["people/ada-lovelace"]
    assert entity.meta["aka"] == ["Ada", "Lovelace"] and entity.meta["review_due"] > TODAY
    assert list(entity.sections)[:4] == ["Who", "Reach", "Write to them", "Read them"]
    assert "POLICY.md" in ada.files
    assert lint_store(ada, today=TODAY)["errors"] == []


def test_new_refuses_a_duplicate_and_suggests_a_qualifier(ada):
    with pytest.raises(AcquaintError, match="qualifier"):
        new_entity(ada, "person", "Ada Lovelace", today=TODAY)
    assert new_entity(ada, "person", "Ada Lovelace", qualifier="example-org", today=TODAY)["id"] == "ada-lovelace--example-org"


def test_new_accepts_open_kinds_with_the_ledger_template(store):
    result = new_entity(store, "community", "Example Circle", today=TODAY)
    assert result["key"] == "communities/example-circle"
    assert "Norms" in store["communities/example-circle"].sections


# ---------------------------------------------------------------------- remember


def test_remember_appends_numbered_sourced_entries(ada):
    first = append_observation(ada, "ada-lovelace", "prefers email for attachments", source="https://example.org/thread/1", today=TODAY)
    second = append_observation(ada, "ada-lovelace", "replied within the hour", source="log/2026-09.md#e01", today=TODAY)
    assert (first["ref"], second["ref"]) == ("log/2026-09.md#e01", "log/2026-09.md#e02")
    assert ada["people/ada-lovelace"]["log/2026-09.md"].count("## e0") == 2
    assert "PROFILE.md" in ada["people/ada-lovelace"], "the hot path never rewrites the entry file"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"kind": "preference"}, "needs its source"),
        ({"kind": "preference", "source": "2026-09-11"}, "a date alone is not a source"),
        ({"kind": "gossip", "source": "operator"}, "kind must be one of"),
    ],
)
def test_remember_refuses_what_lint_would_fail(ada, kwargs, message):
    with pytest.raises(AcquaintError, match=message):
        append_observation(ada, "ada-lovelace", "likes short emails", today=TODAY, **kwargs)


def test_remember_identity_and_policy_warnings(ada):
    address = "ada" + "@" + "example.org"
    append_observation(ada, "ada-lovelace", f"email:{address}", kind="identity", source='self: "write to me there"', today=TODAY)
    assert ada["people/ada-lovelace"].identities[0]["value"] == address
    result = append_observation(ada, "ada-lovelace", "mentioned a new medication", source="operator", today=TODAY)
    assert any("special-category" in w for w in result["warnings"])
    unsourced = append_observation(ada, "ada-lovelace", "seemed busy", today=TODAY)
    assert any("without a source" in w for w in unsourced["warnings"])


# -------------------------------------------------------------------------- lint


def _rules(lint):
    return sorted((f["file"], f["rule"]) for f in lint["errors"])


def test_lint_fails_unsourced_and_date_only_preferences(ada):
    _add_to_profile(ada, "people/ada-lovelace", "\n## Write to them\n- Keep it short.\n- Lead with the ask. [source: 2026-09-01]\n- One question. [source: operator]\n")
    result = lint_store(ada, "people/ada-lovelace", today=TODAY)
    messages = [f["message"] for f in result["errors"]]
    assert len(result["errors"]) == 2
    assert any("no [source: …] tag" in m for m in messages) and any("a date alone is not a source" in m for m in messages)
    assert all(f["line"] for f in result["errors"])


def test_lint_scope_card_files_logs_rules_and_broken_yaml(ada):
    key = "people/ada-lovelace"
    _add_to_profile(ada, key, "\n## More\n- anything goes here\n")
    ada.files[f"{key}/style.md"] = "## Do\n- Plain words. [source: operator]\n- Short sentences.\n"
    ada.files[f"{key}/log/2026-08.md"] = "## e01 · 2026-08-02 · preference\nlikes calls\n- source: none given\n"
    ada.files[f"{key}/rules.yaml"] = dump_yaml({"rules": [{"when": {"urgency": "high"}, "do": {"channel": "signal"}}]})
    ada.files["people/other/PROFILE.md"] = "---\nname: [unclosed\n---\n"
    result = lint_store(ada, today=TODAY)
    assert _rules(result) == [
        ("PROFILE.md", "unparseable"),
        ("log/2026-08.md#e01", "unsourced"),
        ("rules.yaml", "unsourced"),
        ("style.md", "unsourced"),
    ]
    assert result["checked"] == 2


def test_lint_warns_on_expired_now_and_policy_tripwires(ada):
    _add_to_profile(ada, "people/ada-lovelace", "\n## Now\n- Travelling. (until: 2026-01-01) [source: operator]\n- Mentioned their therapy sessions. (until: 2027-01-01) [source: operator]\n")
    rules = {f["rule"] for f in lint_store(ada, "people/ada-lovelace", today=TODAY)["warnings"]}
    assert {"now-expired", "special-category"} <= rules


# ---------------------------------------------------------------- rename, forget


def test_rename_relinks_other_records_and_keeps_the_old_forms(ada):
    new_entity(ada, "project", "Analytical Engine", today=TODAY)
    ada.files["people/ada-lovelace/links.yaml"] = dump_yaml({"links": [{"to": "project:analytical-engine", "relation": "contributesTo"}]})
    ada.files["people/ada-lovelace/log/2026-09.md"] = "## e01 · 2026-09-11 · observation\nworks on project:analytical-engine\n- source: operator\n"
    result = rename_entity(ada, "project:analytical-engine", "engine", today=TODAY)
    assert result["to"] == "projects/engine"
    assert ada["people/ada-lovelace"].links[0]["to"] == "project:engine"
    assert "project:analytical-engine" in ada["people/ada-lovelace"]["log/2026-09.md"], "history is not rewritten"
    assert "analytical-engine" in ada["projects/engine"].aka


def test_forget_is_a_dry_run_until_confirmed_then_tombstones(ada):
    plan = forget_entity(ada, "ada-lovelace", today=TODAY)
    assert plan["done"] is False and "people/ada-lovelace" in ada
    done = forget_entity(ada, "ada-lovelace", confirm=True, today=TODAY)
    assert done["done"] and "people/ada-lovelace" not in ada
    assert "Lovelace" not in ada.files["_tombstones.yaml"], "the tombstone holds hashes, not names"
    with pytest.raises(AcquaintError, match="forgotten"):
        new_entity(ada, "person", "Ada Lovelace", today=TODAY)
    assert new_entity(ada, "person", "Ada", today=TODAY)["id"] == "ada", "a bare name part is not tombstoned"
    assert new_entity(ada, "person", "Ada Lovelace", force=True, today=TODAY)["id"] == "ada-lovelace"


# ------------------------------------------------------------------------- brief


def test_brief_assembles_card_style_views_norms_and_gaps(ada):
    key = "people/ada-lovelace"
    _add_to_profile(ada, key, "")
    profile = ada.files[f"{key}/PROFILE.md"].replace(
        "## Write to them\n", "## Write to them\n- Lead with the decision. [source: operator]\n"
    ).replace("## Now\n", "## Now\n- Old news. (until: 2026-01-01) [source: operator]\n- On leave. (until: 2026-12-01) [source: operator]\n")
    ada.files[f"{key}/PROFILE.md"] = profile
    ada.files[f"{key}/style.md"] = "---\nai_tolerance: averse\n---\n## Blocklist\n- \"circle back\" [source: operator]\n"
    ada.files[f"{key}/views.md"] = "## Standing objections\n- Asks who maintains it. [source: operator]\n"
    new_entity(ada, "project", "Engine", today=TODAY)
    ada.files["projects/engine/PROFILE.md"] = ada.files["projects/engine/PROFILE.md"].replace("## Norms\n", "## Norms\n- Decisions go in writing. [source: operator]\n")

    brief = compose_brief(ada, key, purpose="ask", project="engine", today=TODAY)
    text = brief["text"]
    assert "Lead with the decision. [source: operator]" in text
    assert "On leave." in text and "Old news." not in text
    assert brief["ai_tolerance"] == "averse" and "explicit disclosure decision" in brief["disclosure"]
    assert "Asks who maintains it." in text and "Decisions go in writing." in text
    assert "nothing recorded under 'Write to them'" not in brief["gaps"]
    assert "no identities (handles or addresses) recorded" in brief["gaps"]


def test_brief_marks_relational_purposes(ada):
    brief = compose_brief(ada, "people/ada-lovelace", purpose="condolence", today=TODAY)
    assert brief["relational"] and "do not draft the text" in brief["text"]
