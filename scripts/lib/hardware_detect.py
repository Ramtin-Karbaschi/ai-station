#!/usr/bin/env python3
"""Hardware snapshot helpers (ADR-031, ADR-032). Never promotes an NPU backend."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
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


def probe_runtime_gpu(
    *,
    executable: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
    wsl_tool_path: Path = Path("/usr/lib/wsl/lib/nvidia-smi"),
) -> dict[str, Any]:
    """Probe current WSL NVIDIA visibility independently of the cached profile."""
    tool = executable or which("nvidia-smi")
    if not tool and wsl_tool_path.is_file():
        tool = str(wsl_tool_path)
    if not tool:
        return {
            "status": "tool_missing",
            "adapter_count": 0,
            "message": (
                "nvidia-smi is unavailable in this WSL session; check WSL GPU "
                "pass-through and the Windows NVIDIA driver."
            ),
        }

    try:
        result = runner(
            [tool, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "status": "query_failed",
            "adapter_count": 0,
            "message": (
                "nvidia-smi could not query a GPU inside WSL; check WSL GPU "
                "pass-through, /dev/dxg, and the Windows NVIDIA driver."
            ),
        }

    if result.returncode != 0:
        return {
            "status": "query_failed",
            "adapter_count": 0,
            "return_code": result.returncode,
            "message": (
                "nvidia-smi failed inside WSL; check WSL GPU pass-through, "
                "/dev/dxg, and the Windows NVIDIA driver."
            ),
        }

    adapters: list[dict[str, Any]] = []
    for line in (result.stdout or "").splitlines():
        name, separator, total = line.partition(",")
        if not separator:
            continue
        name = name.strip()
        try:
            total_mib = int(total.strip())
        except ValueError:
            continue
        if name:
            adapters.append({"name": name, "vram_total_mib": total_mib})

    if not adapters:
        return {
            "status": "no_adapters",
            "adapter_count": 0,
            "message": (
                "nvidia-smi runs inside WSL but reports no NVIDIA adapters; "
                "check WSL GPU pass-through and the Windows NVIDIA driver."
            ),
        }
    return {
        "status": "available",
        "adapter_count": len(adapters),
        "adapters": adapters,
        "message": f"{len(adapters)} NVIDIA adapter(s) are visible to this WSL session.",
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
        "gpu_count_source": "cached config/hardware-profile.json; not live WSL visibility",
        "gpus": [
            {
                "index": int(gpu.get("index", index)),
                "name": gpu.get("name"),
                "vram_total_mib": gpu.get("vram_total_mib"),
            }
            for index, gpu in enumerate(gpus)
        ],
        "max_heavy_providers_default": 1,
        "runtime_gpu": probe_runtime_gpu(),
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
