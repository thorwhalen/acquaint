"""The deterministic half of deslop: find the patterns that make prose read as machine-written, scaled to the reader.

How strict the check is depends on the recipient's tolerance of AI-sounding text,
recorded as ``ai_tolerance`` in their ``style.md`` (``tolerant``, ``neutral``,
``averse``; unknown counts as neutral):

- **tolerant** enforces tier E only, with looser counts;
- **neutral** enforces E and W;
- **averse** enforces E, W and S, with the tightest counts.

Findings outside the enforced tiers are still reported, marked ``enforced: False``.
The catalogue is data (``acquaint/data/deslop/tells.yaml``) and a keyword argument,
so a list derived from the operator's own writing can replace it without code changes.

>>> result = lint_text("Great question! This robust tool serves as a bridge.", tolerance="neutral")
>>> sorted({f["rule"] for f in result["findings"] if f["enforced"]})
['ai-vocabulary', 'chat-leftover', 'copula-avoidance']
>>> lint_text("Sending the export on Friday. Two sites, not five.")["ok"]
True
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Iterable
from typing import Any

from acquaint.records import bullets, sections, split_frontmatter
from acquaint.resources import data_yaml

__all__ = ["lint_text", "recipient_card", "text_metrics", "TOLERANCES"]

TOLERANCES = ("tolerant", "neutral", "averse", "unknown")
_WORD_RE = re.compile(r"[A-Za-z0-9’']+")
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]*")
_QUOTED_RE = re.compile(r"[\"“]([^\"”]+)[\"”]")
_SOURCE_TAG_RE = re.compile(r"\[source:[^\]]*\]", re.I)


def recipient_card(entity: Any) -> dict[str, Any]:
    """What the check needs from a recipient's writing card (``style.md``): tolerance, disclosure, blocklist.

    ``ai_tolerance`` and ``disclosure`` come from the card's frontmatter. Blocklist
    phrases are the bullets of its ``## Blocklist`` section: the quoted phrase when a
    bullet quotes one, else the bullet without its source tag.
    """
    text = entity.text("style.md") if "style.md" in entity else ""
    meta, body, _ = split_frontmatter(text)
    blocklist = []
    for title, section in sections(body).items():
        if title.strip().lower() != "blocklist":
            continue
        for _, bullet in bullets(section):
            quoted = _QUOTED_RE.search(bullet)
            phrase = quoted.group(1) if quoted else _SOURCE_TAG_RE.sub("", bullet).strip()
            if phrase:
                blocklist.append(phrase)
    return {
        "tolerance": str(meta.get("ai_tolerance") or "unknown").lower(),
        "disclosure": meta.get("disclosure"),
        "blocklist": blocklist,
    }


def text_metrics(text: str) -> dict[str, float]:
    """Counts the checks use: words, sentences, sentence-length variation, em-dash rate, headers, bold.

    >>> text_metrics("One two three. Four five!")["sentences"]
    2
    """
    words = _WORD_RE.findall(text)
    lengths = [len(_WORD_RE.findall(s)) for s in _SENTENCE_RE.findall(text)]
    lengths = [n for n in lengths if n]
    mean = statistics.fmean(lengths) if lengths else 0.0
    cv = statistics.pstdev(lengths) / mean if len(lengths) > 1 and mean else 0.0
    return {
        "words": len(words),
        "sentences": len(lengths),
        "sentence_len_mean": round(mean, 2),
        "sentence_len_cv": round(cv, 3),
        "em_dashes": text.count("—"),
        "em_dash_per_100w": round(100 * text.count("—") / len(words), 2) if words else 0.0,
        "headers": len(re.findall(r"^#{1,6}\s", text, re.M)),
        "bold": len(re.findall(r"\*\*[^*]+\*\*", text)),
    }


def _finding(rule: str, tier: str, message: str, enforced: bool, text: str, span: tuple[int, int] | None) -> dict:
    excerpt = text[max(0, span[0] - 25) : span[1] + 25].replace("\n", " ").strip() if span else ""
    return {"rule": rule, "tier": tier, "message": message, "enforced": enforced, "span": list(span) if span else None, "excerpt": excerpt}


def lint_text(
    text: str,
    *,
    tolerance: str = "neutral",
    blocklist: Iterable[str] = (),
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check a draft against the tells catalogue at a reader's tolerance: ``{"ok", "findings", "metrics", "relational"}``.

    ``blocklist`` holds phrases this recipient's card says never to use; each hit is
    tier E. ``catalog`` replaces the shipped catalogue (same schema as ``tells.yaml``).
    """
    catalog = catalog if catalog is not None else data_yaml("deslop/tells.yaml")
    levels = catalog["tolerance"]
    level = levels.get(tolerance, levels["neutral"]) if tolerance in TOLERANCES or tolerance in levels else None
    if level is None:
        raise ValueError(f"tolerance must be one of {', '.join(TOLERANCES)}; got {tolerance!r}")
    if isinstance(level, str):
        level = levels[level]
    enforce = set(level["enforce"])
    findings: list[dict] = []

    for rule in catalog["rules"]:
        # Two patterns of one rule often match the same construction: merge overlaps.
        spans: list[tuple[int, int]] = []
        for start, end in sorted(m.span() for p in rule["patterns"] for m in re.finditer(p, text, re.I | re.M)):
            if spans and start < spans[-1][1]:
                spans[-1] = (spans[-1][0], max(end, spans[-1][1]))
            else:
                spans.append((start, end))
        limit = level.get(rule["count_against"]) if rule.get("count_against") else None
        over_limit = limit is None or len(spans) > limit
        for span in spans:
            enforced = rule["tier"] in enforce and over_limit
            message = rule["message"] + (f" ({len(spans)} found, {limit} allowed)" if limit is not None else "")
            findings.append(_finding(rule["id"], rule["tier"], message, enforced, text, span))

    for phrase in blocklist:
        for m in re.finditer(re.escape(phrase), text, re.I):
            findings.append(_finding("recipient-blocklist", "E", f"this recipient's card says never to use {phrase!r}", True, text, m.span()))

    metrics = text_metrics(text)
    limits = catalog["metrics"]
    if metrics["em_dash_per_100w"] > level["em_dash_per_100w_max"] and metrics["em_dashes"] > 1:
        findings.append(_finding("em-dash-density", "W", f"{metrics['em_dash_per_100w']} em dashes per 100 words (max {level['em_dash_per_100w_max']})", "W" in enforce, text, None))
    if metrics["sentences"] >= limits["min_sentences_for_rhythm"] and metrics["sentence_len_cv"] < limits["sentence_len_cv_min"]:
        findings.append(_finding("uniform-rhythm", "S", f"sentence lengths barely vary (variation {metrics['sentence_len_cv']}, want ≥ {limits['sentence_len_cv_min']})", "S" in enforce, text, None))
    if metrics["words"] < limits["short_message_words"] and (metrics["headers"] or metrics["bold"]):
        findings.append(_finding("formatting-in-short-message", "W", "headers or bold in a short message", "W" in enforce, text, None))

    relational = any(re.search(p, text, re.I) for p in catalog.get("relational", {}).get("patterns", []))
    findings.sort(key=lambda f: (not f["enforced"], "ESW".index(f["tier"]), f["span"] or [0]))
    return {
        "ok": not any(f["enforced"] for f in findings) and not relational,
        "tolerance": tolerance,
        "enforced_tiers": sorted(enforce, key="ESW".index),
        "findings": findings,
        "metrics": metrics,
        "relational": relational,
        "relational_message": catalog.get("relational", {}).get("message") if relational else None,
    }
