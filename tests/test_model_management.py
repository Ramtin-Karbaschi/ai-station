#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "scripts/model_manager.py"
PROVISIONER = ROOT / "scripts/model_provision.py"
MANIFEST = ROOT / "config/model-manifest.json"
CODER_ID = "coder-qwen3-30b-a3b-q4"
EMBED_ID = "embedding-qwen3-0.6b-q8"


def _load_provisioner():
    spec = importlib.util.spec_from_file_location("model_provision", PROVISIONER)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load scripts/model_provision.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _HubStub(types.ModuleType):
    def __init__(self, download):
        super().__init__("huggingface_hub")
        self.hf_hub_download = download


class ModelManagementTests(unittest.TestCase):
    def test_provisioner_help_and_list_need_no_huggingface_dependency(self) -> None:
        help_result = subprocess.run(
            ["python3", str(PROVISIONER), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("--id", help_result.stdout)
        listed = subprocess.run(
            [
                "python3",
                str(PROVISIONER),
                "--manifest",
                str(MANIFEST),
                "--data-root",
                "/tmp/ai-station-model-test-does-not-exist",
                "--id",
                CODER_ID,
                "--list",
                "--json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        rows = json.loads(listed.stdout)
        self.assertEqual([row["id"] for row in rows], [CODER_ID])

    def test_quarantine_is_dry_run_by_default_and_reversible(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        model = next(item for item in manifest["models"] if item["id"] == CODER_ID)
        with tempfile.TemporaryDirectory() as directory:
            data_root = Path(directory)
            model_path = data_root / model["destination"]
            model_path.parent.mkdir(parents=True)
            model_path.write_bytes(b"fixture")

            dry_run = subprocess.run(
                [str(MANAGER), "--data-root", directory, "quarantine", CODER_ID],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("DRY-RUN", dry_run.stdout)
            self.assertTrue(model_path.is_file())

            subprocess.run(
                [
                    str(MANAGER),
                    "--data-root",
                    directory,
                    "quarantine",
                    CODER_ID,
                    "--confirm",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertFalse(model_path.exists())

            subprocess.run(
                [
                    str(MANAGER),
                    "--data-root",
                    directory,
                    "restore",
                    CODER_ID,
                    "--confirm",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(model_path.read_bytes(), b"fixture")

    def test_quarantine_refuses_required_core_without_allow_required(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        model = next(item for item in manifest["models"] if item["id"] == EMBED_ID)
        self.assertTrue(model.get("required_for_runtime"))
        with tempfile.TemporaryDirectory() as directory:
            data_root = Path(directory)
            model_path = data_root / model["destination"]
            model_path.parent.mkdir(parents=True)
            model_path.write_bytes(b"fixture")
            refused = subprocess.run(
                [str(MANAGER), "--data-root", directory, "quarantine", EMBED_ID, "--confirm"],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("--allow-required", refused.stderr)
            self.assertTrue(model_path.is_file())

    def test_add_is_dry_run_by_default_and_writes_only_with_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            shutil.copytree(ROOT / "config", work / "config")
            add_args = [
                str(MANAGER),
                "--root",
                str(work),
                "add",
                "--id",
                "custom-test-q4",
                "--repo",
                "org/name",
                "--filename",
                "model.gguf",
                "--role",
                "general",
                "--revision",
                "0123456789abcdef0123456789abcdef01234567",
            ]
            dry = subprocess.run(add_args, check=True, capture_output=True, text=True)
            self.assertIn("DRY-RUN", dry.stdout)
            original = json.loads((ROOT / "config/model-manifest.json").read_text(encoding="utf-8"))
            copied = json.loads((work / "config/model-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [item["id"] for item in copied["models"]],
                [item["id"] for item in original["models"]],
            )

            mutable = subprocess.run(
                [
                    str(MANAGER),
                    "--root",
                    str(work),
                    "add",
                    "--id",
                    "custom-mutable-q4",
                    "--repo",
                    "org/name",
                    "--filename",
                    "model.gguf",
                    "--role",
                    "general",
                    "--revision",
                    "main",
                    "--confirm",
                    "--sha256",
                    "a" * 64,
                    "--size-bytes",
                    "8",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(mutable.returncode, 0)

            written = subprocess.run(
                add_args
                + [
                    "--confirm",
                    "--sha256",
                    "ab" * 32,
                    "--size-bytes",
                    "8",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("OK: manifest entry written", written.stdout)
            updated = json.loads((work / "config/model-manifest.json").read_text(encoding="utf-8"))
            entry = next(item for item in updated["models"] if item["id"] == "custom-test-q4")
            self.assertEqual(entry["repo_id"], "org/name")
            self.assertEqual(entry["profiles"], ["custom"])
            self.assertFalse(entry["required_for_runtime"])
            duplicate = subprocess.run(
                add_args + ["--confirm", "--sha256", "ab" * 32, "--size-bytes", "8"],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("already exists", duplicate.stderr)

    def test_provisioner_sets_hub_timeouts_without_overwriting(self) -> None:
        provisioner = _load_provisioner()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HF_HUB_DOWNLOAD_TIMEOUT", None)
            os.environ.pop("HF_HUB_ETAG_TIMEOUT", None)
            os.environ.pop("HF_XET_HIGH_PERFORMANCE", None)
            provisioner.configure_hub_client()
            self.assertEqual(os.environ["HF_HUB_DOWNLOAD_TIMEOUT"], "600")
            self.assertEqual(os.environ["HF_HUB_ETAG_TIMEOUT"], "120")
            self.assertEqual(os.environ["HF_XET_HIGH_PERFORMANCE"], "1")
        with patch.dict(
            os.environ,
            {
                "HF_HUB_DOWNLOAD_TIMEOUT": "90",
                "HF_HUB_ETAG_TIMEOUT": "15",
                "HF_XET_HIGH_PERFORMANCE": "0",
            },
        ):
            provisioner.configure_hub_client()
            self.assertEqual(os.environ["HF_HUB_DOWNLOAD_TIMEOUT"], "90")
            self.assertEqual(os.environ["HF_HUB_ETAG_TIMEOUT"], "15")
            self.assertEqual(os.environ["HF_XET_HIGH_PERFORMANCE"], "0")

    def test_stale_hub_locks_are_cleared_for_one_repo(self) -> None:
        provisioner = _load_provisioner()
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            mine = cache / ".locks" / "models--org--name"
            other = cache / ".locks" / "models--other--repo"
            mine.mkdir(parents=True)
            other.mkdir(parents=True)
            (mine / "abc.lock").write_text("stale", encoding="utf-8")
            (other / "xyz.lock").write_text("keep", encoding="utf-8")
            removed = provisioner.clear_stale_hub_locks(cache, "org/name")
            self.assertEqual(removed, 1)
            self.assertFalse((mine / "abc.lock").exists())
            self.assertTrue((other / "xyz.lock").is_file())

    def test_incomplete_destination_resumes_over_http_not_quarantine(self) -> None:
        provisioner = _load_provisioner()
        payload = b"complete!"
        model = {
            "id": "fixture-q4",
            "repo_id": "org/name",
            "revision": "abc123",
            "filename": "model.gguf",
            "destination": "models/custom/model.gguf",
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        with tempfile.TemporaryDirectory() as directory:
            data_root = Path(directory)
            dest = data_root / model["destination"]
            dest.parent.mkdir(parents=True)
            dest.write_bytes(b"part")

            def fake_http(url, path, token=None, user_agent="ai-station-provisioner"):
                self.assertIn("org/name/resolve/abc123/model.gguf", url)
                path.write_bytes(payload)

            with patch.object(
                provisioner,
                "http_resume_download",
                side_effect=fake_http,
            ):
                provisioner.install_model(
                    model,
                    data_root,
                    data_root / "cache",
                    None,
                )
            self.assertEqual(dest.read_bytes(), payload)
            self.assertEqual(list(dest.parent.glob("*.invalid-*")), [])

    def test_full_size_invalid_destination_is_quarantined(self) -> None:
        provisioner = _load_provisioner()
        payload = b"complete!"
        model = {
            "id": "fixture-q4",
            "repo_id": "org/name",
            "revision": "abc123",
            "filename": "model.gguf",
            "destination": "models/custom/model.gguf",
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        with tempfile.TemporaryDirectory() as directory:
            data_root = Path(directory)
            dest = data_root / model["destination"]
            dest.parent.mkdir(parents=True)
            dest.write_bytes(b"COMPLETE!")
            cache_blob = data_root / "cache" / "blob"
            cache_blob.parent.mkdir(parents=True)
            cache_blob.write_bytes(payload)

            def fake_hub(**kwargs):
                return str(cache_blob)

            with patch.dict("sys.modules", {"huggingface_hub": _HubStub(fake_hub)}):
                provisioner.install_model(
                    model,
                    data_root,
                    data_root / "cache",
                    None,
                )
            self.assertEqual(dest.read_bytes(), payload)
            quarantined = list(dest.parent.glob("model.gguf.invalid-*"))
            self.assertEqual(len(quarantined), 1)
            self.assertEqual(quarantined[0].read_bytes(), b"COMPLETE!")

    def test_retryable_timeout_errors_are_detected(self) -> None:
        provisioner = _load_provisioner()
        self.assertTrue(
            provisioner.is_retryable_download_error(
                TimeoutError("The read operation timed out")
            )
        )
        self.assertFalse(
            provisioner.is_retryable_download_error(
                RuntimeError("Downloaded model checksum is invalid")
            )
        )

    def test_provision_models_exports_hub_timeouts(self) -> None:
        script = (ROOT / "scripts/provision-models.sh").read_text(encoding="utf-8")
        self.assertIn("HF_HUB_DOWNLOAD_TIMEOUT", script)
        self.assertIn("HF_HUB_ETAG_TIMEOUT", script)
        self.assertIn("HF_XET_HIGH_PERFORMANCE", script)

    def test_cli_exposes_curated_storage_lifecycle(self) -> None:
        cli = (ROOT / "scripts/ai").read_text(encoding="utf-8")
        models_lib = (ROOT / "scripts/lib/ai-models.sh").read_text(encoding="utf-8")
        self.assertIn('source "$ROOT/scripts/lib/ai-models.sh"', cli)
        for needle in (
            "cmd_models_catalog",
            "cmd_models_add",
            "cmd_models_install",
            "cmd_models_verify",
            "cmd_models_remove",
            "cmd_models_restore",
        ):
            self.assertIn(needle, models_lib)


if __name__ == "__main__":
    unittest.main(verbosity=2)
