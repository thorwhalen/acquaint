"""The disclosure answer: tiers in force, the clearance lattice, seals, the vocabulary to scan for, what was already told, and the gaps.

Built on the A1 fixture store (``test_disclosure_schema.build``). Every person, project and
organisation here is invented.
"""

import json
from datetime import date

import pytest

from acquaint import tools
from acquaint.disclosure import disclose
from acquaint.lint import lint_store
from acquaint.records import dump_yaml
from acquaint.store import AcquaintError, Store
from test_disclosure_schema import ADA, BRAM, CLIENT, HERON, TODAY, _days, _edit_meta, _set, _tier, _trust, build

CY, DEE, WREN = "people/cy", "people/dee", "projects/wren"
HERON_TERMS = ["Heron", "the bird project", "H."]


def _audience(scope, *, ref="github:example/app#12", complete=False, readers=()):
    return json.dumps({"ref": ref, "scope": scope, "complete": complete, "readers": list(readers)})


def _terms(result, entity):
    return [v["term"] for v in result["vocabulary"] if v["entity"] == entity]


# --------------------------------------------------------------------- acceptance


def test_ada_on_heron_is_amber_and_cleared_for_her_own_project(store, put):
    result = disclose(build(store, put), ["ada"], projects=["heron"], today=TODAY)
    ada = result["people"]["ada"]
    assert (ada["tier"], ada["clearance"], ada["lapsed"], ada["source"]) == ("open", "amber", False, "operator")
    assert ada["involved_in"] == ["project:heron"]
    assert result["entities"]["project:heron"]["cleared"] == ["ada"]
    assert result["least_clearance"] == "amber"
    assert result["vocabulary"] == [] and result["seals"] == []


def test_adding_bram_drops_to_clear_and_seals_heron(store, put):
    result = disclose(build(store, put), ["ada", "bram"], projects=["heron"], today=TODAY)
    assert result["least_clearance"] == "clear"
    assert result["seals"] == [{"entity": "project:heron", "from": "bram"}]
    heron = [v for v in result["vocabulary"] if v["entity"] == "project:heron"]
    assert [v["term"] for v in heron] == HERON_TERMS
    assert all(v["sealed_from"] == ["bram"] and v["label"] == "amber" for v in heron)
    assert result["entities"]["project:heron"]["cleared"] == ["ada"]


def test_a_public_audience_puts_everything_not_clear_in_the_vocabulary(store, put):
    build(store, put)
    put(store, WREN, meta={"name": "Wren", "label": "clear", "label_source": "operator"})
    result = disclose(store, ["ada"], audience=_audience("public"), today=TODAY)
    assert result["least_clearance"] == "clear"
    named = {v["entity"] for v in result["vocabulary"]}
    assert named == {ref for ref, e in result["entities"].items() if e["label"] != "clear"}
    assert "project:wren" not in named and {"project:heron", "org:example-client", "person:ada"} <= named


def test_an_org_audience_is_held_to_the_organisations_clearance(store, put):
    build(store, put)
    store.files[f"{CLIENT}/identities.yaml"] = dump_yaml({"identities": [{"platform": "github", "value": "example-client", "source": "operator"}]})
    result = disclose(store, [], audience=_audience("org", ref="github:example-client/app#12"), today=TODAY)
    assert result["audience"]["organisation"] == "org:example-client"
    assert result["least_clearance"] == "green"
    assert disclose(store, ["ada"], audience=_audience("org", ref="github:example-client/app#12"), today=TODAY)["least_clearance"] == "green"


def test_a_lapsed_open_tier_is_clear_and_says_so(store, put):
    build(store, put)
    _set(store, f"{ADA}/trust.yaml", _trust(_tier("open", review_by=_days(TODAY, -1))))
    ada = disclose(store, ["ada"], projects=["heron"], today=TODAY)["people"]["ada"]
    assert (ada["clearance"], ada["lapsed"], ada["tier"], ada["recorded_tier"]) == ("clear", True, "need-to-know", "open")


def test_an_id_with_no_record_is_a_gap_read_as_a_stranger(store, put):
    result = disclose(build(store, put), ["ada", "zed"], projects=["heron"], today=TODAY)
    assert result["gaps"]["unrecorded"] == ["zed"]
    assert result["least_clearance"] == "clear" and "zed" not in result["people"]
    assert _terms(result, "project:heron") == HERON_TERMS, "an unknown reader is not cleared for an amber project"


def test_a_need_to_know_person_linked_to_heron_is_cleared_for_heron(store, put):
    build(store, put)
    put(store, CY, meta={"name": "Cy Example"}, files={
        "trust.yaml": _trust(_tier("need-to-know")),
        "links.yaml": dump_yaml({"links": [{"to": "project:heron", "source": "operator"}]}),
    })
    result = disclose(store, ["cy"], projects=["heron"], today=TODAY)
    assert result["people"]["cy"]["clearance"] == "clear"
    assert result["entities"]["project:heron"]["cleared"] == ["cy"] and _terms(result, "project:heron") == []


def test_remember_disclosed_is_what_was_already_told(tmp_path, put, monkeypatch, capsys):
    data, today = tmp_path / "data", date.today().isoformat()
    build(Store(data), put, today=today)
    from acquaint.__main__ import main

    monkeypatch.setenv("ACQUAINT_DATA_DIR", str(data))
    with pytest.raises(SystemExit) as exited:
        main(["remember", "ada", "sent the export note", "--kind", "interaction", "--disclosed", "project:heron"])
    assert exited.value.code == 0
    capsys.readouterr()
    with pytest.raises(SystemExit) as exited:
        main(["disclosure", "ada", "--project", "heron", "--json"])
    result = json.loads(capsys.readouterr().out)
    assert exited.value.code == 0
    [told] = result["people"]["ada"]["already_told"]
    assert (told["entity"], told["date"]) == ("project:heron", today)
    assert lint_store(Store(data))["errors"] == []


# ------------------------------------------------------------------ the CLI surface


def test_the_cli_takes_several_readers_projects_and_an_audience_file(tmp_path, put, monkeypatch, capsys):
    data = tmp_path / "data"
    build(Store(data), put, today=date.today().isoformat())
    audience = tmp_path / "public.json"
    audience.write_text(_audience("public"), encoding="utf-8")
    from acquaint.__main__ import main

    monkeypatch.setenv("ACQUAINT_DATA_DIR", str(data))

    def run(*args):
        with pytest.raises(SystemExit) as exited:
            main(["disclosure", *args])
        return exited.value.code, capsys.readouterr().out

    code, out = run("ada", "bram", "--project", "heron", "--json")
    result = json.loads(out)
    assert code == 0 and result["least_clearance"] == "clear" and result["seals"] == [{"entity": "project:heron", "from": "bram"}]
    code, out = run("ada", "--audience-json", str(audience), "--json")
    assert code == 0 and json.loads(out)["audience"]["scope"] == "public"
    code, out = run("ada", "bram", "--project", "heron")
    assert code == 0 and "sealed: project:heron from bram" in out and "the bird project" in out


# ---------------------------------------------------------------- failing closed


def test_default_tier_of_a_linked_org_applies_when_no_tier_is_recorded(store, put):
    build(store, put)
    put(store, DEE, meta={"name": "Dee Example"}, files={"links.yaml": dump_yaml({"links": [{"to": "org:example-client", "source": "operator"}]})})
    dee = disclose(store, ["dee"], today=TODAY)["people"]["dee"]
    assert (dee["tier"], dee["clearance"], dee["source"]) == ("reviewed", "clear", "default_tier of org:example-client")


def test_the_most_restrictive_default_wins_and_an_ended_link_gives_none(store, put):
    build(store, put)
    _edit_meta(store, HERON, default_tier="involved")
    links = [{"to": "project:heron", "source": "operator"}, {"to": "org:example-client", "until": _days(TODAY, -1), "source": "operator"}]
    put(store, DEE, meta={"name": "Dee Example"}, files={"links.yaml": dump_yaml({"links": links})})
    assert disclose(store, ["dee"], today=TODAY)["people"]["dee"]["tier"] == "need-to-know", "the org link has ended; a permissive default reads as lapsed"
    links[1].pop("until")
    _set(store, f"{DEE}/links.yaml", dump_yaml({"links": links}))
    assert disclose(store, ["dee"], today=TODAY)["people"]["dee"]["tier"] == "reviewed"


def test_nothing_recorded_is_need_to_know_and_a_gap(store, put):
    build(store, put)
    put(store, DEE, meta={"name": "Dee Example"})
    result = disclose(store, ["dee"], today=TODAY)
    assert result["people"]["dee"]["tier"] == "need-to-know" and result["gaps"]["no_tier"] == ["dee"]


@pytest.mark.parametrize("path, change", [
    (f"{ADA}/trust.yaml", lambda s: _set(s, f"{ADA}/trust.yaml", _trust(_tier("open", source="a scraped page")))),
    (HERON, lambda s: _edit_meta(s, HERON, label="clear", label_source="a colleague said so")),
    (CLIENT, lambda s: _edit_meta(s, CLIENT, clearance="red", label_source="none located")),
], ids=["unsourced-open-tier", "unsourced-clear-label", "unsourced-org-clearance"])
def test_what_the_operator_did_not_set_never_widens(store, put, path, change):
    build(store, put)
    store.files[f"{CLIENT}/identities.yaml"] = dump_yaml({"identities": [{"platform": "github", "value": "example-client", "source": "operator"}]})
    change(store)
    result = disclose(store, ["ada", "bram"], audience=_audience("org", ref="github:example-client/app"), today=TODAY)
    assert result["people"]["ada"]["clearance"] in {"amber", "clear"}
    assert result["entities"]["project:heron"]["label"] == "amber"
    assert result["least_clearance"] == "clear"


def test_a_seal_beats_a_link(store, put):
    build(store, put)
    _set(store, f"{BRAM}/links.yaml", dump_yaml({"links": [{"to": "project:heron", "source": "operator"}]}))
    result = disclose(store, ["bram"], projects=["heron"], today=TODAY)
    assert result["entities"]["project:heron"]["cleared"] == [] and _terms(result, "project:heron") == HERON_TERMS


@pytest.mark.parametrize("scope, complete, expected", [
    ("operator", False, "amber"),
    ("named", True, "amber"),
    ("named", False, "clear"),
    ("group", False, "clear"),
    ("somewhere", True, "clear"),
])
def test_scopes(store, put, scope, complete, expected):
    reader = {"channel": "email", "native_id": "ada@example.org"}
    build(store, put)
    store.files[f"{ADA}/identities.yaml"] = dump_yaml({"identities": [{"platform": "email", "value": "ada@example.org", "source": "operator"}]})
    result = disclose(store, [], audience=_audience(scope, complete=complete, readers=[reader]), today=TODAY)
    assert result["least_clearance"] == expected and list(result["people"]) == ["ada"]


def test_audience_readers_resolve_as_resolve_does_and_the_operator_is_not_a_reader(store, put):
    build(store, put)
    store.files[f"{BRAM}/identities.yaml"] = dump_yaml({"identities": [{"platform": "github", "value": "bram-example", "source": "operator"}]})
    readers = [
        {"channel": "github", "native_id": "1", "handle": "bram-example"},
        {"channel": "github", "native_id": "2", "handle": "someone-else"},
        {"channel": "github", "native_id": "3", "handle": "the-operator", "is_self": True},
    ]
    result = disclose(store, ["ada"], audience=_audience("named", complete=True, readers=readers), today=TODAY)
    assert sorted(result["people"]) == ["ada", "bram"] and result["gaps"]["unrecorded"] == ["github:someone-else"]
    assert result["least_clearance"] == "clear"


def test_disclosure_needs_a_reader_and_exact_projects(store, put):
    build(store, put)
    with pytest.raises(AcquaintError):
        disclose(store, [], today=TODAY)
    with pytest.raises(AcquaintError):
        disclose(store, ["ada"], projects=["her"], today=TODAY)
    with pytest.raises(AcquaintError):
        disclose(store, ["ada"], audience="{not json", today=TODAY)


def test_remember_disclosed_checks_its_targets_and_lint_checks_hand_edits(store, put):
    build(store, put)
    from acquaint.edit import append_observation

    with pytest.raises(AcquaintError, match="interaction"):
        append_observation(store, "ada", "sent a note", disclosed=["heron"], today=TODAY)
    with pytest.raises(AcquaintError):
        append_observation(store, "ada", "sent a note", kind="interaction", disclosed=["project:osprey"], today=TODAY)
    result = append_observation(store, "ada", "sent a note", kind="interaction", disclosed=["heron"], today=TODAY)
    assert result["disclosed"] == ["project:heron"]
    assert lint_store(store, today=TODAY)["errors"] == []
    log = f"{ADA}/log/{TODAY[:7]}.md"
    store.files[log] = store.files[log].replace("disclosed: project:heron", "disclosed: project:osprey")
    assert [f["rule"] for f in lint_store(store, today=TODAY)["errors"]] == ["unknown-disclosed"]


# ------------------------------------------------ what the adversarial review broke


def _osprey(store, put, **meta):
    put(store, "projects/osprey", meta={"name": "Osprey", "label": "red", "label_source": "operator", **meta})


def test_a_seal_that_names_nobody_withholds_the_record_from_everyone(store, put):
    build(store, put)
    for sealed_from in ("ada, bram", ["Ada Example"], ["@nobody"]):
        _edit_meta(store, HERON, sealed_from=sealed_from)
        result = disclose(store, ["ada"], projects=["heron"], today=TODAY)
        assert "Heron" in _terms(result, "project:heron"), sealed_from
        assert result["entities"]["project:heron"]["cleared"] == []
    assert result["gaps"]["unresolved_seals"] == ["project:heron: @nobody"]
    _edit_meta(store, HERON, sealed_from="ada, bram")
    assert disclose(store, ["ada"], today=TODAY)["seals"] == [{"entity": "project:heron", "from": "ada"}]


def test_a_bare_seal_id_means_the_person_when_a_project_shares_it(store, put):
    build(store, put)
    put(store, "projects/ada", meta={"name": "Ada Project"})
    _edit_meta(store, HERON, sealed_from=["ada"])
    assert disclose(store, ["ada"], projects=["heron"], today=TODAY)["seals"] == [{"entity": "project:heron", "from": "ada"}]


def test_an_unreadable_entry_file_withholds_the_record(store, put):
    build(store, put)
    put(store, CY, meta={"name": "Cy Example"}, files={"trust.yaml": _trust(_tier("open"))})
    _osprey(store, put)
    store.files["projects/osprey/PROFILE.md"] = store.files["projects/osprey/PROFILE.md"].replace("name: Osprey", "name: [Osprey")
    result = disclose(store, ["cy"], today=TODAY)
    osprey = result["entities"]["project:osprey"]
    assert (osprey["label"], osprey["cleared"]) == ("red", []) and "osprey" in _terms(result, "project:osprey")
    assert any(g.startswith("projects/osprey/PROFILE.md") for g in result["gaps"]["unreadable"])


@pytest.mark.parametrize("readers", [["email:bram@example.org"], "github:bram", [7]])
def test_audience_readers_in_any_shape_count(store, put, readers):
    build(store, put)
    store.files[f"{BRAM}/identities.yaml"] = dump_yaml({"identities": [{"platform": "email", "value": "bram@example.org", "source": "operator"}]})
    audience = json.dumps({"ref": "email:bram@example.org", "scope": "named", "complete": True, "readers": readers})
    result = disclose(store, [], audience=audience, today=TODAY)
    assert result["least_clearance"] == "clear"
    assert "Heron" in _terms(result, "project:heron")


def test_a_person_given_as_a_project_is_refused(store, put):
    build(store, put)
    with pytest.raises(AcquaintError, match="is a person"):
        disclose(store, ["ada"], projects=["heron", "bram"], today=TODAY)


def test_an_ambiguous_reader_counts_as_every_candidate_for_seals(store, put):
    build(store, put)
    _edit_meta(store, HERON, label="clear")
    put(store, "people/bram-2", meta={"name": "Bram Other"})
    for key in (BRAM, "people/bram-2"):
        store.files[f"{key}/identities.yaml"] = dump_yaml({"identities": [{"platform": "github", "value": "b-ex", "source": "operator"}]})
    result = disclose(store, ["github:b-ex"], today=TODAY)
    assert result["gaps"]["ambiguous"] == ["github:b-ex"] and "Heron" in _terms(result, "project:heron")


def test_a_seal_on_an_org_seals_its_members(store, put):
    build(store, put)
    put(store, "orgs/rival", meta={"name": "Rival"})
    put(store, CY, meta={"name": "Cy Example"}, files={
        "trust.yaml": _trust(_tier("open")),
        "links.yaml": dump_yaml({"links": [{"to": "org:rival", "source": "operator"}]}),
    })
    _edit_meta(store, HERON, sealed_from=["org:rival"])
    result = disclose(store, ["cy"], projects=["heron"], today=TODAY)
    assert result["seals"] == [{"entity": "project:heron", "from": "cy"}] and "Heron" in _terms(result, "project:heron")


def test_projects_narrow_the_report_not_the_vocabulary(store, put):
    build(store, put)
    _edit_meta(store, CLIENT, label="red", sealed_from=["bram"])
    result = disclose(store, ["bram"], projects=["heron"], today=TODAY)
    assert "org:example-client" not in result["entities"] and "Example Client" in _terms(result, "org:example-client")


def test_link_dates_not_written_iso_give_no_involvement(store, put):
    build(store, put)
    _osprey(store, put)
    put(store, CY, meta={"name": "Cy Example"}, files={
        "trust.yaml": _trust(_tier("open")),
        "links.yaml": dump_yaml({"links": [{"to": "project:osprey", "until": "2026-9-1", "source": "operator"}]}),
    })
    result = disclose(store, ["cy"], today=TODAY)
    assert result["people"]["cy"]["involved_in"] == [] and "Osprey" in _terms(result, "project:osprey")
    _set(store, f"{CY}/trust.yaml", _trust(_tier("open", valid_to="2026-9-1")))
    cy = disclose(store, ["cy"], today=TODAY)
    assert cy["people"]["cy"]["tier"] == "reviewed" and cy["gaps"]["unreadable"]


def test_a_link_not_sourced_to_the_operator_gives_no_involvement(store, put):
    build(store, put)
    _osprey(store, put)
    put(store, CY, meta={"name": "Cy Example"}, files={
        "trust.yaml": _trust(_tier("reviewed")),
        "links.yaml": dump_yaml({"links": [{"to": "project:osprey", "source": "their public profile page"}]}),
    })
    result = disclose(store, ["cy"], today=TODAY)
    assert result["entities"]["project:osprey"]["cleared"] == [] and "Osprey" in _terms(result, "project:osprey")


def test_an_unparseable_trust_file_is_reviewed_not_the_org_default(store, put):
    build(store, put)
    _edit_meta(store, CLIENT, default_tier="open")
    put(store, CY, meta={"name": "Cy Example"}, files={
        "trust.yaml": "tiers: [\n",
        "links.yaml": dump_yaml({"links": [{"to": "org:example-client", "source": "operator"}]}),
    })
    cy = disclose(store, ["cy"], today=TODAY)
    assert (cy["people"]["cy"]["tier"], cy["people"]["cy"]["clearance"]) == ("reviewed", "clear") and cy["gaps"]["unreadable"]


def test_a_later_unsourced_entry_cannot_undo_reviewed(store, put):
    build(store, put)
    later = _tier("involved", valid_from=_days(TODAY, -1), source="a scraped page")
    _set(store, f"{BRAM}/trust.yaml", _trust(_tier("reviewed"), later))
    assert disclose(store, ["bram"], today=TODAY)["people"]["bram"]["tier"] == "reviewed"


def test_a_permissive_default_tier_reads_as_lapsed(store, put):
    build(store, put)
    _edit_meta(store, CLIENT, default_tier="open")
    put(store, DEE, meta={"name": "Dee Example"}, files={"links.yaml": dump_yaml({"links": [{"to": "org:example-client", "source": "operator"}]})})
    dee = disclose(store, ["dee"], today="2099-01-01")["people"]["dee"]
    assert (dee["tier"], dee["lapsed"], dee["recorded_tier"]) == ("need-to-know", True, "open")


def test_small_inputs_that_used_to_misbehave(store, put):
    build(store, put)
    assert list(disclose(store, "ada", today=date.fromisoformat(TODAY))["people"]) == ["ada"]
    assert disclose(store, ["ada"], audience={"scope": "operator", "defaulted": "true"}, today=TODAY)["least_clearance"] == "clear"
    store.files[f"{ADA}/identities.yaml"] = dump_yaml({"identities": [{"platform": "github", "value": "ada-gh", "source": "operator"}]})
    assert "ada-gh" in _terms(disclose(store, ["bram"], today=TODAY), "person:ada")


def test_a_missing_audience_file_is_a_clean_error(tmp_path, put, monkeypatch, capsys):
    data = tmp_path / "data"
    build(Store(data), put, today=date.today().isoformat())
    from acquaint.__main__ import main

    monkeypatch.setenv("ACQUAINT_DATA_DIR", str(data))
    with pytest.raises(SystemExit) as exited:
        main(["disclosure", "ada", "--audience-json", str(tmp_path / "missing.json")])
    assert exited.value.code == 1 and "missing.json" in capsys.readouterr().err


def test_mcp_does_not_let_a_model_set_the_date():
    pytest.importorskip("py2mcp")
    import asyncio

    from acquaint.mcp import mk_server

    [tool] = [t for t in asyncio.run(mk_server().list_tools()) if t.name == "disclosure"]
    assert "people" in tool.parameters["properties"] and "today" not in tool.parameters["properties"]


def test_the_tool_result_is_json_ready_and_readable(tmp_path, put):
    data = tmp_path / "data"
    build(Store(data), put, today=date.today().isoformat())
    result = tools.disclosure(["ada", "bram"], projects=["heron"], data_dir=str(data))
    json.dumps(result)
    assert result["ok"] and "least clearance clear" in result["summary"] and "bram: reviewed" in result["text"]
