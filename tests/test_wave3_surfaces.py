#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB))

import catalog_review  # noqa: E402
import media_guard  # noqa: E402
import roi  # noqa: E402


class MediaGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        os.environ["AI_STATION_MEDIA_AUDIT_DIR"] = self.temp.name

    def tearDown(self) -> None:
        self.temp.cleanup()
        os.environ.pop("AI_STATION_MEDIA_AUDIT_DIR", None)

    def test_allows_station_image_prompt_and_hashes_it(self) -> None:
        payload = {
            "prompt": {
                "1": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {
                        "text": "A product photo of a matte black ceramic mug on a wooden desk."
                    },
                }
            }
        }
        result = media_guard.evaluate(payload, source="fixture")
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.prompt_count, 1)
        self.assertEqual(len(result.hashes[0]), 64)
        encoded = json.dumps(result.as_dict())
        self.assertNotIn("ceramic mug", encoded)
        self.assertNotIn("product photo", encoded)

    def test_denies_sexual_content_involving_minors_without_storing_text(self) -> None:
        payload = {
            "nodes": [
                {
                    "type": "CLIPTextEncode",
                    "widgets_values": [
                        "a banned csam request that must never be stored in the audit log"
                    ],
                }
            ]
        }
        result = media_guard.evaluate(payload, source="deny-fixture")
        self.assertEqual(result.decision, "deny")
        self.assertEqual(result.rule, "csam")
        path = media_guard.append_audit(result)
        stored = path.read_text(encoding="utf-8")
        self.assertNotIn("banned csam request", stored)
        self.assertIn('"decision":"deny"', stored)

    def test_skips_markdown_notes_and_weight_filenames(self) -> None:
        payload = {
            "nodes": [
                {
                    "type": "MarkdownNote",
                    "widgets_values": [
                        "## MiniMax Music 3\nA long documentation note about captions and lyrics."
                    ],
                },
                {
                    "type": "MiniMaxMusic3",
                    "widgets_values": [
                        "minimax_music3_dit_int8_convrot.safetensors",
                        "Global Metadata: Lo-fi hip-hop, chillhop. Laid-back study music.",
                    ],
                },
            ]
        }
        texts = media_guard.extract_prompts(payload)
        self.assertEqual(len(texts), 1)
        self.assertIn("Lo-fi hip-hop", texts[0])

    def test_audit_is_size_capped(self) -> None:
        now = datetime(2026, 9, 3, tzinfo=timezone.utc)
        records = []
        for index in range(40):
            records.append(
                {
                    "checked_at": (now - timedelta(hours=index)).isoformat(),
                    "decision": "allow",
                    "padding": "x" * 200,
                }
            )
        pruned = media_guard.prune_records(records, now=now, max_bytes=8192)
        encoded = "\n".join(json.dumps(item) for item in pruned).encode("utf-8")
        self.assertLessEqual(len(encoded), 8192)
        self.assertGreater(len(pruned), 0)

    def test_pinned_music3_workflow_is_allowed(self) -> None:
        path = ROOT / "config/clients/comfyui/workflows/music3-text-to-music.json"
        result = media_guard.evaluate(
            json.loads(path.read_text(encoding="utf-8")),
            source=str(path),
        )
        self.assertEqual(result.decision, "allow")
        self.assertGreater(result.prompt_count, 0)


class RoiTests(unittest.TestCase):
    def test_build_report_uses_operator_tariff(self) -> None:
        totals = roi.SpendTotals(tokens=2_000_000, spend=0.0, source="fixture")
        tariff = {
            "currency": "USD",
            "label": "Test cloud",
            "cloud_usd_per_1k_tokens": 0.005,
            "local_usd_per_1k_tokens": 0.0,
            "notes": "fixture",
            "path": "fixture.json",
        }
        report = roi.build_report(totals, tariff, days=30)
        self.assertEqual(report["tokens"], 2_000_000)
        self.assertEqual(report["cloud_equivalent"], 10.0)
        self.assertEqual(report["savings"], 10.0)
        self.assertTrue(report["requests_allowed"])

    def test_tariff_rejects_negative_rate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tariff.json"
            path.write_text(
                json.dumps({"cloud_usd_per_1k_tokens": -1}),
                encoding="utf-8",
            )
            with self.assertRaises(roi.RoiError):
                roi.load_tariff(path)

    def test_example_tariff_loads(self) -> None:
        tariff = roi.load_tariff(
            ROOT / "config/tariffs/cloud-comparison.example.json"
        )
        self.assertGreaterEqual(tariff["cloud_usd_per_1k_tokens"], 0)
        self.assertEqual(tariff["currency"], "USD")


class CatalogReviewTests(unittest.TestCase):
    def test_explicit_active_model_is_fresh(self) -> None:
        overlay = {
            "stale_days": 180,
            "reviews": {
                "qwen38-27b-q4": {
                    "status": "active",
                    "last_evaluated": "2026-08-27",
                }
            },
        }
        review = catalog_review.resolve_review(
            "qwen38-27b-q4",
            overlay,
            today=date(2026, 9, 3),
        )
        self.assertEqual(review.status, "active")
        self.assertFalse(review.stale)
        ok, reasons = catalog_review.before_replace(
            "qwen38-27b-q4",
            overlay,
            today=date(2026, 9, 3),
        )
        self.assertTrue(ok)
        self.assertEqual(reasons, [])

    def test_unreviewed_and_stale_block_replace(self) -> None:
        overlay = {
            "stale_days": 30,
            "reviews": {
                "old-model": {
                    "status": "active",
                    "last_evaluated": "2025-01-01",
                }
            },
        }
        ok_missing, reasons_missing = catalog_review.before_replace(
            "missing-model",
            overlay,
            today=date(2026, 9, 3),
        )
        self.assertFalse(ok_missing)
        self.assertTrue(any("last-evaluated" in item for item in reasons_missing))
        ok_stale, reasons_stale = catalog_review.before_replace(
            "old-model",
            overlay,
            today=date(2026, 9, 3),
        )
        self.assertFalse(ok_stale)
        self.assertTrue(any("stale" in item for item in reasons_stale))

    def test_experimental_prefix_requires_flag(self) -> None:
        overlay = {
            "stale_days": 180,
            "reviews": {},
            "status_by_prefix": [
                {
                    "prefix": "studio-",
                    "status": "experimental",
                    "last_evaluated": "2026-08-27",
                }
            ],
        }
        ok, reasons = catalog_review.before_replace(
            "studio-z-image-turbo-nvfp4",
            overlay,
            today=date(2026, 9, 3),
        )
        self.assertFalse(ok)
        self.assertTrue(any("experimental" in item for item in reasons))
        allowed, _ = catalog_review.before_replace(
            "studio-z-image-turbo-nvfp4",
            overlay,
            allow_experimental=True,
            today=date(2026, 9, 3),
        )
        self.assertTrue(allowed)

    def test_station_overlay_covers_retained_chat_model(self) -> None:
        overlay = catalog_review.load_overlay(ROOT / "config/catalog-review.json")
        review = catalog_review.resolve_review(
            "qwen38-27b-q4",
            overlay,
            today=date(2026, 9, 3),
        )
        self.assertEqual(review.status, "active")
        self.assertFalse(review.stale)


class FaqContractTests(unittest.TestCase):
    def test_faq_covers_chat_rag_and_allowed_use(self) -> None:
        text = (ROOT / "docs/clients/FAQ.md").read_text(encoding="utf-8")
        for needle in (
            "http://127.0.0.1:3000",
            "http://127.0.0.1:4000/v1",
            "Knowledge",
            "allowed use",
            "SSO",
        ):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
