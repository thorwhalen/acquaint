"""Name matching, handle resolution, the conflation check, and channel precedence."""

import pytest

from acquaint.lookup import check_text, match, reach_channels, resolve_handle
from acquaint.records import dump_yaml

ADA_IDENTITIES = dump_yaml(
    {
        "identities": [
            {"platform": "email", "value": "Ada.Lovelace@example.org", "source": "operator"},
            {"platform": "github", "value": "octocat", "source": "operator"},
            {"platform": "signal", "value": "+10000000000", "source": "operator", "status": "stale"},
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
    assert match(people, "lovel") == {"exact": [], "partial": ["people/ada-lovelace"]}
    assert sorted(match(people, "sam")["exact"]) == ["people/sam-sample", "people/zoe-example"]


@pytest.mark.parametrize("handle", ["email:ada.lovelace@example.org", "ADA.LOVELACE@example.org", "github:octocat", "@octocat"])
def test_resolve_handle_finds_the_identity(people, handle):
    [found] = resolve_handle(people, handle)
    assert found["id"] == "ada-lovelace" and found["evidence"] == "operator"


def test_resolve_handle_respects_platform_and_falls_back_to_names_only_without_one(people):
    assert resolve_handle(people, "discord:octocat") == []
    [by_name] = resolve_handle(people, "Lovelace")
    assert by_name["evidence"] == "name only"


def test_gmail_addresses_ignore_dots_and_plus_tags(store, put):
    address = "ada.l" + "@" + "gmail.com"
    put(store, "people/ada", meta={"name": "Ada"}, files={"identities.yaml": dump_yaml({"identities": [{"platform": "email", "value": address}]})})
    assert resolve_handle(store, "email:adal+news" + "@" + "gmail.com")[0]["id"] == "ada"


def test_check_flags_one_person_written_as_two(people):
    result = check_text(people, "We asked Ada or Lovelace, and Grace Hopper answered.")
    [conflation] = result["conflations"]
    assert conflation["id"] == "ada-lovelace" and conflation["forms"] == ["Ada", "Lovelace"]
    assert "Grace Hopper" in result["unknown_candidates"]


def test_check_accepts_a_full_name_and_reports_shared_forms(people):
    result = check_text(people, "Ada Lovelace met Sam. The Engine ran.")
    assert result["conflations"] == []
    assert {"form": "sam", "ids": ["sam-sample", "zoe-example"]} in result["ambiguous"]
    assert "The Engine" not in result["unknown_candidates"]


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
    assert urgent["channels"][0]["address"] == "signal:+10000000000"

    routine = reach_channels(store, "people/ada-lovelace", defaults_text=defaults, purpose="ask")
    assert [c["channel"] for c in routine["channels"]] == ["github", "discord", "email"]


def test_reach_without_rules_lists_active_identities(people):
    result = reach_channels(people, "people/ada-lovelace")
    assert [c["address"] for c in result["channels"]] == ["email:Ada.Lovelace@example.org", "github:octocat"]
    assert {c["tier"] for c in result["channels"]} == {"none"}
