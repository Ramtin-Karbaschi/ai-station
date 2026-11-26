from __future__ import annotations

import asyncio
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.voice import service  # noqa: E402


class VoiceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(service.app)

    def test_health_and_model_aliases(self) -> None:
        health = self.client.get("/health").json()
        self.assertEqual(health["cpu_only"], True)
        self.assertEqual(set(health["assets"]), {"fa", "en"})
        ids = {row["id"] for row in self.client.get("/v1/models").json()["data"]}
        self.assertEqual(ids, {"fa", "en"})

    def test_rejects_unsupported_voice_and_format(self) -> None:
        bad_voice = self.client.post("/v1/audio/speech", json={"input": "hello", "voice": "unknown"})
        self.assertEqual(bad_voice.status_code, 400)
        bad_format = self.client.post("/v1/audio/speech", json={"input": "hello", "voice": "en", "response_format": "wav"})
        self.assertEqual(bad_format.status_code, 400)

    def test_returns_mp3_without_logging_or_provider_dependency(self) -> None:
        with patch.object(service.backend, "synthesize", return_value=b"ID3fixture") as synth:
            response = self.client.post(
                "/v1/audio/speech",
                json={"model": "piper", "input": "hello", "voice": "en"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/mpeg")
        self.assertTrue(response.content.startswith(b"ID3"))
        synth.assert_called_once_with("en", "hello", 1.0)

    def test_auto_and_mixed_explicit_turns_preserve_speed(self) -> None:
        with patch.object(service.backend, "synthesize", return_value=b"ID3fixture") as synth, patch.object(
            service.backend, "synthesize_runs", return_value=b"ID3fixture"
        ) as mixed_synth:
            auto = self.client.post(
                "/v1/audio/speech",
                json={"input": "\u0633\u0644\u0627\u0645 hello", "voice": "auto", "speed": 1.25},
            )
            mixed = self.client.post(
                "/v1/audio/speech",
                json={"input": "\u0633\u0644\u0627\u0645 hello", "voice": "fa", "speed": 0.75},
            )
        self.assertEqual(auto.status_code, 200)
        self.assertEqual(mixed.status_code, 200)
        self.assertEqual(mixed_synth.call_args.args, ([
            ("fa", "\u0633\u0644\u0627\u0645 "),
            ("en", "hello"),
        ], 1.25))
        self.assertEqual(synth.call_args.args, ("fa", "\u0633\u0644\u0627\u0645 hello", 0.75))

    def test_split_script_runs_keeps_neutral_text_with_previous_run(self) -> None:
        self.assertEqual(
            service.split_script_runs("\u0633\u0644\u0627\u0645 OpenAI 2026!", "fa"),
            [("fa", "\u0633\u0644\u0627\u0645 "), ("en", "OpenAI 2026!")],
        )

    def test_falls_back_to_one_voice_for_pathological_script_run_count(self) -> None:
        text = "\u0627a" * (service.MAX_SCRIPT_RUNS + 1)
        with patch.object(service.backend, "synthesize", return_value=b"ID3fixture") as synth:
            response = self.client.post("/v1/audio/speech", json={"input": text, "voice": "auto"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(synth.call_args.args, ("fa", text, 1.0))

    def test_rejects_non_string_voice_and_contradictory_explicit_language(self) -> None:
        non_string = self.client.post("/v1/audio/speech", json={"input": "hello", "voice": []})
        self.assertEqual(non_string.status_code, 400)
        contradictory = self.client.post("/v1/audio/speech", json={"input": "hello", "voice": "fa"})
        self.assertEqual(contradictory.status_code, 400)

    def test_timeout_keeps_concurrency_slot_until_worker_finishes(self) -> None:
        started = threading.Event()
        finish = threading.Event()
        old_timeout = service.SYNTHESIS_TIMEOUT_SECONDS

        def blocked(*args):
            started.set()
            finish.wait(2)
            return b"ID3fixture"

        async def exercise() -> tuple[int, int]:
            transport = httpx.ASGITransport(app=service.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                first = asyncio.create_task(
                    client.post("/v1/audio/speech", json={"input": "hello", "voice": "en"})
                )
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                await asyncio.sleep(0.03)
                second = await client.post(
                    "/v1/audio/speech", json={"input": "hello", "voice": "en"}
                )
                finish.set()
                return (second.status_code, (await first).status_code)

        service.SYNTHESIS_TIMEOUT_SECONDS = 0.01
        old_slots = service.slots
        service.slots = asyncio.Semaphore(1)
        try:
            with patch.object(service.backend, "synthesize", side_effect=blocked):
                second_code, first_code = asyncio.run(exercise())
            self.assertEqual(second_code, 429)
            self.assertEqual(first_code, 504)
        finally:
            service.SYNTHESIS_TIMEOUT_SECONDS = old_timeout
            service.slots = old_slots

    def test_enforces_input_bound(self) -> None:
        response = self.client.post(
            "/v1/audio/speech",
            json={"input": "x" * (service.MAX_TEXT_CHARS + 1), "voice": "fa"},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
