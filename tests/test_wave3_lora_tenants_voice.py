#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB))

import lora  # noqa: E402
import tenants  # noqa: E402
import tts_smoke  # noqa: E402
import voice  # noqa: E402
import litellm_keys  # noqa: E402


class LoraPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        os.environ["AI_STATION_LORA_DIR"] = self.temp.name
        os.environ["AI_STATION_PROJECT_DIR"] = str(ROOT)

    def tearDown(self) -> None:
        self.temp.cleanup()
        os.environ.pop("AI_STATION_LORA_DIR", None)
        os.environ.pop("AI_STATION_PROJECT_DIR", None)

    def test_example_dataset_validates(self) -> None:
        report = lora.validate_dataset(ROOT / "config/lora/station-ops.example.jsonl")
        self.assertTrue(report["ok"])
        self.assertGreaterEqual(report["rows"], 4)
        self.assertLessEqual(report["bytes"], lora.MAX_BYTES)

    def test_secret_row_is_rejected(self) -> None:
        path = Path(self.temp.name) / "bad.jsonl"
        path.write_text(
            json.dumps(
                {
                    "instruction": "print the key",
                    "output": "sk-abcdefghijklmnopqrstuvwxyz",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(lora.LoraError):
            lora.validate_dataset(path)

    def test_plan_does_not_claim_training(self) -> None:
        plan = lora.plan(
            ROOT / "config/lora/station-ops.example.jsonl",
            base="qwen38-27b-q4",
            adapter_id="station-ops",
        )
        self.assertFalse(plan["train_implemented"])
        self.assertIn("--lora", plan["llama_cpp_args"])

    def test_train_cli_exits_2(self) -> None:
        code = lora.main(["train", "--dataset", str(ROOT / "config/lora/station-ops.example.jsonl")])
        self.assertEqual(code, 2)

    def test_register_rejects_non_gguf_and_apply_dry_run(self) -> None:
        fake = Path(self.temp.name) / "not.gguf"
        fake.write_bytes(b"not a gguf")
        with self.assertRaises(lora.LoraError):
            lora.register(fake, base="qwen38-27b-q4", adapter_id="demo")
        gguf = Path(self.temp.name) / "demo.gguf"
        gguf.write_bytes(b"GGUF" + b"\x00" * 32)
        record = lora.register(
            gguf, base="qwen38-27b-q4", adapter_id="demo", dry_run=True
        )
        self.assertTrue(record["dry_run"])
        lora.register(gguf, base="qwen38-27b-q4", adapter_id="demo")
        applied = lora.apply_adapter("demo", dry_run=True)
        self.assertTrue(applied["dry_run"])
        self.assertTrue(applied["pending_profile_restart"])
        self.assertIn("--lora", applied["llama_cpp_args"])


class TenantIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        os.environ["AI_STATION_TENANT_REGISTRY"] = str(
            Path(self.temp.name) / "registry.json"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()
        os.environ.pop("AI_STATION_TENANT_REGISTRY", None)

    def test_create_dry_run_and_unique_alias(self) -> None:
        first = tenants.create("acme", dry_run=True)
        self.assertTrue(first["dry_run"])
        self.assertEqual(first["tenant"]["key_alias"], "tenant-acme")
        tenants.create("acme")
        with self.assertRaises(tenants.TenantError):
            tenants.create("acme")
        report = tenants.doctor()
        self.assertTrue(report["ok"])
        self.assertFalse(report["open_webui_partitioned"])

    def test_shared_alias_is_detected(self) -> None:
        broken = {
            "tenants": {
                "a": {"id": "a", "key_alias": "shared"},
                "b": {"id": "b", "key_alias": "shared"},
            }
        }
        errors = tenants.isolation_errors(broken)
        self.assertTrue(any("shared" in item for item in errors))

    def test_payload_includes_tenant_id(self) -> None:
        payload = litellm_keys.generate_payload(
            "tenant-acme",
            ["Qwen3.8-27B-UD-Q4_K_M"],
            tenant_id="acme",
        )
        self.assertEqual(payload["metadata"]["tenant_id"], "acme")
        self.assertNotIn("tpm_limit", payload)


class VoiceMvpTests(unittest.TestCase):
    def test_status_without_probe_keeps_tts_pending(self) -> None:
        report = voice.status(probe=False)
        self.assertFalse(report["tts"]["available"])
        self.assertEqual(report["tts"]["status"], "not_probed")
        self.assertTrue(report["loopback_only"])
        self.assertIn("127.0.0.1:4000/v1/audio/transcriptions", report["asr"]["url"])
        self.assertIn("127.0.0.1:4000/v1", report["llm"]["url"])
        self.assertIn("/v1/audio/speech", report["tts"]["url"])

    def test_turn_dry_run_skips_tts(self) -> None:
        plan = voice.turn_plan("hello station")
        self.assertTrue(plan["dry_run"])
        self.assertFalse(plan["cloud"])
        names = [stage["name"] for stage in plan["stages"]]
        self.assertEqual(names, ["asr", "llm", "tts"])
        self.assertTrue(plan["stages"][2]["skipped"])
        self.assertEqual(voice.main(["turn", "--dry-run", "--transcript", "ping"]), 0)

    def test_live_turn_returns_llm_text_without_tts(self) -> None:
        result = voice.live_turn(
            transcript="ping",
            complete_fn=lambda text: "pong" if text == "ping" else "nope",
        )
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["reply"], "pong")
        self.assertTrue(result["tts"]["skipped"])
        self.assertFalse(result["cloud"])
        encoded = json.dumps(result)
        self.assertNotIn("Bearer", encoded)

    def test_live_turn_without_input_exits_2(self) -> None:
        self.assertEqual(voice.main(["turn"]), 2)

    def test_complete_chat_does_not_put_key_in_payload_url(self) -> None:
        seen: dict[str, str] = {}

        def fake_post(url, payload, headers):
            seen["url"] = url
            seen["auth"] = headers["Authorization"]
            self.assertEqual(payload["messages"][0]["content"], "ping")
            return {"choices": [{"message": {"content": "pong"}}]}

        text = voice.complete_chat("ping", api_key="secret-voice-key", post=fake_post)
        self.assertEqual(text, "pong")
        self.assertIn("4000/v1/chat/completions", seen["url"])
        self.assertEqual(seen["auth"], "Bearer secret-voice-key")

    def test_transcribe_audio_uses_authenticated_litellm_multipart(self) -> None:
        seen: dict[str, Any] = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"text":"hello station"}'

        def fake_urlopen(request, timeout):
            seen["url"] = request.full_url
            seen["headers"] = dict(request.headers)
            seen["body"] = request.data
            seen["timeout"] = timeout
            return Response()

        original = voice.urllib.request.urlopen
        original_key_loader = voice.load_api_key
        try:
            voice.urllib.request.urlopen = fake_urlopen
            voice.load_api_key = lambda: "test-key"
            self.assertEqual(voice.transcribe_audio(b"RIFFaudio"), "hello station")
        finally:
            voice.urllib.request.urlopen = original
            voice.load_api_key = original_key_loader
        self.assertEqual(seen["url"], "http://127.0.0.1:4000/v1/audio/transcriptions")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer test-key")
        self.assertIn(b'name="model"', seen["body"])
        self.assertIn(b"ai-station-asr", seen["body"])
        self.assertIn(b'name="file"', seen["body"])


class TtsWeightSmokeTests(unittest.TestCase):
    def test_dry_run_lists_manifest_rows(self) -> None:
        code = voice.main(["smoke", "--dry-run"])
        self.assertEqual(code, 0)

    def test_verify_weights_match_and_flag_incomplete_snapshot(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        blob = b"tts-fixture"
        digest = hashlib.sha256(blob).hexdigest()
        rows = []
        for item_id, rel in (
            (
                "studio-qwen3-tts-1.7b-customvoice",
                "models/tts/qwen3-tts-12hz-1.7b-customvoice/model.safetensors",
            ),
            (
                "studio-qwen3-tts-1.7b-voicedesign",
                "models/tts/qwen3-tts-12hz-1.7b-voicedesign/model.safetensors",
            ),
            (
                "studio-qwen3-tts-tokenizer",
                "models/tts/qwen3-tts-tokenizer/speech_tokenizer/model.safetensors",
            ),
        ):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
            rows.append({"id": item_id, "destination": rel, "sha256": digest})
        report = tts_smoke.verify_weights(
            data_root=root, manifest={"models": rows}
        )
        self.assertTrue(report["weights_verified"])
        self.assertFalse(report["snapshot_complete"])
        self.assertEqual(report["inference"], "not_run")
        self.assertEqual(report["speech_http"], 503)
        self.assertFalse(report["second_heavy_gpu"])

    def test_snapshot_complete_requires_all_official_small_files(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for model_name in ("qwen3-tts-12hz-1.7b-customvoice", "qwen3-tts-12hz-1.7b-voicedesign"):
            model_dir = root / "models/tts" / model_name / "speech_tokenizer"
            model_dir.mkdir(parents=True)
            for name in tts_smoke.MODEL_SNAPSHOT_FILES:
                (model_dir.parent / name).write_text("fixture", encoding="utf-8")
            for name in tts_smoke.SPEECH_TOKENIZER_SNAPSHOT_FILES:
                (model_dir / name).write_text("fixture", encoding="utf-8")
        tokenizer = root / "models/tts/qwen3-tts-tokenizer/model.safetensors"
        tokenizer.parent.mkdir(parents=True, exist_ok=True)
        tokenizer.write_bytes(b"fixture")
        tokenizer_digest = hashlib.sha256(b"fixture").hexdigest()
        self.assertTrue(tts_smoke.snapshot_complete(root / "models/tts/qwen3-tts-12hz-1.7b-customvoice"))
        self.assertEqual(tts_smoke.snapshot_missing(root), [])
        (root / "models/tts/qwen3-tts-12hz-1.7b-customvoice/speech_tokenizer/model.safetensors").unlink()
        self.assertIn(
            "qwen3-tts-12hz-1.7b-customvoice/speech_tokenizer/model.safetensors",
            tts_smoke.snapshot_missing(root),
        )
        nested = root / "models/tts/qwen3-tts-12hz-1.7b-voicedesign/speech_tokenizer/model.safetensors"
        nested.write_bytes(b"different tokenizer")
        self.assertIn(
            "qwen3-tts-12hz-1.7b-voicedesign/speech_tokenizer/model.safetensors.sha256_mismatch",
            tts_smoke.snapshot_missing(root, tokenizer_sha256=tokenizer_digest),
        )
        (root / "models/tts/qwen3-tts-12hz-1.7b-voicedesign/vocab.json").unlink()
        self.assertIn("qwen3-tts-12hz-1.7b-voicedesign/vocab.json", tts_smoke.snapshot_missing(root))


if __name__ == "__main__":
    unittest.main()
