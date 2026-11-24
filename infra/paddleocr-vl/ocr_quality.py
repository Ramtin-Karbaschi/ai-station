"""Pure OCR quality and human-review decisions.

This module has no Paddle, PDF, or HTTP dependency so quality policy can be
tested independently of the runtime.  ``server.py`` re-exports its helpers for
backward-compatible imports.
"""
from __future__ import annotations

import html
import re
import unicodedata
from typing import Any

_DIGIT_TRANSLATION = str.maketrans(
    "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669",
    "01234567890123456789",
)


def normalize_canary_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").translate(_DIGIT_TRANSLATION)
    normalized = normalized.replace("\u200c", " ").replace("\u200f", "")
    return " ".join(normalized.split()).casefold()


def plain_text(markdown: str) -> str:
    """Reduce OCR markdown to comparable/searchable text without layout markup."""
    text = re.sub(r"!\[[^]]*]\([^)]*\)", " ", markdown or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[`#*_>|~\[\]() ]", " ", text)
    return " ".join(text.split())


def digits(text: str) -> list[str]:
    return re.findall(r"\d+", normalize_canary_text(text))


def evaluate_canaries(pages: list[dict[str, Any]], canaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_number = {page["page_number"]: page for page in pages}
    results = []
    for canary in canaries:
        number, expected = int(canary["page"]), str(canary["expected"])
        page = by_number.get(number)
        haystack = normalize_canary_text(page.get("text", "") if page else "")
        needle = normalize_canary_text(expected)
        results.append({"page": number, "expected": expected, "normalized_expected": needle, "passed": bool(page and needle in haystack)})
    return results


def review_queue(
    pages: list[dict[str, Any]], comparisons: list[dict[str, Any]], canaries: list[dict[str, Any]], expected_pages: int
) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    if len(pages) != expected_pages:
        queue.append({"severity": "critical", "reason": "page_count_mismatch", "expected": expected_pages, "observed": len(pages)})
    queue.extend({"severity": "critical", "reason": "canary_failed", **item} for item in canaries if not item["passed"])
    for page in pages:
        validated_needles = [normalize_canary_text(item.get("expected", "")) for item in canaries if item.get("page") == page["page_number"] and item.get("passed")]
        for block in page.get("blocks", []):
            if block.get("artifact_only") or not block.get("digit_disagreement"):
                continue
            selected = normalize_canary_text(block.get("text", ""))
            if any(needle and needle in selected for needle in validated_needles):
                continue
            queue.append({"severity": "high", "reason": "numeric_engine_disagreement", "page": page["page_number"], "block_id": block.get("id"), "selected_engine": block.get("selected_engine"), "vl_digits": digits(block.get("vl_text", "")), "tesseract_digits": digits(block.get("tesseract_text", "")), "fusion_similarity": block.get("fusion_similarity")})
    for item in comparisons:
        confidence = item.get("tesseract_mean_confidence")
        similarity = item.get("normalized_sequence_similarity", 0.0)
        if confidence is not None and confidence < 0.82:
            queue.append({"severity": "high", "reason": "low_tesseract_confidence", "page": item["page_number"], "value": confidence})
        if similarity < 0.70:
            queue.append({"severity": "high", "reason": "cross_engine_disagreement", "page": item["page_number"], "value": similarity})
    queue.extend(
        {"severity": "critical", "reason": "empty_page_text", "page": page["page_number"]}
        for page in pages
        if not " ".join(str(page.get("text", "")).split())
    )
    return queue
