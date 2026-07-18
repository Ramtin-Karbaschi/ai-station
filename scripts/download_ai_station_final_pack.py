from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download, snapshot_download


BASE = Path("/srv/ai-station/models")
REGISTRY_PATH = BASE / "ai-station-model-registry-final.json"


GGUF_MODELS = [
    {
        "id": "deepseek-r1-distill-qwen-32b-thinking",
        "role": "thinking_reasoning",
        "repo_id": "bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF",
        "quant_preferences": ["Q4_K_M", "Q5_K_M", "IQ4_XS"],
        "dest_dir": "thinking",
        "dest_file": "deepseek-r1-distill-qwen-32b-q4_k_m.gguf",
        "notes": "Primary thinking/reasoning model for deep analysis.",
    },
    {
        "id": "qwen3-vl-32b-instruct",
        "role": "vision_language",
        "repo_id": "Qwen/Qwen3-VL-32B-Instruct-GGUF",
        "quant_preferences": ["Q4_K_M"],
        "dest_dir": "vision/qwen3-vl-32b-instruct",
        "dest_file": "qwen3-vl-32b-instruct-q4_k_m.gguf",
        "notes": "Primary local vision-language model.",
    },
]


OCR_SNAPSHOTS = [
    {
        "id": "dots-mocr",
        "role": "ocr_layout_parsing",
        "repo_id": "rednote-hilab/dots.mocr",
        "dest_dir": "ocr/dots-mocr",
        "ignore_patterns": ["*.onnx", "*.tflite"],
        "notes": "Primary advanced OCR/document parsing model.",
    },
    {
        "id": "dots-ocr",
        "role": "ocr_layout_parsing_light",
        "repo_id": "rednote-hilab/dots.ocr",
        "dest_dir": "ocr/dots-ocr",
        "ignore_patterns": ["*.onnx", "*.tflite"],
        "notes": "Fallback compact multilingual document parser.",
    },
    {
        "id": "deepseek-ocr-2",
        "role": "ocr_document_understanding",
        "repo_id": "deepseek-ai/DeepSeek-OCR-2",
        "dest_dir": "ocr/deepseek-ocr-2",
        "ignore_patterns": ["*.onnx", "*.tflite"],
        "notes": "Secondary OCR/document understanding model.",
    },
]


FRONTIER_HEAVY_CATALOG = [
    {
        "id": "glm-5.2-gguf",
        "role": "frontier_thinking_agentic",
        "repo_id": "unsloth/GLM-5.2-GGUF",
        "status": "accepted_catalog_only_not_downloaded",
        "reason": "Accepted as powerful frontier model, but too heavy for immediate operational pack.",
    },
    {
        "id": "kimi-k2.7-code-gguf",
        "role": "frontier_coding_agentic",
        "repo_id": "unsloth/Kimi-K2.7-Code-GGUF",
        "status": "accepted_catalog_only_not_downloaded",
        "reason": "Accepted as powerful frontier coding model, but too heavy for immediate operational pack.",
    },
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024 * 8), b""):
            h.update(chunk)
    return h.hexdigest()


def list_files(repo_id: str) -> list[str]:
    return HfApi().list_repo_files(repo_id)


def choose_gguf(repo_id: str, preferences: list[str]) -> str:
    files = list_files(repo_id)
    ggufs = [
        f for f in files
        if f.lower().endswith(".gguf")
        and "mmproj" not in f.lower()
        and "00001-of-" not in f.lower()
    ]

    if not ggufs:
        all_ggufs = [f for f in files if f.lower().endswith(".gguf") and "mmproj" not in f.lower()]
        raise RuntimeError(
            f"No single-file base GGUF found in {repo_id}. "
            f"Split GGUF not accepted by this quick operational pack. Examples={all_ggufs[:20]}"
        )

    for pref in preferences:
        matches = [f for f in ggufs if pref.lower() in f.lower()]
        if matches:
            return sorted(matches)[0]

    raise RuntimeError(
        f"No GGUF matching preferences={preferences} in {repo_id}. "
        f"Available examples={ggufs[:30]}"
    )


def choose_mmproj(repo_id: str) -> str | None:
    files = list_files(repo_id)
    mmprojs = [
        f for f in files
        if f.lower().endswith(".gguf")
        and "mmproj" in f.lower()
    ]
    if not mmprojs:
        return None

    for pref in ["q8_0", "fp16", "f16"]:
        matches = [f for f in mmprojs if pref in f.lower()]
        if matches:
            return sorted(matches)[0]

    return sorted(mmprojs)[0]


def download_file(repo_id: str, source_file: str, dest_path: Path) -> dict:
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    downloaded = hf_hub_download(
        repo_id=repo_id,
        filename=source_file,
        local_dir=str(dest_path.parent),
    )

    src = Path(downloaded)
    if src.resolve() != dest_path.resolve():
        shutil.copy2(src, dest_path)

    digest = sha256_file(dest_path)
    sha_path = dest_path.with_suffix(dest_path.suffix + ".sha256")
    sha_path.write_text(f"{digest}  {dest_path}\n")

    return {
        "source_file": source_file,
        "local_file": str(dest_path),
        "relative_file": str(dest_path.relative_to(BASE)),
        "sha256": digest,
    }


def download_gguf_model(spec: dict) -> dict:
    print(f"\n=== Download GGUF: {spec['id']} ===")
    repo_id = spec["repo_id"]
    selected = choose_gguf(repo_id, spec["quant_preferences"])
    dest = BASE / spec["dest_dir"] / spec["dest_file"]

    print(f"repo: {repo_id}")
    print(f"selected: {selected}")
    print(f"dest: {dest}")

    record = {
        "id": spec["id"],
        "role": spec["role"],
        "repo_id": repo_id,
        "notes": spec["notes"],
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    record.update(download_file(repo_id, selected, dest))

    if spec["role"] == "vision_language":
        mmproj = choose_mmproj(repo_id)
        if mmproj:
            mmproj_dest = BASE / spec["dest_dir"] / "mmproj-qwen3-vl-32b.gguf"
            print(f"mmproj selected: {mmproj}")
            print(f"mmproj dest: {mmproj_dest}")
            mm = download_file(repo_id, mmproj, mmproj_dest)
            record["mmproj"] = mm
        else:
            record["mmproj"] = None
            record["warning"] = "No mmproj found. llama.cpp multimodal support may need separate runtime."

    return record


def download_ocr_snapshot(spec: dict) -> dict:
    print(f"\n=== Download OCR snapshot: {spec['id']} ===")
    repo_id = spec["repo_id"]
    dest = BASE / spec["dest_dir"]
    dest.mkdir(parents=True, exist_ok=True)

    print(f"repo: {repo_id}")
    print(f"dest: {dest}")

    snapshot_download(
        repo_id=repo_id,
        local_dir=str(dest),
        local_dir_use_symlinks=False,
        ignore_patterns=spec.get("ignore_patterns", []),
    )

    return {
        "id": spec["id"],
        "role": spec["role"],
        "repo_id": repo_id,
        "local_dir": str(dest),
        "relative_dir": str(dest.relative_to(BASE)),
        "notes": spec["notes"],
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    BASE.mkdir(parents=True, exist_ok=True)

    installed_final = []
    for spec in GGUF_MODELS:
        installed_final.append(download_gguf_model(spec))

    ocr = []
    for spec in OCR_SNAPSHOTS:
        ocr.append(download_ocr_snapshot(spec))

    old_registry_path = BASE / "ai-station-model-registry.json"
    old_registry = {}
    if old_registry_path.exists():
        try:
            old_registry = json.loads(old_registry_path.read_text())
        except Exception:
            old_registry = {}

    registry = {
        "project": "AI Station",
        "version": "final-operational-model-pack-2026-07",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_dir": str(BASE),
        "existing_installed": old_registry.get("installed", []),
        "installed_final": installed_final,
        "ocr_model_store": ocr,
        "frontier_heavy_catalog": FRONTIER_HEAVY_CATALOG,
        "policy": {
            "daily_general": "qwen3.6-35b-a3b-general",
            "daily_coder": "qwen3-coder-30b-a3b",
            "deep_thinking": "deepseek-r1-distill-qwen-32b-thinking",
            "vision_language": "qwen3-vl-32b-instruct",
            "ocr_primary": "dots-mocr",
            "ocr_fallback": "dots-ocr",
            "ocr_secondary": "deepseek-ocr-2",
            "frontier_accepted_but_not_downloaded": ["glm-5.2-gguf", "kimi-k2.7-code-gguf"],
            "gpu_rule": "Only one heavy LLM/VLM should run at a time on RTX 5090 Laptop 24GB.",
        },
    }

    REGISTRY_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=False))
    print(f"\nRegistry written: {REGISTRY_PATH}")
    print(json.dumps(registry, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
