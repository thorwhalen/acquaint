"""Exact references, handle resolution, the conflation check, channel precedence, and isolation from unreadable records."""

import pytest

from acquaint import tools
from acquaint.brief import compose_brief
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


def test_an_id_and_another_records_alias_compete_on_equal_terms(people, put):
    put(people, "projects/ada", meta={"name": "Ada Project"})
    with pytest.raises(AcquaintError, match="could be"):
        find_entity(people, "ada")
    assert find_entity(people, "project:ada") == "projects/ada"
    assert find_entity(people, "person:ada-lovelace") == "people/ada-lovelace"


def test_ids_are_found_whatever_their_case(store, put):
    put(store, "people/jordan", meta={"name": "Jordan"})
    assert find_entity(store, "Jordan") == find_entity(store, "JORDAN", names=False) == "people/jordan"
    put(store, "people/michael-jordan", meta={"name": "Michael Jordan", "aka": ["Jordan"]})
    with pytest.raises(AcquaintError, match="could be"):
        find_entity(store, "Jordan")


@pytest.mark.parametrize("handle", ["email:ada.lovelace@example.org", "ADA.LOVELACE@example.org", "github:octocat"])
def test_resolve_handle_finds_the_active_identity(people, handle):
    [found] = resolve_handle(people, handle)["matches"]
    assert found["id"] == "ada-lovelace" and found["evidence"] == "operator"


@pytest.mark.parametrize("status", ["retracted", "stale", "former", "unverified", "dead"])
def test_only_usable_identities_are_matches(store, put, status):
    identities = dump_yaml({"identities": [{"platform": "github", "value": "octocat", "source": "operator", "status": status}]})
    put(store, "people/ada", meta={"name": "Ada"}, files={"identities.yaml": identities})
    result = resolve_handle(store, "github:octocat")
    assert result["matches"] == [] and [row["status"] for row in result["inactive"]] == [status]


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
    result = check_text(people, "Ada Lovelace met Sam. See Lovelace, Ada (1843). As Lovelace, Ada wrote. The Engine ran.")
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


def test_reach_without_rules_lists_usable_identities_only(people):
    result = reach_channels(people, "people/ada-lovelace")
    assert [c["address"] for c in result["channels"]] == ["email:Ada.Lovelace@example.org", "github:octocat"]
    assert {c["tier"] for c in result["channels"]} == {"none"}


def test_a_rule_with_a_non_text_channel_is_skipped_with_a_note_not_a_crash(store, put):
    put(store, "orgs/example-org", meta={"name": "Example Org"}, files={"rules.yaml": _rules({"when": {}, "do": {"channel": ["email", "phone"], "fallback": 7}, "source": "operator"})})
    put(store, "people/ada", meta={"name": "Ada"}, files={"identities.yaml": ADA_IDENTITIES, "links.yaml": dump_yaml({"links": [{"to": "org:example-org"}]})})
    result = reach_channels(store, "people/ada")
    [affiliation] = [c for c in result["channels"] if c["tier"] == "affiliation"]
    assert affiliation["channel"] is None and affiliation["address"] is None
    assert "ignored ['email', 'phone']" in affiliation["note"] and "ignored 7" in affiliation["note"]
    assert compose_brief(store, "people/ada")["text"].startswith("# Brief: Ada")


def test_resolve_tool_is_ok_only_for_a_usable_identity_on_a_named_platform(tmp_path):
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    tools.remember("ada-lovelace", "github:octocat", kind="identity", source="operator", data_dir=data)
    assert tools.resolve("github:octocat", data_dir=data)["ok"]
    assert not tools.resolve("@octocat", data_dir=data)["ok"]
    assert not tools.resolve("Ada", data_dir=data)["ok"]


def test_reach_reports_a_matched_rule_whose_channel_has_no_address(tmp_path):
    """Issue #14: a matched rule is a result, not "nothing recorded", and the missing address is named."""
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules({"when": {"urgency": "high"}, "do": {"channel": "pager"}, "set_by": "self", "source": "operator"}),
        encoding="utf-8",
    )
    matched = tools.reach("ada-lovelace", urgency="high", data_dir=data)
    assert (matched["ok"], matched["outcome"]) == (False, "no_address")
    assert "no active identit" not in matched["summary"]
    assert "1 rule(s) matched for ada-lovelace, but no usable address is recorded for pager" in matched["summary"]
    assert 'acquaint remember person:ada-lovelace "pager:<address>" --kind identity' in matched["summary"], "it says what to add"
    assert matched["text"] == "1. pager  [self]  (no pager address recorded)"

    tools.remember("ada-lovelace", "pager:example-rotation", kind="identity", source="operator", data_dir=data)
    reached = tools.reach("ada-lovelace", urgency="high", data_dir=data)
    assert (reached["ok"], reached["outcome"]) == (True, "reachable")
    assert reached["channels"][0]["address"] == "pager:example-rotation" and reached["channels"][0]["note"] is None


def test_reach_does_not_say_nothing_is_recorded_when_rules_exist(tmp_path):
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    rules = tmp_path / "people" / "ada-lovelace" / "rules.yaml"
    cases = {
        "no rules": None,
        "a rule for another context": {"when": {"urgency": "high"}, "do": {"channel": "pager"}, "source": "operator"},
        "a retracted rule": {"when": {}, "do": {"channel": "pager"}, "status": "retracted", "source": "operator"},
        "a matched rule that names no channel": {"when": {}, "do": {}, "source": "operator"},
    }
    for case, rule in cases.items():
        if rule:
            rules.write_text(_rules(rule), encoding="utf-8")
        result = tools.reach("ada-lovelace", data_dir=data)
        assert (result["ok"], result["outcome"]) == (False, "no_channel"), case
        assert result["summary"] == "no matching rule names a channel for ada-lovelace, and no active identity is recorded", case


def test_reach_notes_an_addressless_channel_even_when_another_is_usable(tmp_path):
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    tools.remember("ada-lovelace", "email:ada@example.org", kind="identity", source="operator", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules({"when": {}, "do": {"channel": "pager", "fallback": "email"}, "set_by": "self", "source": "operator"}),
        encoding="utf-8",
    )
    result = tools.reach("ada-lovelace", data_dir=data)
    assert (result["ok"], result["outcome"], result["summary"]) == (True, "reachable", "1 usable channel(s) for ada-lovelace")
    assert result["text"].splitlines() == ["1. pager  [self]  (no pager address recorded)", "2. email → email:ada@example.org  [self]"]


def test_reach_returns_the_address_a_rule_states(tmp_path):
    """Issue #16: a channel addressed by conversation, not by person, gets its address from the rule."""
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    tools.remember("ada-lovelace", "github:ada", kind="identity", source="operator", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules(
            {
                "when": {"project": "heron"},
                "do": {"channel": "github", "address": "github:example/heron"},
                "set_by": "operator",
                "source": "operator",
            }
        ),
        encoding="utf-8",
    )
    stated = tools.reach("ada-lovelace", project="heron", data_dir=data)
    assert (stated["ok"], stated["outcome"]) == (True, "reachable")
    channel = stated["channels"][0]
    assert channel["address"] == "github:example/heron", "the rule's address, not the github:ada handle"
    assert channel["address_kind"] == "stated"
    assert channel["note"] is None

    # Without the rule's context the identity is all there is, and it is marked as derived.
    derived = tools.reach("ada-lovelace", data_dir=data)
    assert derived["channels"][0]["address"] == "github:ada"
    assert derived["channels"][0]["address_kind"] == "identity"


def test_reach_states_an_address_per_fallback_and_needs_no_identity(tmp_path):
    """A fallback states its own address, and a stated address needs no identity on the record."""
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules(
            {
                "when": {},
                "do": {
                    "channel": "github",
                    "address": "github:example/heron",
                    "fallback": [{"channel": "webinbox", "address": "webinbox:heron"}, "email"],
                },
                "set_by": "operator",
                "source": "operator",
            }
        ),
        encoding="utf-8",
    )
    result = tools.reach("ada-lovelace", data_dir=data)
    assert (result["ok"], result["outcome"]) == (True, "reachable")
    assert [(c["channel"], c["address"], c["address_kind"]) for c in result["channels"]] == [
        ("github", "github:example/heron", "stated"),
        ("webinbox", "webinbox:heron", "stated"),
        ("email", None, None),
    ]
    assert result["text"].splitlines()[-1] == "3. email  [operator]  (no email address recorded)"


def test_reach_ignores_a_fallback_entry_with_no_channel(tmp_path):
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    tools.remember("ada-lovelace", "email:ada@example.org", kind="identity", source="operator", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules(
            {
                "when": {},
                "do": {"channel": "email", "fallback": [{"address": "github:example/heron"}]},
                "set_by": "operator",
                "source": "operator",
            }
        ),
        encoding="utf-8",
    )
    result = tools.reach("ada-lovelace", data_dir=data)
    assert [c["channel"] for c in result["channels"]] == ["email"]
    assert "ignored" in result["channels"][0]["note"], "the entry is named, not dropped in silence"


def _stated_rule(when, address=None, **extra):
    rule = {"when": when, "do": {"channel": "github", **({"address": address} if address else {})}, "set_by": "operator", "source": "operator"}
    rule["do"].update(extra)
    return rule


def test_reach_answers_with_the_project_that_was_asked_about(tmp_path):
    """A project named in the call is consulted before the person's other affiliations, which share its tier."""
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    for slug in ("ibis", "heron"):
        tools.new("project", slug.title(), data_dir=data)
        (tmp_path / "projects" / slug / "rules.yaml").write_text(
            _rules(_stated_rule({}, f"github:example/{slug}")), encoding="utf-8"
        )
    (tmp_path / "people" / "ada-lovelace" / "links.yaml").write_text(
        dump_yaml({"links": [{"to": "project:ibis", "role": "author", "source": "operator"}]}), encoding="utf-8"
    )
    result = tools.reach("ada-lovelace", project="heron", data_dir=data)
    assert result["channels"][0]["address"] == "github:example/heron", "not the ibis link's address"


def test_reach_takes_the_address_from_the_best_rule_that_states_one(tmp_path):
    """A broad rule naming a channel says nothing about where it goes, so it must not bury a stated address."""
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    tools.remember("ada-lovelace", "github:ada", kind="identity", source="operator", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules(
            {"when": {}, "do": {"channel": "github"}, "set_by": "self", "source": "operator"},
            _stated_rule({"project": "heron"}, "github:example/heron"),
        ),
        encoding="utf-8",
    )
    result = tools.reach("ada-lovelace", project="heron", data_dir=data)
    assert (result["ok"], result["outcome"]) == (True, "reachable")
    channel = result["channels"][0]
    assert channel["address"] == "github:example/heron", "the self rule wins the channel, not the address"
    assert channel["address_kind"] == "stated"
    assert channel["tier"] == "self", "the channel's place still comes from the best-placed rule naming it"
    assert channel["note"].startswith("address stated by the rule for {'project': 'heron'} in people/ada-lovelace/rules.yaml"), "the note names the rule and the file the address came from"


def test_reach_is_reachable_when_only_a_lower_rule_states_the_address(tmp_path):
    """The same shape with no identity recorded: a stated address makes it reachable, not exit 3."""
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules(
            {"when": {}, "do": {"channel": "github"}, "set_by": "self", "source": "operator"},
            _stated_rule({"project": "heron"}, "github:example/heron"),
        ),
        encoding="utf-8",
    )
    result = tools.reach("ada-lovelace", project="heron", data_dir=data)
    assert (result["ok"], result["outcome"]) == (True, "reachable")
    assert result["channels"][0]["address"] == "github:example/heron"


def test_reach_offers_both_remedies_when_nothing_gives_an_address(tmp_path):
    """Exit 3 must not push a conversation reference into identities.yaml."""
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules(_stated_rule({})), encoding="utf-8"
    )
    result = tools.reach("ada-lovelace", data_dir=data)
    assert (result["ok"], result["outcome"]) == (False, "no_address")
    assert "--kind identity" in result["summary"], "record an identity"
    assert "do: {channel: github, address: <reference>}" in result["summary"], "or state it on the rule"


def test_reach_keeps_an_instruction_and_a_channel_of_the_same_name_apart(tmp_path):
    """A free-text `do` must not collide with a rule naming that channel."""
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules(
            {"when": {}, "do": "github", "set_by": "self", "source": "operator"},
            _stated_rule({"project": "heron"}, "github:example/heron"),
        ),
        encoding="utf-8",
    )
    result = tools.reach("ada-lovelace", project="heron", data_dir=data)
    assert len(result["channels"]) == 2, "the instruction and the channel are two entries"
    assert result["channels"][0]["instruction"] == "github" and result["channels"][0]["channel"] is None
    assert result["channels"][1]["address"] == "github:example/heron"


def test_reach_will_not_read_a_mapping_as_a_channel_name(tmp_path):
    """`do.channel` is a name; an address goes in `address`. A mapping there is reported, not parsed."""
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules({"when": {}, "do": {"channel": {"channel": "github", "address": "github:example/heron"}}, "source": "operator"}),
        encoding="utf-8",
    )
    result = tools.reach("ada-lovelace", data_dir=data)
    assert [c["channel"] for c in result["channels"]] == [None]
    assert "ignored" in result["channels"][0]["note"]
    assert result["channels"][0]["address"] is None and result["channels"][0]["address_kind"] is None
    assert (result["ok"], result["outcome"]) == (False, "no_channel"), "not reachable through a malformed rule"
    assert result["text"].startswith("1. (no channel named)"), "its repr does not stand in for a channel"


def test_reach_does_not_offer_an_address_that_names_no_channel(tmp_path):
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules({"when": {}, "do": {"address": "github:example/heron"}, "source": "operator"}),
        encoding="utf-8",
    )
    result = tools.reach("ada-lovelace", data_dir=data)
    assert (result["ok"], result["outcome"]) == (False, "no_channel")
    assert "{'address'" not in result["text"], "no repr masquerading as a usable channel"


def test_brief_says_when_an_address_came_from_the_identities(tmp_path):
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    tools.remember("ada-lovelace", "github:ada", kind="identity", source="operator", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules(_stated_rule({"project": "heron"}, "github:example/heron"), _stated_rule({})),
        encoding="utf-8",
    )
    stated = tools.brief("ada-lovelace", project="heron", data_dir=data)["text"]
    assert "→ github:example/heron (" in stated and "from their identities" not in stated
    derived = tools.brief("ada-lovelace", data_dir=data)["text"]
    assert "→ github:ada (from their identities)" in derived


def test_one_broken_rule_does_not_hide_the_addresses_that_work(tmp_path):
    """A rule too malformed to name a channel is reported; it does not take the identities down with it."""
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    for handle in ("email:ada@example.org", "github:ada"):
        tools.remember("ada-lovelace", handle, kind="identity", source="operator", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules({"when": {}, "do": {"channel": 42}, "source": "operator"}), encoding="utf-8"
    )
    result = tools.reach("ada-lovelace", data_dir=data)
    assert (result["ok"], result["outcome"]) == (True, "reachable"), "an active identity is recorded"
    assert [c["address"] for c in result["channels"] if c["channel"]] == ["email:ada@example.org", "github:ada"]
    assert "ignored 42" in result["text"], "and the broken rule is still reported"
    reach_section = tools.brief("ada-lovelace", data_dir=data)["text"]
    assert "1. (no channel named) (" in reach_section, "brief names the broken rule's entry, not `None`"
    assert "→ email:ada@example.org (from their identities)" in reach_section
    assert "no rule matched; usable identities in the order listed" in reach_section, "and says why they are there"


def test_reach_will_not_answer_with_another_projects_address(tmp_path):
    """An affiliation's stated address is that affiliation's. Asking about one project must not return another's."""
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    tools.remember("ada-lovelace", "github:ada", kind="identity", source="operator", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules({"when": {}, "do": {"channel": "github"}, "set_by": "self", "source": "operator"}), encoding="utf-8"
    )
    tools.new("project", "Ibis", data_dir=data)
    (tmp_path / "projects" / "ibis" / "rules.yaml").write_text(_rules(_stated_rule({}, "github:example/ibis")), encoding="utf-8")
    (tmp_path / "people" / "ada-lovelace" / "links.yaml").write_text(
        dump_yaml({"links": [{"to": "project:ibis", "role": "author", "source": "operator"}]}), encoding="utf-8"
    )
    tools.new("project", "Heron", data_dir=data)

    asked_about_heron = tools.reach("ada-lovelace", project="heron", data_dir=data)
    assert asked_about_heron["channels"][0]["address"] == "github:ada", "the handle, not the Ibis repository"
    assert asked_about_heron["channels"][0]["address_kind"] == "identity"

    # Ibis's own address is still Ibis's, when Ibis is what was asked about.
    asked_about_ibis = tools.reach("ada-lovelace", project="ibis", data_dir=data)
    assert asked_about_ibis["channels"][0]["address"] == "github:example/ibis"


def test_reach_says_when_two_rules_state_different_addresses(tmp_path):
    """Precedence decides, but it must not decide in silence."""
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules(
            {"id": "urgent", "when": {"urgency": "high"}, "do": {"channel": "github", "address": "github:example/urgent"}, "set_by": "self", "source": "operator"},
            {"id": "heron", "when": {"project": "heron"}, "do": {"channel": "github", "address": "github:example/heron"}, "set_by": "self", "source": "operator"},
        ),
        encoding="utf-8",
    )
    result = tools.reach("ada-lovelace", urgency="high", project="heron", data_dir=data)
    channel = result["channels"][0]
    assert channel["address"] == "github:example/urgent", "first among equals, by file order"
    assert "another rule states a different address" in channel["note"]


def test_two_rules_broken_the_same_way_are_two_things_to_fix(tmp_path):
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    tools.new("project", "Heron", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "links.yaml").write_text(
        dump_yaml({"links": [{"to": "project:heron", "role": "author", "source": "operator"}]}), encoding="utf-8"
    )
    broken = _rules({"when": {}, "do": {"channel": 42}, "source": "operator"})
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(broken, encoding="utf-8")
    (tmp_path / "projects" / "heron" / "rules.yaml").write_text(broken, encoding="utf-8")
    result = tools.reach("ada-lovelace", data_dir=data)
    assert [c["rule_from"] for c in result["channels"]] == [
        "people/ada-lovelace/rules.yaml",
        "projects/heron/rules.yaml",
    ], "both are listed, not collapsed by an identical note"
    assert (result["ok"], result["outcome"]) == (False, "no_channel")
    assert result["summary"].count("ignored 42") == 2, "the summary names every one of them"


def test_a_stated_address_is_stripped(tmp_path):
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    (tmp_path / "people" / "ada-lovelace" / "rules.yaml").write_text(
        _rules(_stated_rule({}, "  github:example/heron  ")), encoding="utf-8"
    )
    assert tools.reach("ada-lovelace", data_dir=data)["channels"][0]["address"] == "github:example/heron"


def test_no_channel_named_is_importable():
    """A consumer detecting the case needs the literal it compares against."""
    from acquaint.lookup import NO_CHANNEL_NAMED
    from acquaint.lookup import __all__ as lookup_all

    assert "NO_CHANNEL_NAMED" in lookup_all and NO_CHANNEL_NAMED


def test_reach_prefers_the_named_projects_channel_choice(tmp_path):
    """Ordering, not just addresses: every affiliation shares one tier, so the project asked about goes first."""
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    for handle in ("email:ada@example.org", "github:ada"):
        tools.remember("ada-lovelace", handle, kind="identity", source="operator", data_dir=data)
    for slug, channel in (("ibis", "email"), ("heron", "github")):
        tools.new("project", slug.title(), data_dir=data)
        (tmp_path / "projects" / slug / "rules.yaml").write_text(
            _rules({"when": {}, "do": {"channel": channel}, "source": "operator"}), encoding="utf-8"
        )
    (tmp_path / "people" / "ada-lovelace" / "links.yaml").write_text(
        dump_yaml({"links": [{"to": "project:ibis", "role": "author", "source": "operator"}]}), encoding="utf-8"
    )
    assert tools.reach("ada-lovelace", project="heron", data_dir=data)["channels"][0]["channel"] == "github"
    assert tools.reach("ada-lovelace", project="ibis", data_dir=data)["channels"][0]["channel"] == "email"
