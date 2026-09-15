"""The disclosure schema: tiers in trust.yaml, labels, seals, vocabulary, clearance and default tiers, fact tags, and the lint that keeps them honest.

Every person, project and organisation here is invented.
"""

from datetime import date, timedelta

import pytest

from acquaint import tools
from acquaint.edit import new_entity
from acquaint.lint import lint_store
from acquaint.records import dump_yaml, join_frontmatter, split_frontmatter
from acquaint.render import render
from acquaint.store import Store

TODAY = "2026-09-15"
ADA, BRAM, HERON, CLIENT = "people/ada", "people/bram", "projects/heron", "orgs/example-client"
DROP = object()


def _days(today, n):
    return (date.fromisoformat(today) + timedelta(days=n)).isoformat()


def _tier(tier, today=TODAY, **changes):
    entry = {"tier": tier, "valid_from": _days(today, -14), "valid_to": None, "recorded": _days(today, -14), "source": "operator"}
    if tier in ("open", "involved"):
        entry["review_by"] = _days(today, 47)
    entry.update(changes)
    return {k: v for k, v in entry.items() if v is not DROP}


def _trust(*entries):
    return dump_yaml({"tiers": list(entries)})


def build(store, put, today=TODAY):
    """Ada open with a review date; Bram reviewed; project Heron amber, sealed from Bram, with vocabulary; a client org."""
    store.files["POLICY.md"] = "# What this store may hold\n"
    put(store, ADA, meta={"name": "Ada Example"}, files={
        "trust.yaml": _trust(_tier("open", today, note="may hear about the operator's other work")),
        "links.yaml": dump_yaml({"links": [{"to": "project:heron", "role": "contributor", "source": "operator"}]}),
        "log/2026-09.md": "## e01 · 2026-09-10 · observation\nAsked when the bird project ships [sealed-from: bram]\n- source: operator\n",
    })
    put(store, BRAM, meta={"name": "Bram Example"}, files={"trust.yaml": _trust(_tier("reviewed", today))})
    put(
        store,
        HERON,
        meta={"name": "Heron", "label": "amber", "sealed_from": ["bram"], "vocabulary": ["the bird project", "H."], "label_source": "operator"},
        body="## What & status\n- Heron ships in October. [label: amber] [source: operator]\n\n"
        "## Where things live\n| What | Where |\n|---|---|\n| Code | a private repository |\n",
    )
    put(store, CLIENT, meta={"name": "Example Client", "default_tier": "reviewed", "clearance": "green", "label_source": "operator"})
    return store


def _edit_meta(store, key, **changes):
    meta, body, _ = split_frontmatter(store.files[f"{key}/PROFILE.md"])
    meta.update(changes)
    store.files[f"{key}/PROFILE.md"] = join_frontmatter({k: v for k, v in meta.items() if v is not DROP}, body)


def _replace(store, path, old, new):
    assert old in store.files[path]
    store.files[path] = store.files[path].replace(old, new)


def _set(store, path, text):
    store.files[path] = text


# The acceptance line of the slice, then the rest of the rules.
ERRORS = [
    pytest.param("tier-unsourced", lambda s: _set(s, f"{ADA}/trust.yaml", _trust(_tier("open", source="a scraped page"))), id="tier-from-a-scraped-page"),
    pytest.param("label-unsourced", lambda s: _edit_meta(s, HERON, label_source=DROP), id="label-without-label-source"),
    pytest.param("tier-without-review", lambda s: _set(s, f"{ADA}/trust.yaml", _trust(_tier("open", review_by=DROP))), id="open-without-review-by"),
    pytest.param("unknown-label", lambda s: _edit_meta(s, HERON, label="purple"), id="unknown-label-value"),
    pytest.param("bad-fact-tag", lambda s: _replace(s, f"{HERON}/PROFILE.md", "[label: amber]", "[label amber]"), id="fact-tag-bad-grammar"),
    pytest.param("unknown-sealed-from", lambda s: _edit_meta(s, HERON, sealed_from=["cy"]), id="sealed-from-no-entity"),
    pytest.param("label-unsourced", lambda s: _edit_meta(s, HERON, label_source='self: "keep it quiet"'), id="label-sourced-to-someone-else"),
    pytest.param("tier-unsourced", lambda s: _set(s, f"{BRAM}/trust.yaml", _trust(_tier("reviewed", source=DROP))), id="tier-without-source"),
    pytest.param("unknown-tier", lambda s: _set(s, f"{BRAM}/trust.yaml", _trust(_tier("trusted"))), id="unknown-tier-value"),
    pytest.param("unknown-tier", lambda s: _edit_meta(s, CLIENT, default_tier="friendly"), id="unknown-default-tier"),
    pytest.param("unknown-clearance", lambda s: _edit_meta(s, CLIENT, clearance="beige"), id="unknown-clearance"),
    pytest.param("bad-date", lambda s: _set(s, f"{ADA}/trust.yaml", _trust(_tier("open", review_by="soon"))), id="review-by-not-a-date"),
    pytest.param("unknown-label", lambda s: _replace(s, f"{HERON}/PROFILE.md", "[label: amber]", "[label: purple]"), id="fact-tag-unknown-label"),
    pytest.param("bad-fact-tag", lambda s: _replace(s, f"{ADA}/log/2026-09.md", "[sealed-from: bram]", "[sealed_from: bram]"), id="log-tag-bad-grammar"),
    pytest.param("unknown-sealed-from", lambda s: _replace(s, f"{ADA}/log/2026-09.md", "[sealed-from: bram]", "[sealed-from: cy]"), id="log-seal-no-entity"),
    pytest.param("unparseable", lambda s: _set(s, f"{BRAM}/trust.yaml", "tiers: [\n"), id="trust-yaml-does-not-parse"),
]

WARNINGS = [
    pytest.param("tier-lapsed", lambda s: _set(s, f"{ADA}/trust.yaml", _trust(_tier("open", review_by=_days(TODAY, -1)))), id="lapsed-permissive-tier"),
    pytest.param("public-repository-not-clear", lambda s: _replace(s, f"{HERON}/PROFILE.md", "a private repository", "github.com/example/heron (public)"), id="amber-project-in-public-repo"),
    pytest.param("sealed-but-linked", lambda s: _set(s, f"{BRAM}/links.yaml", dump_yaml({"links": [{"to": "project:heron", "source": "operator"}]})), id="sealed-from-a-linked-person"),
    pytest.param("misplaced-field", lambda s: _edit_meta(s, HERON, clearance="green"), id="clearance-on-a-project"),
    pytest.param("misplaced-field", lambda s: _set(s, f"{HERON}/trust.yaml", _trust(_tier("reviewed"))), id="trust-yaml-on-a-project"),
    pytest.param("vocabulary-not-text", lambda s: _edit_meta(s, HERON, vocabulary=["the bird project", 7]), id="vocabulary-not-text"),
]


def test_the_fixture_store_lints_clean(store, put):
    result = lint_store(build(store, put), today=TODAY)
    assert (result["errors"], result["warnings"]) == ([], [])


@pytest.mark.parametrize("rule, mutate", ERRORS)
def test_each_mistake_is_exactly_one_error_naming_its_rule(store, put, rule, mutate):
    mutate(build(store, put))
    result = lint_store(store, today=TODAY)
    assert [f["rule"] for f in result["errors"]] == [rule], result["errors"]


@pytest.mark.parametrize("rule, mutate", WARNINGS)
def test_each_doubt_is_exactly_one_warning_naming_its_rule(store, put, rule, mutate):
    mutate(build(store, put))
    result = lint_store(store, today=TODAY)
    assert result["errors"] == [] and [f["rule"] for f in result["warnings"]] == [rule], result


def test_what_does_not_warn(store, put):
    build(store, put)
    _set(store, f"{BRAM}/links.yaml", dump_yaml({"links": [{"to": "project:heron", "until": _days(TODAY, -30), "source": "operator"}]}))
    _replace(store, f"{HERON}/PROFILE.md", "a private repository", "github.com/example/heron (public)")
    _edit_meta(store, HERON, label="clear")
    _set(store, f"{BRAM}/trust.yaml", _trust(_tier("reviewed", review_by=_days(TODAY, -100))))
    result = lint_store(store, today=TODAY)
    assert (result["errors"], result["warnings"]) == ([], []), "an ended link, a clear project and a restrictive tier are fine"


def test_a_superseded_tier_is_history_not_a_lapse(store, put):
    build(store, put)
    earlier = _tier("involved", valid_from=_days(TODAY, -200), valid_to=_days(TODAY, -14), review_by=_days(TODAY, -100))
    _set(store, f"{ADA}/trust.yaml", _trust(earlier, _tier("open")))
    result = lint_store(store, today=TODAY)
    assert (result["errors"], result["warnings"]) == ([], [])


def test_who_prints_the_label_and_the_tier_in_force(tmp_path, put, monkeypatch, capsys):
    data = tmp_path / "data"
    build(Store(data), put, today=date.today().isoformat())

    def ask(name, field):
        return tools.who(name, field=field, data_dir=str(data))

    assert render(ask("heron", "label"))[0] == "amber"
    assert render(ask("ada", "tier"))[0] == "open"
    assert [ask(n, f)["value"] for n, f in [("bram", "tier"), ("bram", "label"), ("example-client", "label"), ("heron", "sealed_from")]] == ["reviewed", "green", "amber", ["bram"]]
    assert ask("heron", "tier")["ok"] is False, "a project has no tier of its own"

    from acquaint.__main__ import main

    monkeypatch.setenv("ACQUAINT_DATA_DIR", str(data))
    for args, expected in [(["who", "heron", "-f", "label"], "amber\n"), (["who", "ada", "-f", "tier"], "open\n")]:
        with pytest.raises(SystemExit) as exited:
            main(args)
        assert (exited.value.code, capsys.readouterr().out) == (0, expected)


def test_who_reads_a_lapsed_tier_as_need_to_know_and_says_so(tmp_path, put):
    data, today = tmp_path / "data", date.today().isoformat()
    store = build(Store(data), put, today=today)
    _set(store, f"{ADA}/trust.yaml", _trust(_tier("open", today, review_by=_days(today, -1))))
    result = tools.who("ada", field="tier", data_dir=str(data))
    assert result["value"] == "need-to-know" and "lapsed" in " ".join(result["warnings"])


def test_new_records_and_the_policy_document_the_schema(store):
    new_entity(store, "person", "Ada Lovelace", today=TODAY)
    new_entity(store, "project", "Heron", today=TODAY)
    assert "trust.yaml" in store.files["people/ada-lovelace/PROFILE.md"]
    assert "default_tier" in store.files["projects/heron/PROFILE.md"]
    assert "Only the operator grants trust" in store.files["POLICY.md"]
    assert lint_store(store, today=TODAY)["errors"] == []
