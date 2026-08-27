#!/usr/bin/env python3
from __future__ import annotations

import unittest

from apps.gateway.app.document_router import describe_pipeline, extract_document, classify_document
from apps.gateway.app.stt import Transcript, transcribe


def _tika_good(_b, _n, _m):
    return "Platform Scope loopback-binding benchmark-first pgvector-default " * 3


def _tika_empty(_b, _n, _m):
    return "[Tika extraction completed but no readable text was extracted. Last error: empty]"


def _paddle(_b, _n, _m):
    persian = "\u0641\u0627\u0631\u0633\u06cc"
    return f"PaddleOCR-VL table formula chart {persian} English mixed layout text recovered. " * 4


def _tess(_b, _n, _m):
    return "Tesseract fas+eng fallback text for a poor-quality Persian scan. " * 4


class DocumentRouterTests(unittest.TestCase):
    def test_pipeline_never_includes_reranker(self):
        p = describe_pipeline()
        self.assertEqual(p["never"], "reranker")
        self.assertEqual(p["digital"], "Apache Tika")

    def test_english_pdf_stays_on_tika(self):
        r = extract_document(b"%PDF", "en.pdf", "application/pdf", tika_fn=_tika_good, paddle_fn=_paddle, tesseract_fn=_tess, document_class="digital", paddle_available=True)
        self.assertEqual(r.engine, "tika")

    def test_scan_uses_paddle(self):
        r = extract_document(b"x", "scan.png", "image/png", tika_fn=_tika_empty, paddle_fn=_paddle, tesseract_fn=_tess, document_class="scanned_persian", paddle_available=True)
        self.assertEqual(r.engine, "paddleocr-vl-1.6")

    def test_complex_classes(self):
        for c in ("table", "formula", "chart", "screenshot", "rotated", "poor_scan", "mixed_persian_english"):
            r = extract_document(b"x", f"{c}.png", "image/png", tika_fn=_tika_empty, paddle_fn=_paddle, tesseract_fn=_tess, document_class=c, paddle_available=True)
            self.assertEqual(r.engine, "paddleocr-vl-1.6", c)

    def test_tesseract_fallback(self):
        r = extract_document(b"x", "scan.png", "image/png", tika_fn=_tika_empty, paddle_fn=_paddle, tesseract_fn=_tess, document_class="scanned_persian", paddle_available=False)
        self.assertEqual(r.engine, "tesseract")
        self.assertTrue(r.fallback_used)


class SttRouterTests(unittest.TestCase):
    def test_qwen_primary(self):
        def qwen(_b, lang):
            return Transcript("\u0633\u0644\u0627\u0645", "qwen3-asr-1.7b", lang, None, False, "ok")
        def whisper(_b, lang):
            return Transcript("w", "faster-whisper-large-v3", lang, [{"start": 0}], True, "ok")
        r = transcribe(b"x", language="fa", qwen_available=True, qwen_fn=qwen, whisper_fn=whisper)
        self.assertEqual(r.engine, "qwen3-asr-1.7b")

    def test_timestamp_whisper(self):
        def qwen(_b, lang):
            return Transcript("x", "qwen3-asr-1.7b", lang, None, False, "ok")
        def whisper(_b, lang):
            return Transcript("w", "faster-whisper-large-v3", lang, [{"start": 0}], True, "ok")
        r = transcribe(b"x", want_timestamps=True, qwen_available=True, qwen_fn=qwen, whisper_fn=whisper)
        self.assertEqual(r.engine, "faster-whisper-large-v3")


class GatewaySttRouteTests(unittest.TestCase):
    def test_host_gateway_exposes_transcriptions(self) -> None:
        from apps.gateway.app import main as gateway_main

        paths = {getattr(route, "path", None) for route in gateway_main.app.routes}
        self.assertIn("/v1/audio/transcriptions", paths)


if __name__ == "__main__":
    unittest.main(verbosity=2)
