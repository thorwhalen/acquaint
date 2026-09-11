"""Exact references, handle resolution, the conflation check, channel precedence, and isolation from unreadable records."""

import pytest

from acquaint.lookup import check_text, find_entity, match, reach_channels, resolve_handle
from acquaint.records import dump_yaml
from acquaint.store import AcquaintError, Store

ADA_IDENTITIES = dump_yaml(
    {
        "identities": [
            {"platform": "email", "value": "Ada.Lovelace@example.org", "source": "operator"},
            {"platform": "github", "value": "octocat", "source": "operator"},
            {"platform": "signal", "value": "+10000000000", "source": "operator", "status": "stale"},
            {"platform": "email", "value": "old-job@example.org", "source": "operator", "status": "retracted"},
        ]
    }
)


@pytest.fixture
def people(store, put):
    put(store, "people/ada-lovelace", meta={"name": "Ada Lovelace", "aka": ["Ada", "Lovelace"]}, files={"identities.yaml": ADA_IDENTITIES})
    put(store, "people/zoe-example", meta={"name": "Zoë Example", "aka": ["Sam"]})
    put(store, "people/sam-sample", meta={"name": "Sam Sample", "aka": ["Sam"]})
    return store


def test_match_is_case_punctuation_and_accent_insensitive(people):
    assert match(people, "ADA")["exact"] == ["people/ada-lovelace"]
    assert match(people, "zoe")["exact"] == ["people/zoe-example"]
    assert match(people, "octocat")["exact"] == ["people/ada-lovelace"]
    assert (match(people, "lovel")["exact"], match(people, "lovel")["partial"]) == ([], ["people/ada-lovelace"])
    assert sorted(match(people, "sam")["exact"]) == ["people/sam-sample", "people/zoe-example"]


def test_find_entity_acts_only_on_exact_unique_matches(people, put):
    put(people, "people/joanna-smith", meta={"name": "Joanna Smith"})
    assert find_entity(people, "Joanna") == "people/joanna-smith"
    with pytest.raises(AcquaintError, match="did you mean joanna-smith"):
        find_entity(people, "ann")
    with pytest.raises(AcquaintError, match="could be"):
        find_entity(people, "sam")
    with pytest.raises(AcquaintError, match="exact id"):
        find_entity(people, "Joanna", names=False)
    assert find_entity(people, "joanna-smith", names=False) == "people/joanna-smith"


@pytest.mark.parametrize("handle", ["email:ada.lovelace@example.org", "ADA.LOVELACE@example.org", "github:octocat"])
def test_resolve_handle_finds_the_active_identity(people, handle):
    [found] = resolve_handle(people, handle)["matches"]
    assert found["id"] == "ada-lovelace" and found["evidence"] == "operator"


def test_inactive_identities_are_reported_never_matched(people):
    result = resolve_handle(people, "email:old-job@example.org")
    assert result["matches"] == [] and [row["status"] for row in result["inactive"]] == ["retracted"]


def test_handles_without_a_platform_and_names_are_kept_apart(people):
    assert resolve_handle(people, "discord:octocat")["matches"] == []
    bare = resolve_handle(people, "@octocat")
    assert bare["platform"] is None and [m["platform"] for m in bare["matches"]] == ["github"]
    [by_name] = resolve_handle(people, "Lovelace")["by_name"]
    assert by_name["evidence"] == "name only"


def test_gmail_addresses_ignore_dots_and_plus_tags(store, put):
    address = "ada.l" + "@" + "gmail.com"
    put(store, "people/ada", meta={"name": "Ada"}, files={"identities.yaml": dump_yaml({"identities": [{"platform": "email", "value": address}]})})
    assert resolve_handle(store, "email:adal+news" + "@" + "gmail.com")["matches"][0]["id"] == "ada"


def test_check_flags_one_person_written_as_two(people):
    result = check_text(people, "We asked Ada or Lovelace, and Grace Hopper answered.")
    [conflation] = result["conflations"]
    assert conflation["id"] == "ada-lovelace" and conflation["forms"] == ["Ada", "Lovelace"]
    assert "Grace Hopper" in result["unknown_candidates"]


def test_check_accepts_full_names_and_citation_order_and_reports_shared_forms(people):
    result = check_text(people, "Ada Lovelace met Sam. See Lovelace, Ada (1843). The Engine ran.")
    assert result["conflations"] == []
    assert {"form": "sam", "ids": ["sam-sample", "zoe-example"]} in result["ambiguous"]
    assert "The Engine" not in result["unknown_candidates"]


def test_one_unreadable_record_does_not_break_any_lookup(put):
    class Flaky(dict):
        def __getitem__(self, key):
            if key.startswith("people/broken/"):
                raise OSError("the disk says no")
            return super().__getitem__(key)

    store = Store(files=Flaky())
    put(store, "people/ada-lovelace", meta={"name": "Ada Lovelace", "aka": ["Ada"]}, files={"identities.yaml": ADA_IDENTITIES})
    dict.__setitem__(store.files, "people/broken/PROFILE.md", "---\nname: Broken\n---\n")
    assert match(store, "ada")["exact"] == ["people/ada-lovelace"]
    assert [row["key"] for row in match(store, "ada")["unreadable"]] == ["people/broken"]
    assert check_text(store, "Ada or Lovelace")["mentioned"] == ["ada-lovelace"]
    assert resolve_handle(store, "github:octocat")["matches"][0]["id"] == "ada-lovelace"


def _rules(*rules):
    return dump_yaml({"rules": list(rules)})


def test_reach_precedence_self_over_operator_over_affiliation_over_defaults(store, put):
    put(
        store,
        "people/ada-lovelace",
        meta={"name": "Ada Lovelace"},
        files={
            "identities.yaml": ADA_IDENTITIES,
            "rules.yaml": _rules(
                {"when": {"purpose": "ask"}, "do": {"channel": "github"}, "set_by": "operator", "source": "operator"},
                {"when": {"purpose": "ask", "urgency": "high"}, "do": {"channel": "signal", "fallback": "email"}, "set_by": "self", "source": 'self: "text me if urgent"'},
                {"when": {}, "do": {"channel": "email"}, "set_by": "self", "status": "superseded", "source": "operator"},
            ),
            "links.yaml": dump_yaml({"links": [{"to": "project:engine", "relation": "contributesTo"}]}),
        },
    )
    put(store, "projects/engine", meta={"name": "Engine"}, files={"rules.yaml": _rules({"when": {}, "do": {"channel": "discord"}, "source": "operator"})})
    defaults = _rules({"when": {}, "do": {"channel": "email"}, "source": "operator"})

    urgent = reach_channels(store, "people/ada-lovelace", defaults_text=defaults, purpose="ask", urgency="high")
    assert [(c["channel"], c["tier"]) for c in urgent["channels"]] == [
        ("signal", "self"), ("email", "self"), ("github", "operator"), ("discord", "affiliation"),
    ]
    signal, email = urgent["channels"][0], urgent["channels"][1]
    assert signal["address"] is None and "stale" in signal["note"], "an inactive address is never offered"
    assert email["address"] == "email:Ada.Lovelace@example.org", "the retracted address is skipped"

    routine = reach_channels(store, "people/ada-lovelace", defaults_text=defaults, purpose="ask")
    assert [c["channel"] for c in routine["channels"]] == ["github", "discord", "email"]


def test_reach_without_rules_lists_active_identities_only(people):
    result = reach_channels(people, "people/ada-lovelace")
    assert [c["address"] for c in result["channels"]] == ["email:Ada.Lovelace@example.org", "github:octocat"]
    assert {c["tier"] for c in result["channels"]} == {"none"}
