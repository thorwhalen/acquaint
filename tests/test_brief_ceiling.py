"""The brief at write time: the ceiling, what not to identify, what is withheld, what was already told.

Built on the A1 fixture store (``test_disclosure_schema.build``). Every person, project and
organisation here is invented.
"""

import json
import sys
import types

import pytest

from acquaint import tools
from acquaint.brief import compose_brief
from acquaint.edit import append_observation
from acquaint.records import dump_yaml
from acquaint.store import AcquaintError, Store
from test_disclosure_schema import ADA, TODAY, build

SEALED_FACT = "Asked when the bird project ships"
PUBLIC = {"ref": "github:example/app#12", "scope": "public", "complete": False, "readers": []}
ONLY_ADA = {
    "ref": "email:ada@example.org",
    "scope": "named",
    "complete": True,
    "readers": [{"channel": "email", "native_id": "ada@example.org"}],
}
NEW_KEYS = {"ceiling", "do_not_identify", "withheld", "already_told"}


def _fixture(store, put):
    build(store, put)
    store.files[f"{ADA}/identities.yaml"] = dump_yaml(
        {"identities": [{"platform": "email", "value": "ada@example.org", "source": "operator"}]}
    )
    return store


def _dump(result):
    return json.dumps(result, ensure_ascii=False)


def _section(text, heading):
    return text.split(f"## {heading}", 1)[1].split("\n## ", 1)[0]


def _entities(result):
    return [d["entity"] for d in result["do_not_identify"]]


def _public_behaviour(result):
    text = result["text"]
    assert "world-readable" in result["ceiling"]["line"] and "write for a stranger" in result["ceiling"]["line"]
    assert text.index("## Ceiling") < text.index("## Writing card")
    assert "project:heron" in _entities(result) and "person:ada" not in _entities(result), "not the recipient's own record"
    assert result["withheld"] == [{"entity": "person:ada", "count": 1}]
    assert SEALED_FACT not in _dump(result)


# --------------------------------------------------------------------- acceptance


def test_a_public_audience_file_sets_a_strangers_ceiling(tmp_path, put, monkeypatch, capsys):
    data = tmp_path / "data"
    _fixture(Store(data), put)
    public = tmp_path / "public.json"
    public.write_text(json.dumps(PUBLIC), encoding="utf-8")
    from acquaint.__main__ import main

    monkeypatch.setenv("ACQUAINT_DATA_DIR", str(data))
    with pytest.raises(SystemExit) as exited:
        main(["brief", "ada", "--purpose", "reply", "--audience-json", str(public)])
    out = capsys.readouterr().out
    assert exited.value.code == 0
    assert "world-readable" in _section(out, "Ceiling") and "write for a stranger" in _section(out, "Ceiling")
    assert "project:heron" in _section(out, "Do not identify")
    assert "person:ada: 1 fact" in _section(out, "Withheld")
    assert out.index("## Ceiling") < out.index("## Writing card")
    assert SEALED_FACT not in out
    _public_behaviour(compose_brief(Store(data), ADA, purpose="reply", audience=PUBLIC))


def test_a_named_audience_of_ada_alone_hides_nothing(store, put):
    result = compose_brief(_fixture(store, put), ADA, purpose="reply", audience=ONLY_ADA, today=TODAY)
    assert "project:heron" not in _entities(result)
    assert result["withheld"] == [] and SEALED_FACT in _dump(result)


def test_an_email_to_ada_is_judged_by_ada_even_though_it_can_be_forwarded(store, put):
    """Discussion 32 §4.4: forwarding is accepted, so an incomplete email to Ada keeps what Ada may read, seals on others included."""
    email = {**ONLY_ADA, "complete": False}
    result = compose_brief(_fixture(store, put), ADA, purpose="reply", audience=email, today=TODAY)
    assert "project:heron" not in _entities(result)
    assert result["withheld"] == [] and SEALED_FACT in _dump(result)
    assert "judged by the readers it names" in result["ceiling"]["line"]


class _FakeAudience:
    def __init__(self, data):
        self.data = data

    def to_dict(self):
        return dict(self.data)

    def in_words(self):
        return "world-readable; emailed to watchers and participants; not retractable"


def test_a_ref_asks_correspond_for_the_audience(store, put, monkeypatch):
    asked = []
    fake = types.ModuleType("correspond")
    fake.audience = lambda ref: asked.append(ref) or _FakeAudience({**PUBLIC, "ref": ref})
    monkeypatch.setitem(sys.modules, "correspond", fake)
    result = compose_brief(_fixture(store, put), ADA, purpose="reply", ref="github:example/app#12", today=TODAY)
    assert asked == ["github:example/app#12"]
    assert result["ceiling"]["audience"].startswith("world-readable; emailed to watchers")
    _public_behaviour(result)


def test_a_ref_without_correspond_is_treated_as_public(store, put, monkeypatch):
    monkeypatch.setitem(sys.modules, "correspond", None)  # import correspond now raises ImportError
    result = compose_brief(_fixture(store, put), ADA, purpose="reply", ref="github:example/app#12", today=TODAY)
    assert any("audience unknown; treated as public" in w for w in result["warnings"])
    _public_behaviour(result)


def test_without_a_ref_or_an_audience_the_brief_is_unchanged(store, put):
    result = compose_brief(_fixture(store, put), ADA, purpose="reply", today=TODAY)
    assert not NEW_KEYS & set(result)
    assert "## Ceiling" not in result["text"] and SEALED_FACT in result["text"]


def test_liaise_writing_card_still_reads_the_summary(tmp_path, put):
    """``liaise.gate.writing_card`` calls ``acquaint.brief(recipient, purpose=…)`` and reads ``summary``."""
    data = str(tmp_path / "data")
    _fixture(Store(data), put)
    plain = tools.brief("ada", purpose="reply", data_dir=data)
    ceiling = tools.brief("ada", purpose="reply", audience=json.dumps(PUBLIC), data_dir=data)
    assert plain["summary"] == ceiling["summary"] == "brief for Ada Example (reply)"
    assert not NEW_KEYS & set(plain) and NEW_KEYS <= set(ceiling)


# ---------------------------------------------------------------- minimisation


def test_tagged_lines_above_the_ceiling_leave_every_section(store, put):
    _fixture(store, put)
    store.files[f"{ADA}/PROFILE.md"] += (
        "\n## Write to them\n"
        "- Mention the October date for Heron. [label: amber] [source: operator]\n"
        "- Short replies. [source: operator]\n"
        "- A line with a broken tag. [label amber] [source: operator]\n"
    )
    store.files[f"{ADA}/views.md"] = "## Positions\n- Prefers the red plan. [label: red] [source: operator]\n- Likes tests. [source: operator]\n"
    public = compose_brief(store, ADA, purpose="reply", audience=PUBLIC, today=TODAY)
    dumped = _dump(public)
    assert "October" not in dumped and "broken tag" not in dumped and "red plan" not in dumped
    assert "Short replies" in public["card"]["Write to them"] and "Likes tests" in public["views"]
    assert public["withheld"] == [{"entity": "person:ada", "count": 4}]
    named = compose_brief(store, ADA, purpose="reply", audience=ONLY_ADA, today=TODAY)
    assert "October" in named["card"]["Write to them"] and "red plan" not in _dump(named), "Ada is open (amber), not red"
    assert "broken tag" not in _dump(named), "a malformed tag is withheld from everyone"
    assert named["withheld"] == [{"entity": "person:ada", "count": 2}]


def test_the_norms_of_a_project_above_the_ceiling_stay_out(store, put):
    _fixture(store, put)
    store.files["projects/heron/PROFILE.md"] += "\n## Norms\n- Weekly sync on Thursdays about the migration. [source: operator]\n"
    public = compose_brief(store, ADA, purpose="reply", project="heron", audience=PUBLIC, today=TODAY)
    assert "Thursdays" not in _dump(public) and {"entity": "project:heron", "count": 1} in public["withheld"]
    named = compose_brief(store, ADA, purpose="reply", project="heron", audience=ONLY_ADA, today=TODAY)
    assert "Thursdays" in named["project_norms"]


def test_already_told_comes_from_interaction_entries(store, put):
    _fixture(store, put)
    append_observation(store, ADA, "sent the export note", kind="interaction", disclosed=["heron"], today=TODAY)
    result = compose_brief(store, ADA, purpose="reply", audience=ONLY_ADA, today=TODAY)
    assert [(t["entity"], t["date"]) for t in result["already_told"]] == [("project:heron", TODAY)]
    assert "project:heron" in _section(result["text"], "Already told")


def test_a_ref_and_an_audience_together_are_refused(store, put):
    with pytest.raises(AcquaintError, match="not both"):
        compose_brief(_fixture(store, put), ADA, ref="github:example/app#12", audience=PUBLIC, today=TODAY)
