from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evaluation = _load("ocr_fixture_evaluation", ROOT / "benchmarks/runners/evaluate_ocr_result.py")
html_builder = _load("ocr_fixture_html", ROOT / "infra/paddleocr-vl/build_searchable_html.py")
quality = _load("ocr_fixture_quality", ROOT / "infra/paddleocr-vl/ocr_quality.py")


FIXTURE = ROOT / "benchmarks/fixtures/ocr/synthetic_bilingual.json"


class SyntheticOCRQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_has_full_bilingual_ground_truth_and_zero_error(self):
        result = evaluation.evaluate(self.fixture["structured"], self.fixture["truth"])
        self.assertEqual(result["page_coverage"], 1.0)
        self.assertEqual(result["cer"], 0)
        self.assertEqual(result["wer"], 0)
        self.assertTrue(result["promotion_allowed"])

    def test_fixture_canaries_are_numeric_and_page_scoped(self):
        pages = self.fixture["structured"]["pages"]
        results = quality.evaluate_canaries(pages, self.fixture["canaries"])
        self.assertEqual([item["passed"] for item in results], [True, True])
        wrong_page = quality.evaluate_canaries(pages, [{"page": 1, "expected": "Grade 60"}])
        self.assertEqual(wrong_page[0]["passed"], False)

    def test_fixture_html_contains_searchable_english_persian_and_escaped_text(self):
        pages = [
            {
                **page,
                "pixel_size": [800, 1000],
                "image": f"pages/page-{page['page_number']}.png",
                "search_text": page["text"],
            }
            for page in self.fixture["structured"]["pages"]
        ]
        rendered = html_builder.build_html("Synthetic OCR <quality>", pages)
        self.assertIn("Structural review", rendered)
        self.assertIn("\u062c\u0632\u0626\u06cc\u0627\u062a \u0627\u062a\u0635\u0627\u0644", rendered)
        self.assertIn("Synthetic OCR &lt;quality&gt;", rendered)
        self.assertIn('id="search-data"', rendered)
        self.assertIn('"normalized":"structural review \u2014 \u062a\u06cc\u0631 1403 load case 12: gravity + seismic"', rendered)

    def test_fixture_detects_a_deterministic_character_error(self):
        degraded = json.loads(json.dumps(self.fixture["structured"]))
        degraded["pages"][1]["text"] = degraded["pages"][1]["text"].replace("Grade", "Grdae")
        result = evaluation.evaluate(degraded, self.fixture["truth"])
        self.assertGreater(result["cer"], 0)
        self.assertGreater(result["wer"], 0)
        self.assertTrue(result["promotion_allowed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
