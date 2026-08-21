#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

from benchmarks.runners.run_document_golden import PERSIAN_RE, load_fixture_bytes


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "benchmarks/datasets/documents/04-persian-scan-placeholder.txt"


class DocumentGoldenFixtureTests(unittest.TestCase):
    def test_persian_fixture_is_ascii_in_source_and_decoded_in_memory(self) -> None:
        source = FIXTURE.read_text(encoding="ascii")
        self.assertIsNone(PERSIAN_RE.search(source))

        decoded = load_fixture_bytes(FIXTURE, decode_unicode_escapes=True).decode(
            "utf-8"
        )
        self.assertIsNotNone(PERSIAN_RE.search(decoded))
        self.assertIn("Platform Scope", decoded)
        self.assertIn("loopback-binding", decoded)


if __name__ == "__main__":
    unittest.main(verbosity=2)
