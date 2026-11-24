import hashlib
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "lib"))
import restore_dry_run  # noqa: E402


class OpenWebUIVolumeBackupTests(unittest.TestCase):
    def _base_backup(self, root: Path) -> Path:
        backup = root / "20261122-120000"
        backup.mkdir()
        (backup / "ai_station_postgres.dump").write_bytes(b"PGDMP-fixture")
        with tarfile.open(backup / "ai_station_files.tar.gz", "w:gz") as archive:
            item = root / "upload.txt"
            item.write_text("upload\n", encoding="utf-8")
            archive.add(item, arcname="uploads/upload.txt")
        (backup / "compose.yml").write_text("services: {}\n", encoding="utf-8")
        (backup / "env.example").write_text("EXAMPLE=1\n", encoding="utf-8")
        return backup

    def test_optional_volume_pair_is_checked_and_restorable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backup = self._base_backup(root)
            with tarfile.open(backup / "ai_station_openwebui_data.tar.gz", "w:gz") as archive:
                whisper = root / "model.bin"
                whisper.write_bytes(b"whisper")
                archive.add(whisper, arcname="cache/whisper/models/model.bin")
            (backup / "openwebui_volume_manifest.json").write_text(
                json.dumps({
                    "schema": 1,
                    "volume": "ai-station-openwebui-data",
                    "sqlite_snapshot_count": 0,
                    "sqlite_snapshots": [],
                    "whisper_member_count": 1,
                }) + "\n",
                encoding="utf-8",
            )
            checksums = []
            for item in sorted(backup.iterdir()):
                checksums.append(f"{hashlib.sha256(item.read_bytes()).hexdigest()}  {item.name}")
            (backup / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")

            self.assertTrue(restore_dry_run.is_station_backup(backup))
            report = restore_dry_run.dry_run(backup, dump_lister=lambda _: (0, "toc"))
            self.assertTrue(report["restorable"], report)
            self.assertTrue(report["openwebui_volume"]["manifest_valid"])

    def test_complete_backup_validates_litellm_dump_and_snapshot_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backup = self._base_backup(root)
            (backup / "ai_station_litellm.dump").write_bytes(b"PGDMP-litellm")
            (backup / "database_backup_manifest.json").write_text(json.dumps({
                "schema": 1,
                "mode": "complete",
                "database": "litellm",
                "snapshot_started_utc": "2026-11-22T10:00:00Z",
                "snapshot_finished_utc": "2026-11-22T10:00:02Z",
                "artifacts": ["ai_station_postgres.dump", "ai_station_litellm.dump"],
            }) + "\n", encoding="utf-8")
            with tarfile.open(backup / "ai_station_openwebui_data.tar.gz", "w:gz") as archive:
                whisper = root / "model.bin"
                whisper.write_bytes(b"whisper")
                archive.add(whisper, arcname="cache/whisper/models/model.bin")
            (backup / "openwebui_volume_manifest.json").write_text(json.dumps({
                "schema": 1,
                "volume": "ai-station-openwebui-data",
                "sqlite_snapshot_count": 0,
                "sqlite_snapshots": [],
                "whisper_member_count": 1,
            }) + "\n", encoding="utf-8")
            checksums = [f"{hashlib.sha256(item.read_bytes()).hexdigest()}  {item.name}" for item in sorted(backup.iterdir())]
            (backup / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")
            self.assertTrue(restore_dry_run.is_station_backup(backup))
            report = restore_dry_run.dry_run(backup, dump_lister=lambda _: (0, "toc"))
            self.assertTrue(report["restorable"], report)
            self.assertEqual(report["litellm_database"]["database"], "litellm")

    def test_incomplete_litellm_pair_is_not_discoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            backup = self._base_backup(Path(temp))
            (backup / "ai_station_litellm.dump").write_bytes(b"PGDMP-litellm")
            self.assertFalse(restore_dry_run.is_station_backup(backup))

    def test_volume_archive_without_manifest_is_not_discoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            backup = Path(temp) / "20261122-120000"
            backup.mkdir()
            for name in restore_dry_run.EXPECTED_FILES:
                (backup / name).write_bytes(b"fixture")
            (backup / "ai_station_openwebui_data.tar.gz").write_bytes(b"extra")
            self.assertFalse(restore_dry_run.is_station_backup(backup))


if __name__ == "__main__":
    unittest.main()
