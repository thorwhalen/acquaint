"""Digests: one file per conversation, a watermark per scope, anchored items, and the tools and brief that read them."""

import pytest

from acquaint import tools
from acquaint.digests import digest_problems, digests, find_digest, mark_digest, new_digest
from acquaint.lint import lint_store
from acquaint.store import AcquaintError

REF = "whatsapp:ada-lovelace"


def test_create_mark_and_find_by_ref(store, put):
    ada = put(store, "people/ada-lovelace", meta={"name": "Ada Lovelace"})
    made = new_digest(ada, REF, today="2026-11-04")
    assert made["file"] == "digests/whatsapp-ada-lovelace.md" and made["through"] == {}
    with pytest.raises(AcquaintError):
        new_digest(ada, REF)
    marked = mark_digest(ada, REF, "2026-11-03T19:37:47+01:00", today="2026-11-04")
    assert marked["through"] == {"content": "2026-11-03T19:37:47+01:00"} and marked["previous"] is None
    mark_digest(ada, REF, "2026-06-21T19:27:45+02:00", scope="style")
    assert find_digest(ada, REF)["through"]["style"] == "2026-06-21T19:27:45+02:00"
    assert [d["ref"] for d in digests(ada)] == [REF]


def test_the_watermark_does_not_move_back_without_force(store, put):
    ada = put(store, "people/ada-lovelace", meta={"name": "Ada Lovelace"})
    new_digest(ada, REF)
    mark_digest(ada, REF, "2026-11-03T19:00:00+01:00")
    with pytest.raises(AcquaintError, match="needs force"):
        mark_digest(ada, REF, "2026-10-01T00:00:00Z")
    assert mark_digest(ada, REF, "2026-10-01T00:00:00Z", force=True)["previous"] == "2026-11-03T19:00:00+01:00"
    with pytest.raises(AcquaintError, match="ISO 8601"):
        mark_digest(ada, REF, "last Tuesday")
    with pytest.raises(AcquaintError, match="scope"):
        mark_digest(ada, REF, "2026-10-01T00:00:00Z", scope="mood")


def test_items_need_anchors_and_quotes_stay_short():
    text = (
        "---\nref: whatsapp:ada-lovelace\nthrough:\n  content: '2026-11-03T19:00:00+01:00'\n---\n"
        "## Orientation\nTwo people, about the engine.\n"
        "## Takeaways\n- Agreed to ship the loom on Friday. [at: 2026-07-03T14:02:11+02:00]\n"
        "- Agreed to something unanchored.\n"
        '## Themes\n- Cost: "' + "word " * 30 + '" [at: 2026-07-04T09:00:00+02:00]\n'
    )
    found = {(severity, rule) for severity, _, rule, _ in digest_problems(text)}
    assert found == {("error", "unanchored"), ("warning", "long-quote")}
    bad = "---\nref: nonsense\nthrough:\n  content: soon\n  mood: '2026-01-01'\n---\n"
    rules = [rule for _, _, rule, _ in digest_problems(bad)]
    assert rules.count("digest-through") == 2 and "digest-ref" in rules


def test_lint_reports_digest_problems(store, put):
    put(
        store,
        "people/ada-lovelace",
        meta={"name": "Ada Lovelace"},
        files={"digests/whatsapp-ada-lovelace.md": "---\nref: whatsapp:ada-lovelace\nthrough: {}\n---\n## Takeaways\n- No anchor here.\n"},
    )
    found = [f for f in lint_store(store)["errors"] if f["file"].startswith("digests/")]
    assert [f["rule"] for f in found] == ["unanchored"]


def test_the_tools_and_the_brief(tmp_path, monkeypatch):
    monkeypatch.setenv("ACQUAINT_DATA_DIR", str(tmp_path / "data"))
    tools.new("person", "Ada Lovelace")
    missing = tools.digest("ada-lovelace", REF)
    assert missing["ok"] is False and missing["since"] is None
    assert tools.digest_new("ada-lovelace", REF)["ok"]
    assert tools.digest_mark("ada-lovelace", REF, through="2026-11-03T19:37:47+01:00")["ok"]
    one = tools.digest("ada-lovelace", REF)
    assert one["since"] == "2026-11-03T19:37:47+01:00"
    assert tools.digest("ada-lovelace")["digests"][0]["ref"] == REF
    text = tools.brief("ada-lovelace")["text"]
    assert "## Conversations on record" in text and "content through 2026-11-03T19:37:47+01:00" in text
