#!/usr/bin/env python3
"""Hardware snapshot helpers (ADR-031, ADR-032). Never promotes an NPU backend."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from apps.gateway.app.admission import list_gpus, load_hardware, npu_present
from apps.gateway.app.paths import PROJECT_DIR

HARDWARE_PATH = Path(
    os.getenv(
        "AI_STATION_HARDWARE_PROFILE",
        str(PROJECT_DIR / "config/hardware-profile.json"),
    )
)


def accel_nodes(sys_class: Path) -> list[str]:
    if not sys_class.is_dir():
        return []
    return sorted(path.name for path in sys_class.iterdir() if path.is_dir())


def detect_npu(*, sys_class_accel: Path | None = None) -> dict[str, Any]:
    accel = sys_class_accel or Path("/sys/class/accel")
    nodes = accel_nodes(accel)
    if not nodes:
        return {
            "present": False,
            "status": "absent",
            "name": None,
            "nodes": [],
            "classification": "optional_profile",
            "promoted": False,
            "note": "No /sys/class/accel device. CPU embed/rerank/ASR stay in place.",
        }
    return {
        "present": True,
        "status": "detected",
        "name": "intel-npu" if nodes else None,
        "nodes": nodes,
        "classification": "optional_profile",
        "promoted": False,
        "note": (
            "NPU detected but not promoted. Keep CPU embed/rerank/ASR until a "
            "local apples-to-apples result under benchmarks/results/ beats the "
            "station 20% rule with no quality regression (ADR-032)."
        ),
    }


def snapshot(
    *,
    hardware: dict[str, Any] | None = None,
    sys_class_accel: Path | None = None,
) -> dict[str, Any]:
    profile = hardware if hardware is not None else load_hardware()
    gpus = list_gpus(profile)
    npu = detect_npu(sys_class_accel=sys_class_accel)
    return {
        "gpu_count": len(gpus),
        "gpus": [
            {
                "index": int(gpu.get("index", index)),
                "name": gpu.get("name"),
                "vram_total_mib": gpu.get("vram_total_mib"),
            }
            for index, gpu in enumerate(gpus)
        ],
        "max_heavy_providers_default": 1,
        "npu": npu,
        "npu_present_in_profile": npu_present(profile),
        "cpu_embed_rerank_asr": "unchanged",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Show GPU/NPU placement facts. Does not enable NPU offload."
    )
    parser.add_argument("command", nargs="?", default="detect")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command not in {"detect", "status"}:
        print("Usage: ai hardware detect [--dry-run]", file=sys.stderr)
        return 2
    report = snapshot()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
