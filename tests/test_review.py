"""The review list: everything the store says about one person's disclosure standing, and the warning when an affiliation ends under a permissive tier.

Built on the A1 fixture store (``test_disclosure_schema.build``). Every person, project and
organisation here is invented.
"""

import json
from datetime import date

import pytest

from acquaint import tools
from acquaint.lint import lint_store
from acquaint.records import dump_yaml
from acquaint.review import review_person
from acquaint.store import AcquaintError, Store
from test_disclosure_schema import ADA, BRAM, HERON, TODAY, _days, _set, _tier, _trust, build

BRAM_RULES = [
    {"when": {"purpose": "ask"}, "do": {"channel": "email"}, "set_by": "operator", "source": "operator"},
    {"when": {"urgency": "high"}, "do": {"channel": "phone"}, "set_by": "self", "source": 'self: "call me if it is urgent"'},
]
ENDED = "affiliation-ended"


def _fixture(store, put, today=TODAY):
    build(store, put, today=today)
    store.files[f"{BRAM}/rules.yaml"] = dump_yaml({"rules": BRAM_RULES})
    _set(store, f"{ADA}/links.yaml", dump_yaml({"links": [
        {"to": "project:heron", "role": "contributor", "source": "operator"},
        {"to": "org:example-client", "role": "advisor", "source": "operator"},
    ]}))
    return store


def _end_heron_link(store, today=TODAY):
    _set(store, f"{ADA}/links.yaml", dump_yaml({"links": [
        {"to": "project:heron", "role": "contributor", "until": _days(today, -1), "source": "operator"},
        {"to": "org:example-client", "role": "advisor", "source": "operator"},
    ]}))


def _snapshot(store):
    return {path: store.files[path] for path in sorted(store.files)}


# --------------------------------------------------------------------- acceptance


def test_bram_lists_his_tier_the_heron_seal_and_every_rule(store, put):
    _fixture(store, put)
    result = review_person(store, "people/bram", today=TODAY)
    [tier] = result["tiers"]
    assert (tier["tier"], tier["source"], tier["valid_from"], tier["recorded"], tier["in_force"]) == ("reviewed", "operator", _days(TODAY, -14), _days(TODAY, -14), True)
    assert result["seals"] == [{"entity": "project:heron", "sealed_from": "bram", "via": None, "label_source": "operator"}]
    assert result["rules"] == BRAM_RULES
    assert result["fact_seals"] == [{"entity": "person:ada", "file": "log/2026-09.md#e01", "line": None}]
    assert result["ended_affiliations"] == []


def test_ada_lists_her_open_tier_her_heron_link_and_the_default_that_would_apply(store, put):
    _fixture(store, put)
    result = review_person(store, "people/ada", today=TODAY)
    assert result["tier_in_force"] == {"tier": "open", "lapsed": False}
    assert [(l["record"], l["state"]) for l in result["links"]] == [("project:heron", "current"), ("org:example-client", "current")]
    assert result["default_tiers"] == [{"entity": "org:example-client", "default_tier": "reviewed", "label_source": "operator"}]
    assert result["clearances"] == [{"entity": "org:example-client", "clearance": "green", "label_source": "operator"}]


def test_an_ended_affiliation_under_an_open_tier_is_reported_and_linted(store, put):
    _fixture(store, put)
    _end_heron_link(store)
    result = review_person(store, "people/ada", today=TODAY)
    assert result["ended_affiliations"] == [{"to": "project:heron", "until": _days(TODAY, -1), "tier": "open", "tier_recorded": _days(TODAY, -14)}]
    warnings = [f for f in lint_store(store, today=TODAY)["warnings"] if f["rule"] == ENDED]
    assert len(warnings) == 1 and warnings[0]["message"].startswith("affiliation ended; permissive tier still in force")
    assert warnings[0]["entity"] == ADA


def test_the_cli_says_so_and_exits_1(tmp_path, put, monkeypatch, capsys):
    data, today = tmp_path / "data", date.today().isoformat()
    store = _fixture(Store(data), put, today=today)
    from acquaint.__main__ import main

    monkeypatch.setenv("ACQUAINT_DATA_DIR", str(data))

    def run(*args):
        with pytest.raises(SystemExit) as exited:
            main(["review", *args])
        captured = capsys.readouterr()
        return exited.value.code, captured.out, captured.err

    code, out, _ = run("bram", "--json")
    result = json.loads(out)
    assert code == 0 and [t["tier"] for t in result["tiers"]] == ["reviewed"] and len(result["rules"]) == 2
    code, out, _ = run("ada")
    assert code == 0 and "project:heron" in out and "org:example-client" in out
    _end_heron_link(store, today)
    code, out, err = run("ada")
    assert code == 1 and "affiliation ended" in err
    with pytest.raises(SystemExit) as exited:
        main(["lint"])
    assert "affiliation ended; permissive tier still in force" in capsys.readouterr().out


def test_review_never_modifies_the_store(store, put):
    _fixture(store, put)
    _end_heron_link(store)
    before = _snapshot(store)
    for key in ("people/ada", "people/bram"):
        review_person(store, key, today=TODAY)
    assert _snapshot(store) == before


# ---------------------------------------------------------------- the rest


def test_a_tier_recorded_after_the_link_ended_was_already_reviewed(store, put):
    _fixture(store, put)
    _end_heron_link(store)
    _set(store, f"{ADA}/trust.yaml", _trust(_tier("open", recorded=TODAY, valid_from=TODAY)))
    assert review_person(store, "people/ada", today=TODAY)["ended_affiliations"] == []
    assert not [f for f in lint_store(store, today=TODAY)["warnings"] if f["rule"] == ENDED]


@pytest.mark.parametrize("tier", ["need-to-know", "reviewed"])
def test_an_ended_link_under_a_restrictive_tier_is_fine(store, put, tier):
    _fixture(store, put)
    _end_heron_link(store)
    _set(store, f"{ADA}/trust.yaml", _trust(_tier(tier)))
    assert review_person(store, "people/ada", today=TODAY)["ended_affiliations"] == []
    assert not [f for f in lint_store(store, today=TODAY)["warnings"] if f["rule"] == ENDED]


def test_a_lapsed_open_tier_is_not_in_force_as_open(store, put):
    _fixture(store, put)
    _end_heron_link(store)
    _set(store, f"{ADA}/trust.yaml", _trust(_tier("open", review_by=_days(TODAY, -1))))
    assert review_person(store, "people/ada", today=TODAY)["ended_affiliations"] == []


def test_seals_through_a_linked_record_and_rules_elsewhere(store, put):
    _fixture(store, put)
    put(store, "projects/osprey", meta={"name": "Osprey", "sealed_from": ["org:example-client"], "label_source": "operator"},
        files={"rules.yaml": dump_yaml({"rules": [{"when": {"person": "person:ada"}, "do": {"channel": "email"}, "source": "operator"},
                                                   {"when": {"purpose": "adage"}, "do": {"channel": "chat"}, "source": "operator"}]})})
    result = review_person(store, "people/ada", today=TODAY)
    assert {"entity": "project:osprey", "sealed_from": "org:example-client", "via": "org:example-client", "label_source": "operator"} in result["seals"]
    assert [r["rule"]["do"]["channel"] for r in result["rules_elsewhere"]] == ["email"], "a substring is not a mention"


def test_review_is_for_people(store, put):
    _fixture(store, put)
    with pytest.raises(AcquaintError, match="not a person"):
        review_person(store, HERON, today=TODAY)


def test_the_tool_result_is_json_ready(tmp_path, put):
    data = tmp_path / "data"
    _fixture(Store(data), put, today=date.today().isoformat())
    result = tools.review("bram", data_dir=str(data))
    json.dumps(result)
    assert result["ok"] and "reviewed" in result["text"] and "project:heron" in result["text"]
