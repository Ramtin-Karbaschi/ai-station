#!/usr/bin/env python3
from __future__ import annotations

import unittest

from email.parser import BytesParser
from email.policy import default

from apps.gateway.app.document_router import describe_pipeline, extract_document, classify_document
from apps.gateway.app.stt import (
    ASR_MULTIPART_BOUNDARY,
    CALL_ASR_UPSTREAM_MODEL,
    Transcript,
    _asr_multipart_body,
    clean_qwen_text,
    extract_audio_request,
    normalize_language,
    transcribe,
)


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

    def test_stt_language_normalizes_locale_and_auto(self):
        self.assertEqual(normalize_language("fa-IR"), "fa")
        self.assertEqual(normalize_language("en_US"), "en")
        self.assertIsNone(normalize_language("auto"))

    def test_stt_rejects_malformed_language_hint(self):
        with self.assertRaises(ValueError):
            normalize_language("fa; rm -rf")

    def test_stt_cleans_qwen_metadata_wrapper(self):
        self.assertEqual(
            clean_qwen_text("language English<asr_text>Say hello in English."),
            "Say hello in English.",
        )

    def test_stt_extracts_openai_multipart_file_and_language(self):
        boundary = "client-boundary"
        body = _asr_multipart_body(b"RIFF\x00\xffWAVE", "fa-IR", boundary=boundary)
        audio, language, model = extract_audio_request(
            body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        self.assertEqual(audio, b"RIFF\x00\xffWAVE")
        self.assertEqual(language, "fa")
        self.assertIsNone(model)

    def test_stt_raw_body_preserves_explicit_language_precedence(self):
        audio, language, model = extract_audio_request(
            b"audio", content_type="audio/wav", language="en-US"
        )
        self.assertEqual(audio, b"audio")
        self.assertEqual(language, "en")
        self.assertIsNone(model)

    def test_stt_extracts_internal_upstream_model_marker(self):
        boundary = "call-route-boundary"
        body = _asr_multipart_body(b"AUDIO", None, boundary=boundary).replace(
            f"--{boundary}--\r\n".encode(),
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n'
                f"{CALL_ASR_UPSTREAM_MODEL}\r\n"
                f"--{boundary}--\r\n"
            ).encode(),
        )
        audio, language, model = extract_audio_request(
            body, content_type=f"multipart/form-data; boundary={boundary}"
        )
        self.assertEqual(audio, b"AUDIO")
        self.assertIsNone(language)
        self.assertEqual(model, CALL_ASR_UPSTREAM_MODEL)

    def test_english_pdf_stays_on_tika(self):
        r = extract_document(b"%PDF", "en.pdf", "application/pdf", tika_fn=_tika_good, paddle_fn=_paddle, tesseract_fn=_tess, document_class="digital", paddle_available=True)
        self.assertEqual(r.engine, "tika")

    def test_scan_uses_paddle(self):
        r = extract_document(b"x", "scan.png", "image/png", tika_fn=_tika_empty, paddle_fn=_paddle, tesseract_fn=_tess, document_class="scanned_persian", paddle_available=True)
        self.assertEqual(r.engine, "paddleocr-vl-1.6")

    def test_complex_hint_on_digital_pdf_skips_tika(self):
        r = extract_document(
            b"%PDF",
            "scan.pdf",
            "application/pdf",
            tika_fn=_tika_good,
            paddle_fn=_paddle,
            tesseract_fn=_tess,
            document_class="scanned_persian",
            paddle_available=True,
        )
        self.assertEqual(r.engine, "paddleocr-vl-1.6")
        self.assertEqual(r.document_class, "scanned_persian")
        self.assertFalse(r.fallback_used)

    def test_complex_classes(self):
        for c in ("table", "formula", "chart", "screenshot", "rotated", "poor_scan", "mixed_persian_english"):
            r = extract_document(b"x", f"{c}.png", "image/png", tika_fn=_tika_empty, paddle_fn=_paddle, tesseract_fn=_tess, document_class=c, paddle_available=True)
            self.assertEqual(r.engine, "paddleocr-vl-1.6", c)

    def test_tesseract_fallback(self):
        r = extract_document(b"x", "scan.png", "image/png", tika_fn=_tika_empty, paddle_fn=_paddle, tesseract_fn=_tess, document_class="scanned_persian", paddle_available=False)
        self.assertEqual(r.engine, "tesseract")
        self.assertTrue(r.fallback_used)

    def test_tika_ocr_fallback_when_no_distinct_tesseract(self):
        r = extract_document(
            b"x",
            "scan.png",
            "image/png",
            tika_fn=_tika_empty,
            paddle_fn=_paddle,
            tesseract_fn=None,
            document_class="scanned_persian",
            paddle_available=False,
        )
        self.assertEqual(r.engine, "tika-ocr")
        self.assertTrue(r.fallback_used)

    def test_tika_passed_as_tesseract_fn_labels_tika_ocr(self):
        r = extract_document(
            b"x",
            "scan.png",
            "image/png",
            tika_fn=_tika_empty,
            paddle_fn=_paddle,
            tesseract_fn=_tika_empty,
            document_class="scanned_persian",
            paddle_available=False,
        )
        self.assertEqual(r.engine, "tika-ocr")
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
        self.assertFalse(r.fallback_used)

    def test_call_route_uses_whisper_first(self):
        calls = []
        def qwen(_b, lang):
            calls.append("qwen")
            return Transcript("qwen", "qwen3-asr-1.7b", lang, None, False, "ok")
        def whisper(_b, lang):
            calls.append("whisper")
            return Transcript("whisper", "faster-whisper-large-v3", lang, [], False, "ok")
        r = transcribe(
            b"audio", language="fa", whisper_primary=True, qwen_available=True,
            qwen_fn=qwen, whisper_fn=whisper,
        )
        self.assertEqual(calls, ["whisper"])
        self.assertEqual(r.engine, "faster-whisper-large-v3")
        self.assertEqual(r.text, "whisper")
        self.assertFalse(r.fallback_used)

    def test_call_route_falls_back_to_qwen_if_whisper_fails(self):
        calls = []
        def qwen(_b, lang):
            calls.append("qwen")
            return Transcript("qwen", "qwen3-asr-1.7b", lang, None, False, "ok")
        def whisper(_b, _lang):
            calls.append("whisper")
            raise RuntimeError("whisper unavailable")
        r = transcribe(
            b"audio", language="fa", whisper_primary=True, qwen_available=True,
            qwen_fn=qwen, whisper_fn=whisper,
        )
        self.assertEqual(calls, ["whisper", "qwen"])
        self.assertEqual(r.engine, "qwen3-asr-1.7b")
        self.assertTrue(r.fallback_used)
        self.assertEqual(r.reason, "Whisper failed: RuntimeError")

    def test_generic_timestamp_whisper_does_not_change_fallback_policy(self):
        def qwen(_b, lang):
            raise AssertionError("generic timestamp mode must not call Qwen")
        def whisper(_b, _lang):
            raise RuntimeError("whisper unavailable")
        with self.assertRaisesRegex(RuntimeError, "whisper unavailable"):
            transcribe(
                b"audio", want_timestamps=True, qwen_available=True,
                qwen_fn=qwen, whisper_fn=whisper,
            )

    def test_whisper_primary_when_qwen_unavailable(self):
        def qwen(_b, lang):
            raise AssertionError("Qwen must not run when unavailable")
        def whisper(_b, lang):
            return Transcript("w", "faster-whisper-large-v3", lang, None, False, "ok")
        r = transcribe(b"x", qwen_available=False, qwen_fn=qwen, whisper_fn=whisper)
        self.assertEqual(r.engine, "faster-whisper-large-v3")
        self.assertFalse(r.fallback_used)

    def test_whisper_is_fallback_when_qwen_fails(self):
        def qwen(_b, lang):
            raise RuntimeError("asr down")
        def whisper(_b, lang):
            return Transcript("w", "faster-whisper-large-v3", lang, None, False, "ok")
        r = transcribe(b"x", qwen_available=True, qwen_fn=qwen, whisper_fn=whisper)
        self.assertEqual(r.engine, "faster-whisper-large-v3")
        self.assertTrue(r.fallback_used)

    def _parse_asr_multipart(self, body: bytes):
        envelope = (
            f"Content-Type: multipart/form-data; boundary={ASR_MULTIPART_BOUNDARY}\r\n\r\n"
        ).encode("utf-8") + body
        return BytesParser(policy=default).parsebytes(envelope)

    def test_asr_multipart_language_has_own_boundary(self):
        body = _asr_multipart_body(b"AUDIO", "fa")
        delimiter = f"--{ASR_MULTIPART_BOUNDARY}\r\n".encode("utf-8")
        closer = f"--{ASR_MULTIPART_BOUNDARY}--\r\n".encode("utf-8")
        self.assertTrue(body.startswith(delimiter))
        self.assertIn(
            delimiter + b'Content-Disposition: form-data; name="language"\r\n',
            body,
        )
        self.assertTrue(body.endswith(closer))
        msg = self._parse_asr_multipart(body)
        parts = list(msg.iter_parts())
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0].get_param("name", header="content-disposition"), "file")
        self.assertEqual(parts[0].get_payload(decode=True), b"AUDIO")
        self.assertEqual(parts[1].get_param("name", header="content-disposition"), "language")
        self.assertEqual(parts[1].get_payload(decode=True), b"fa")

    def test_asr_multipart_crlf_precedes_boundary_after_binary_audio(self):
        audio = b"RIFF\x00\xff\r\n\x1aWAVEfmt"
        body = _asr_multipart_body(audio, "fa")
        start = body.find(audio)
        self.assertNotEqual(start, -1)
        after = body[start + len(audio) :]
        next_part = f"\r\n--{ASR_MULTIPART_BOUNDARY}\r\n".encode("utf-8")
        self.assertTrue(after.startswith(next_part), after[:48])
        msg = self._parse_asr_multipart(body)
        parts = list(msg.iter_parts())
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0].get_payload(decode=True), audio)
        self.assertEqual(parts[1].get_payload(decode=True), b"fa")

    def test_asr_multipart_without_language_has_no_empty_part(self):
        body = _asr_multipart_body(b"AUDIO", None)
        delimiter = f"--{ASR_MULTIPART_BOUNDARY}\r\n".encode("utf-8")
        closer = f"--{ASR_MULTIPART_BOUNDARY}--\r\n".encode("utf-8")
        self.assertEqual(body.count(delimiter), 1)
        self.assertNotIn(b'name="language"', body)
        self.assertTrue(body.endswith(closer))
        msg = self._parse_asr_multipart(body)
        parts = list(msg.iter_parts())
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].get_payload(decode=True), b"AUDIO")


class GatewaySttRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_alias_upstream_model_selects_whisper_primary(self) -> None:
        import httpx

        from apps.gateway.app import main as gateway_main

        seen = {}

        def fake_transcribe(audio, **kwargs):
            seen["audio"] = audio
            seen.update(kwargs)
            return Transcript(
                "synthetic transcript",
                "faster-whisper-large-v3",
                "fa",
                [],
                False,
                "call transcription",
            )

        original = gateway_main.transcribe_station_audio
        gateway_main.transcribe_station_audio = fake_transcribe
        try:
            transport = httpx.ASGITransport(app=gateway_main.app)
            boundary = "route-selection-boundary"
            body = _asr_multipart_body(b"SYNTHETIC", "fa", boundary=boundary).replace(
                f"--{boundary}--\r\n".encode(),
                (
                    f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n'
                    f"{CALL_ASR_UPSTREAM_MODEL}\r\n"
                    f"--{boundary}--\r\n"
                ).encode(),
            )
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                response = await client.post(
                    "/v1/audio/transcriptions",
                    content=body,
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(seen["audio"], b"SYNTHETIC")
            self.assertEqual(seen["language"], "fa")
            self.assertFalse(seen["want_timestamps"])
            self.assertTrue(seen["whisper_primary"])
        finally:
            gateway_main.transcribe_station_audio = original

    async def test_host_gateway_exposes_transcriptions(self) -> None:
        import httpx

        from apps.gateway.app import main as gateway_main

        paths = {getattr(route, "path", None) for route in gateway_main.app.routes}
        self.assertIn("/v1/audio/transcriptions", paths)
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            empty = await client.post("/v1/audio/transcriptions", content=b"")
        self.assertEqual(empty.status_code, 400)

    async def test_host_gateway_speech_is_pending_smoke(self) -> None:
        import httpx

        from apps.gateway.app import main as gateway_main

        paths = {getattr(route, "path", None) for route in gateway_main.app.routes}
        self.assertIn("/v1/audio/speech", paths)
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.post("/v1/audio/speech", content=b"{}")
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "pending_smoke")
        self.assertEqual(body["error"], "tts_pending_smoke")


if __name__ == "__main__":
    unittest.main(verbosity=2)
