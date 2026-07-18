from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download


BASE = Path("/srv/ai-station/models")
REGISTRY_PATH = BASE / "ai-station-model-registry.json"

MODEL_SPECS = [
    {
        "id": "qwen3.6-35b-a3b-general",
        "role": "general_reasoning",
        "repo_id": "unsloth/Qwen3.6-35B-A3B-GGUF",
        "quant_preferences": ["UD-Q4_K_M", "Q4_K_M", "UD-Q4_K_XL", "Q4_K_S"],
        "dest_dir": "general",
        "dest_file": "qwen3.6-35b-a3b-ud-q4_k_m.gguf",
        "active_default": True,
        "notes": "Primary AI Station general reasoning / document analysis model.",
    },
    {
        "id": "qwen3-coder-30b-a3b",
        "role": "coding_agent",
        "repo_id": "unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF",
        "quant_preferences": ["UD-Q4_K_XL", "UD-Q4_K_M", "Q4_K_M", "Q4_K_S"],
        "dest_dir": "coder",
        "dest_file": "qwen3-coder-30b-a3b-instruct-q4.gguf",
        "active_default": False,
        "notes": "Coding, refactoring, repo analysis, agentic IDE workflows.",
    },
    {
        "id": "qwen3-embedding-0.6b",
        "role": "embedding",
        "repo_id": "Qwen/Qwen3-Embedding-0.6B-GGUF",
        "quant_preferences": ["Q8_0", "Q6_K", "Q4_K_M"],
        "dest_dir": "embedding",
        "dest_file": "qwen3-embedding-0.6b-q8_0.gguf",
        "active_default": True,
        "notes": "Primary RAG embedding model. Small enough to keep operationally cheap.",
    },
    {
        "id": "qwen3-reranker-0.6b",
        "role": "reranker",
        "repo_id": "ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF",
        "quant_preferences": ["Q8_0", "Q6_K", "Q4_K_M"],
        "dest_dir": "reranker",
        "dest_file": "qwen3-reranker-0.6b-q8_0.gguf",
        "active_default": False,
        "notes": "Reranker profile. Validate before using in production RAG.",
    },
]


EXPERIMENTAL_CATALOG = [
    {
        "id": "glm-5.2-gguf",
        "role": "experimental_reasoning",
        "repo_id": "unsloth/GLM-5.2-GGUF",
        "status": "catalog_only",
        "reason": "Potentially powerful but not installed now due VRAM/RAM/download risk.",
    },
    {
        "id": "glm-5-gguf",
        "role": "experimental_reasoning",
        "repo_id": "unsloth/GLM-5-GGUF",
        "status": "catalog_only",
        "reason": "Keep as future benchmark candidate, not active runtime.",
    },
    {
        "id": "kimi-k2.7-code-gguf",
        "role": "experimental_coding_agent",
        "repo_id": "unsloth/Kimi-K2.7-Code-GGUF",
        "status": "catalog_only",
        "reason": "Promising agentic coding model; likely too heavy for first operational pack.",
    },
    {
        "id": "deepseek-v3.2-gguf",
        "role": "experimental_reasoning_agent",
        "repo_id": "unsloth/DeepSeek-V3.2-GGUF",
        "status": "catalog_only",
        "reason": "Large model; do not install until we design offload/runtime profile.",
    },
    {
        "id": "deepseek-ocr-2",
        "role": "ocr_document_understanding",
        "repo_id": "deepseek-ai/DeepSeek-OCR-2",
        "status": "runtime_later",
        "reason": "Transformers-based OCR profile, not llama.cpp GGUF service.",
    },
    {
        "id": "dots-mocr",
        "role": "ocr_layout_parsing",
        "repo_id": "rednote-hilab/dots.mocr",
        "status": "runtime_later",
        "reason": "Document parsing/OCR runtime to be added as separate service.",
    },
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024 * 8), b""):
            h.update(chunk)
    return h.hexdigest()


def choose_file(repo_id: str, quant_preferences: list[str]) -> str:
    api = HfApi()
    files = api.list_repo_files(repo_id)

    ggufs = [f for f in files if f.lower().endswith(".gguf")]
    if not ggufs:
        raise RuntimeError(f"No GGUF files found in {repo_id}")

    for q in quant_preferences:
        candidates = [f for f in ggufs if q.lower() in f.lower()]
        if candidates:
            # Prefer non-sharded single file unless only sharded exists.
            single = [c for c in candidates if "00001-of-" not in c.lower()]
            return sorted(single or candidates)[0]

    raise RuntimeError(
        f"No GGUF matching {quant_preferences} found in {repo_id}. "
        f"Available examples: {ggufs[:20]}"
    )


def download_one(spec: dict) -> dict:
    repo_id = spec["repo_id"]
    selected_file = choose_file(repo_id, spec["quant_preferences"])

    dest_dir = BASE / spec["dest_dir"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / spec["dest_file"]

    print(f"\n=== {spec['id']} ===")
    print(f"repo: {repo_id}")
    print(f"selected: {selected_file}")
    print(f"dest: {dest_path}")

    downloaded = hf_hub_download(
        repo_id=repo_id,
        filename=selected_file,
        local_dir=str(dest_dir),
        resume_download=True,
    )

    src = Path(downloaded)
    if src.resolve() != dest_path.resolve():
        shutil.copy2(src, dest_path)

    digest = sha256_file(dest_path)
    (dest_path.with_suffix(dest_path.suffix + ".sha256")).write_text(
        f"{digest}  {dest_path}\n"
    )

    return {
        "id": spec["id"],
        "role": spec["role"],
        "repo_id": repo_id,
        "source_file": selected_file,
        "local_file": str(dest_path),
        "relative_file": str(dest_path.relative_to(BASE)),
        "sha256": digest,
        "active_default": spec["active_default"],
        "notes": spec["notes"],
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    BASE.mkdir(parents=True, exist_ok=True)

    installed = []
    for spec in MODEL_SPECS:
        installed.append(download_one(spec))

    registry = {
        "project": "AI Station",
        "version": "model-pack-2026-07",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_dir": str(BASE),
        "installed": installed,
        "experimental_catalog": EXPERIMENTAL_CATALOG,
        "operational_rule": (
            "Do not run general, coder, and vision large models at the same time "
            "on a 24GB VRAM GPU. Use Compose profiles and stop one before starting another."
        ),
    }

    REGISTRY_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=False))
    print(f"\nModel registry written: {REGISTRY_PATH}")
    print(json.dumps(registry, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
