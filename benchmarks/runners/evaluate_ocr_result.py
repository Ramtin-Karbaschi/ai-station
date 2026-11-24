#!/usr/bin/env python3
"""Measure page-scoped OCR CER/WER against human-transcribed ground truth."""

from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    value = value.replace("\u200c", " ").replace("\u200f", "")
    return " ".join(value.split())


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, expected in enumerate(reference, start=1):
        current = [row]
        for column, observed in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (expected != observed),
                )
            )
        previous = current
    return previous[-1]


def evaluate(structured: dict, ground_truth: dict) -> dict:
    pages = {int(page["page_number"]): page.get("text", "") for page in structured["pages"]}
    page_results = []
    total_char_errors = total_chars = total_word_errors = total_words = 0
    for page_number_text, expected_text in ground_truth["pages"].items():
        page_number = int(page_number_text)
        expected = normalize(expected_text)
        observed = normalize(pages.get(page_number, ""))
        char_errors = edit_distance(list(expected), list(observed))
        expected_words, observed_words = expected.split(), observed.split()
        word_errors = edit_distance(expected_words, observed_words)
        total_char_errors += char_errors
        total_chars += len(expected)
        total_word_errors += word_errors
        total_words += len(expected_words)
        page_results.append(
            {
                "page": page_number,
                "reference_characters": len(expected),
                "reference_words": len(expected_words),
                "cer": char_errors / max(len(expected), 1),
                "wer": word_errors / max(len(expected_words), 1),
            }
        )
    source_pages = int(structured["source"]["pages"])
    return {
        "metric_version": "ai-station.ocr-evaluation.v1",
        "ground_truth_provenance": ground_truth.get("provenance"),
        "evaluated_pages": len(page_results),
        "source_pages": source_pages,
        "page_coverage": len(page_results) / max(source_pages, 1),
        "cer": total_char_errors / max(total_chars, 1),
        "wer": total_word_errors / max(total_words, 1),
        "pages": page_results,
        "promotion_allowed": len(page_results) == source_pages,
        "promotion_note": (
            "Full-document human ground truth coverage is required before engineering-citation promotion."
            if len(page_results) != source_pages
            else "Ground truth covers every source page."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("structured", type=Path)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    structured = json.loads(args.structured.read_text(encoding="utf-8"))
    ground_truth = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    result = evaluate(structured, ground_truth)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
