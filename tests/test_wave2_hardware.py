#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import hardware_detect  # noqa: E402
from apps.gateway.app.admission import npu_present  # noqa: E402


class HardwareDetectTests(unittest.TestCase):
    def test_absent_npu_does_not_promote(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            accel = Path(directory) / "accel"
            accel.mkdir()
            report = hardware_detect.detect_npu(sys_class_accel=accel)
        self.assertFalse(report["present"])
        self.assertEqual(report["status"], "absent")
        self.assertFalse(report["promoted"])

    def test_detected_npu_stays_off_until_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            accel = Path(directory) / "accel"
            (accel / "accel0").mkdir(parents=True)
            report = hardware_detect.detect_npu(sys_class_accel=accel)
        self.assertTrue(report["present"])
        self.assertFalse(report["promoted"])
        self.assertIn("benchmarks/results", report["note"])

    def test_profile_without_npu_is_absent(self) -> None:
        self.assertFalse(npu_present({}))
        self.assertFalse(npu_present({"npu": {"present": False}}))
        self.assertTrue(npu_present({"npu": {"present": True}}))


if __name__ == "__main__":
    unittest.main()
