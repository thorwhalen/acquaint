"""The deterministic deslop check: tiers by tolerance, counted rules, blocklists, the catalogue seam."""

import pytest

from acquaint.deslop import lint_text, recipient_card
from acquaint.store import Store

CONTRASTIVE = "This isn't just a tool, it's a new way of working. It is not only fast, but also simple."
TRIADS = "It is fast, simple, and cheap. We tested speed, memory, and cost. Teams, partners, and clients like it."
CLEAN = "The export will be ready on Friday. Can you grant read access to the sales folder by Thursday? If not, I will send a zip instead."


def _enforced(result):
    return sorted({f["rule"] for f in result["findings"] if f["enforced"]})


@pytest.mark.parametrize("tolerance", ["tolerant", "neutral", "averse", "unknown"])
def test_clean_text_passes_at_every_tolerance(tolerance):
    assert lint_text(CLEAN, tolerance=tolerance)["ok"]


@pytest.mark.parametrize(
    "text, tolerance, ok",
    [
        (CONTRASTIVE, "tolerant", True),   # W is not enforced for a tolerant reader
        (CONTRASTIVE, "neutral", False),   # two constructions, one allowed
        (TRIADS, "neutral", True),         # S is reported, not enforced
        (TRIADS, "averse", False),
        ("Hi [ASK: first name], the export lands Friday.", "tolerant", False),  # E always
    ],
)
def test_tolerance_decides_what_is_enforced(text, tolerance, ok):
    result = lint_text(text, tolerance=tolerance)
    assert result["ok"] is ok
    assert result["findings"], "findings are reported even when not enforced"


def test_overlapping_patterns_count_once():
    result = lint_text(CONTRASTIVE, tolerance="neutral")
    assert len([f for f in result["findings"] if f["rule"] == "contrastive-negation"]) == 2


def test_relational_messages_never_pass():
    result = lint_text("I'm so sorry for your loss.", tolerance="tolerant")
    assert result["relational"] and not result["ok"]


def test_recipient_blocklist_from_the_writing_card():
    store = Store(files={})
    store["people/ada"] = {
        "PROFILE.md": "---\nname: Ada\n---\n",
        "style.md": "---\nai_tolerance: averse\n---\n## Blocklist\n- \"circle back\" [source: operator]\n- synergy [source: operator]\n",
    }
    card = recipient_card(store["people/ada"])
    assert card == {"tolerance": "averse", "disclosure": None, "blocklist": ["circle back", "synergy"]}
    result = lint_text("Let's circle back on Friday.", tolerance=card["tolerance"], blocklist=card["blocklist"])
    assert _enforced(result) == ["recipient-blocklist"]


def test_the_catalogue_is_a_seam():
    catalog = {
        "tolerance": {"neutral": {"enforce": ["E"], "em_dash_per_100w_max": 9, "contrastive_max": 9, "triads_max": 9}},
        "metrics": {"min_sentences_for_rhythm": 99, "sentence_len_cv_min": 0, "short_message_words": 0},
        "rules": [{"id": "house-word", "tier": "E", "message": "not in this house", "patterns": [r"\bsynergy\b"]}],
    }
    assert _enforced(lint_text("Pure synergy.", catalog=catalog)) == ["house-word"]
    assert lint_text("Great question!", catalog=catalog)["ok"], "the shipped catalogue is not consulted"


def test_unknown_tolerance_is_an_error():
    with pytest.raises(ValueError, match="tolerance"):
        lint_text("hello", tolerance="indifferent")
