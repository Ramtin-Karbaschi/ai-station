#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sys
import subprocess
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(ROOT / "scripts"))

import restore_dry_run  # noqa: E402
import retention  # noqa: E402
import station_alerts  # noqa: E402
import litellm_keys  # noqa: E402


def _sha256sums(backup: Path, names: tuple[str, ...]) -> None:
    lines = []
    for name in names:
        digest = hashlib.sha256((backup / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {backup / name}")
    (backup / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_tar(path: Path, members: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def _station_backup(root: Path, backup_id: str = "20260902-120000") -> Path:
    backup = root / "backups" / backup_id
    backup.mkdir(parents=True)
    (backup / "ai_station_postgres.dump").write_bytes(b"PGDMP\x00fixture")
    _write_tar(
        backup / "ai_station_files.tar.gz",
        {"uploads/note.txt": b"hello", "artifacts/keep.txt": b"ok"},
    )
    (backup / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    (backup / "env.example").write_text("EXAMPLE=1\n", encoding="utf-8")
    _sha256sums(
        backup,
        (
            "ai_station_postgres.dump",
            "ai_station_files.tar.gz",
            "compose.yml",
            "env.example",
        ),
    )
    return backup


class RestoreDryRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        os.environ["AI_STATION_DATA"] = str(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()
        os.environ.pop("AI_STATION_DATA", None)

    def test_latest_fixture_is_restorable(self) -> None:
        backup = _station_backup(self.root)

        def lister(path: Path) -> tuple[int, str]:
            self.assertEqual(path, backup / "ai_station_postgres.dump")
            return 0, "; Archive TOC\n"

        report = restore_dry_run.dry_run(backup, dump_lister=lister)
        self.assertTrue(report["restorable"])
        self.assertTrue(report["checksums_ok"])
        self.assertTrue(report["archive_extractable"])
        self.assertTrue(report["temp_dir_removed"])
        self.assertTrue(report["dump"]["toc_listed"])
        self.assertGreater(report["archive_member_count"], 0)

    def test_checksum_mismatch_is_not_restorable(self) -> None:
        backup = _station_backup(self.root)
        (backup / "compose.yml").write_text("changed\n", encoding="utf-8")
        report = restore_dry_run.dry_run(
            backup,
            dump_lister=lambda _path: (0, "toc"),
        )
        self.assertFalse(report["restorable"])
        self.assertFalse(report["checksums_ok"])

    def test_unsafe_tar_is_rejected(self) -> None:
        backup = _station_backup(self.root)
        _write_tar(
            backup / "ai_station_files.tar.gz",
            {"../../etc/passwd": b"nope"},
        )
        _sha256sums(
            backup,
            (
                "ai_station_postgres.dump",
                "ai_station_files.tar.gz",
                "compose.yml",
                "env.example",
            ),
        )
        report = restore_dry_run.dry_run(
            backup,
            dump_lister=lambda _path: (0, "toc"),
        )
        self.assertFalse(report["restorable"])
        self.assertFalse(report["archive_extractable"])
        self.assertIn("unsafe tar member", report["archive_error"])

    def test_special_tar_member_is_rejected(self) -> None:
        backup = _station_backup(self.root)
        with tarfile.open(backup / "ai_station_files.tar.gz", "w:gz") as archive:
            member = tarfile.TarInfo("uploads/device")
            member.type = tarfile.CHRTYPE
            member.devmajor = 1
            member.devminor = 3
            archive.addfile(member)
        _sha256sums(
            backup,
            (
                "ai_station_postgres.dump",
                "ai_station_files.tar.gz",
                "compose.yml",
                "env.example",
            ),
        )
        report = restore_dry_run.dry_run(
            backup,
            dump_lister=lambda _path: (0, "toc"),
        )
        self.assertFalse(report["restorable"])
        self.assertFalse(report["archive_extractable"])
        self.assertIn("special file", report["archive_error"])

    def test_failed_dump_listing_is_not_restorable(self) -> None:
        backup = _station_backup(self.root)
        report = restore_dry_run.dry_run(
            backup,
            dump_lister=lambda _path: (1, "corrupt dump"),
        )
        self.assertFalse(report["restorable"])
        self.assertFalse(report["dump"]["toc_listed"])

    def test_magic_only_dump_is_restorable_with_warning(self) -> None:
        backup = _station_backup(self.root)
        report = restore_dry_run.dry_run(
            backup,
            dump_lister=lambda _path: (127, "pg_restore missing"),
        )
        self.assertTrue(report["restorable"])
        self.assertTrue(report["dump"]["toc_skipped"])
        self.assertTrue(any("pg_restore" in item for item in report["warnings"]))

    def test_resolve_latest_ignores_unrelated_dirs(self) -> None:
        _station_backup(self.root, "20260901-010101")
        _station_backup(self.root, "20260902-120000")
        _station_backup(self.root, ".partial-20260903-120000-fixture")
        _station_backup(self.root, "unpublished-20260903-120000")
        other = self.root / "backups" / "openwebui-stale-models-20260818-135111"
        other.mkdir(parents=True)
        (other / "SHA256SUMS").write_text("deadbeef  x\n", encoding="utf-8")
        chosen = restore_dry_run.resolve_backup_dir(root=self.root)
        self.assertEqual(chosen.name, "20260902-120000")

    def test_partial_only_directory_is_not_a_backup(self) -> None:
        _station_backup(self.root, ".partial-20260903-120000-fixture")
        with self.assertRaises(restore_dry_run.RestoreError):
            restore_dry_run.resolve_backup_dir(root=self.root)

    def test_restore_checksums_and_dump_header_do_not_load_whole_files(self) -> None:
        from unittest.mock import patch

        backup = _station_backup(self.root)
        with patch.object(Path, "read_bytes", side_effect=AssertionError("whole-file read")):
            report = restore_dry_run.dry_run(backup, dump_lister=lambda _path: (0, "toc"))
        self.assertTrue(report["restorable"])

    def test_cli_refuses_live_restore(self) -> None:
        from io import StringIO
        from unittest.mock import patch

        with patch("sys.stderr", StringIO()):
            code = restore_dry_run.main([])
        self.assertEqual(code, 2)

    @unittest.skipIf(os.name == "nt", "requires POSIX shell utilities")
    def test_backup_same_second_collision_keeps_first_publish(self) -> None:
        if shutil.which("bash") is None:
            self.skipTest("bash unavailable")
        with tempfile.TemporaryDirectory() as work:
            work_root = Path(work)
            project = work_root / "project"
            scripts = project / "scripts"
            scripts.mkdir(parents=True)
            backup_script = scripts / "backup.sh"
            backup_script.write_text(
                (ROOT / "scripts" / "backup.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            backup_script.chmod(0o755)
            compose_stub = scripts / "compose-ai-station.sh"
            compose_stub.write_text(
                "#!/usr/bin/env bash\n"
                "set -eu\n"
                "n=0\n"
                "if [[ -f \"$COUNTER_FILE\" ]]; then n=$(cat \"$COUNTER_FILE\"); fi\n"
                "n=$((n + 1)); printf '%s' \"$n\" > \"$COUNTER_FILE\"\n"
                "printf 'PGDMP-%s\\n' \"$n\"\n",
                encoding="utf-8",
            )
            compose_stub.chmod(0o755)
            bin_dir = work_root / "bin"
            bin_dir.mkdir()
            date_stub = bin_dir / "date"
            date_stub.write_text(
                "#!/usr/bin/env bash\nprintf '20260903-120000\\n'\n",
                encoding="utf-8",
            )
            date_stub.chmod(0o755)
            (project / "compose.yml").write_text("services: {}\n", encoding="utf-8")
            (project / ".env.example").write_text("EXAMPLE=1\n", encoding="utf-8")
            data = work_root / "data"
            (data / "data" / "uploads").mkdir(parents=True)
            (data / "data" / "artifacts").mkdir()
            (data / "data" / "uploads" / "note.txt").write_text("first\n", encoding="utf-8")
            counter = work_root / "dump-counter"
            env = os.environ.copy()
            env.update(
                {
                    "AI_STATION_DATA": str(data),
                    "COUNTER_FILE": str(counter),
                    "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
                }
            )
            first = subprocess.run(
                ["bash", str(backup_script)],
                cwd=project,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            second = subprocess.run(
                ["bash", str(backup_script)],
                cwd=project,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(second.returncode, 0)
            published = data / "backups" / "20260903-120000"
            self.assertEqual(
                list((data / "backups").iterdir()),
                [published],
            )
            self.assertEqual(
                (published / "ai_station_postgres.dump").read_bytes(),
                b"PGDMP-1\n",
            )
            self.assertFalse((published / "20260903-120000").exists())
            self.assertEqual(
                list((data / "backups").glob(".partial-*")),
                [],
            )


class RetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        os.environ["AI_STATION_DATA"] = str(self.root)
        os.environ["AI_STATION_RETENTION_POLICY"] = str(
            self.root / "runtime" / "retention.json"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()
        os.environ.pop("AI_STATION_DATA", None)
        os.environ.pop("AI_STATION_RETENTION_POLICY", None)

    def test_missing_policy_is_disabled_with_90_day_default(self) -> None:
        policy = retention.load_policy()
        self.assertFalse(policy.enabled)
        self.assertEqual(policy.ttl_days, 90)

    def test_disabled_apply_deletes_nothing(self) -> None:
        catalog = retention.MappingCatalog(
            {"chat": {"updated_at": "bigint"}}
        )
        executor = retention.RecordingExecutor({"chat": 12})
        report = retention.apply_policy(
            retention.default_policy(),
            catalog,
            executor,
            delete=True,
        )
        self.assertFalse(report["applied"])
        self.assertEqual(executor.statements, [])
        self.assertEqual(report["deleted"], {})

    def test_enabled_dry_run_counts_chats_and_chunks(self) -> None:
        catalog = retention.MappingCatalog(
            {
                "chat": {"updated_at": "bigint", "title": "text"},
                "document_chunk": {
                    "created_at": "timestamp with time zone",
                    "text": "text",
                },
            }
        )
        executor = retention.RecordingExecutor(
            {"chat": 4, "document_chunk": 9}
        )
        now = datetime(2026, 9, 2, tzinfo=timezone.utc)
        report = retention.apply_policy(
            retention.RetentionPolicy(enabled=True, ttl_days=90),
            catalog,
            executor,
            now=now,
            delete=False,
        )
        self.assertEqual(report["counted"]["chat"], 4)
        self.assertEqual(report["counted"]["document_chunk"], 9)
        self.assertEqual(report["deleted"]["chat"], 0)
        self.assertFalse(report["applied"])
        joined = " ".join(sql for sql, _params in executor.statements)
        self.assertNotIn("title", joined.lower())
        self.assertNotRegex(joined, r"\btext\b")

    def test_enabled_apply_deletes_using_cutoff(self) -> None:
        catalog = retention.MappingCatalog(
            {"chat": {"updated_at": "bigint"}}
        )
        executor = retention.RecordingExecutor({"chat": 2})
        now = datetime(2026, 9, 2, tzinfo=timezone.utc)
        report = retention.apply_policy(
            retention.RetentionPolicy(enabled=True, ttl_days=90),
            catalog,
            executor,
            now=now,
            delete=True,
        )
        self.assertTrue(report["applied"])
        self.assertEqual(report["deleted"]["chat"], 2)
        self.assertTrue(
            any(sql.startswith("WITH _d AS (DELETE") for sql, _ in executor.statements)
        )
        cutoff = retention.cutoff_epoch(now, 90)
        self.assertEqual(executor.statements[0][1], (cutoff,))


class AlertTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        os.environ["AI_STATION_DATA"] = str(self.root)
        os.environ["AI_STATION_ALERTS_DIR"] = str(self.root / "runtime" / "alerts")

    def tearDown(self) -> None:
        self.temp.cleanup()
        os.environ.pop("AI_STATION_DATA", None)
        os.environ.pop("AI_STATION_ALERTS_DIR", None)

    def test_usage_alert_does_not_reject_requests(self) -> None:
        series = [
            station_alerts.DailyUsage("n8n", "2026-08-30", 400_000),
            station_alerts.DailyUsage("n8n", "2026-08-31", 400_000),
            station_alerts.DailyUsage("n8n", "2026-09-01", 400_000),
            station_alerts.DailyUsage("n8n", "2026-09-02", 1_300_000),
        ]
        report = station_alerts.evaluate(
            usage=series,
            today="2026-09-02",
            last_fired={},
        )
        self.assertEqual(len(report["alerts"]), 1)
        self.assertEqual(report["alerts"][0]["kind"], "usage")
        self.assertTrue(report["requests_allowed"])
        self.assertTrue(station_alerts.requests_allowed(True))
        payload = litellm_keys.generate_payload(
            "n8n",
            ["Qwen3.8-27B-UD-Q4_K_M"],
        )
        self.assertNotIn("tpm_limit", payload)
        self.assertNotIn("rpm_limit", payload)
        fire, threshold = station_alerts.should_fire_usage(
            400,
            [100, 100, 100],
            multiplier=3.0,
            floor=50,
        )
        self.assertTrue(fire)
        self.assertEqual(threshold, 300)

    def test_usage_warmup_uses_floor(self) -> None:
        quiet = station_alerts.evaluate(
            usage=[station_alerts.DailyUsage("new", "2026-09-02", 999_999)],
            today="2026-09-02",
            last_fired={},
        )
        loud = station_alerts.evaluate(
            usage=[station_alerts.DailyUsage("new", "2026-09-02", 1_000_001)],
            today="2026-09-02",
            last_fired={},
        )
        self.assertEqual(quiet["alerts"], [])
        self.assertEqual(len(loud["alerts"]), 1)

    def test_health_alerts_and_redacted_messages(self) -> None:
        report = station_alerts.evaluate(
            disk_percent=86.2,
            oom_hits={"llm-general": 3},
            container_statuses={"postgres": "exited", "redis": "running"},
            today="2026-09-02",
            last_fired={},
        )
        kinds = {item["kind"] for item in report["alerts"]}
        self.assertEqual(kinds, {"disk", "oom", "container"})
        joined = " ".join(item["message"] for item in report["alerts"])
        self.assertNotRegex(joined, r"prompt|messages|content")
        self.assertTrue(report["requests_allowed"])

    def test_alert_store_is_size_and_age_capped(self) -> None:
        now = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
        old = {
            "kind": "disk",
            "fired_at": (now - timedelta(hours=80)).isoformat(),
            "subject": "disk",
            "message": "old",
        }
        bulky = [
            {
                "kind": "usage",
                "fired_at": now.isoformat(),
                "subject": f"key-{index}",
                "message": "x" * 8000,
            }
            for index in range(80)
        ]
        path = Path(os.environ["AI_STATION_ALERTS_DIR"]) / "alerts.jsonl"
        kept = station_alerts.write_records(
            [old, *bulky],
            path=path,
            now=now,
            max_age_hours=72,
            max_bytes=262144,
        )
        self.assertTrue(all(item["subject"] != "disk" or item["message"] != "old" for item in kept))
        encoded = path.read_bytes()
        self.assertLessEqual(len(encoded), 262144)
        self.assertGreater(len(kept), 0)

    def test_source_never_sets_rate_caps(self) -> None:
        text = (LIB / "station_alerts.py").read_text(encoding="utf-8")
        self.assertNotIn("tpm_limit", text)
        self.assertNotIn("rpm_limit", text)
        self.assertIn("REQUESTS_ALWAYS_ALLOWED = True", text)
        self.assertIn("MAX_ALERT_BYTES = 262144", text)


class CliContractTests(unittest.TestCase):
    def test_ai_usage_lists_wave0_commands(self) -> None:
        text = (ROOT / "scripts" / "ai").read_text(encoding="utf-8")
        self.assertIn("ai restore --dry-run", text)
        self.assertIn("ai retention", text)
        self.assertIn("ai alerts", text)
        self.assertIn("scripts/lib/ai-ops.sh", text)
        self.assertIn("cmd_restore", text)


if __name__ == "__main__":
    unittest.main()
