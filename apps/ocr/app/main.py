from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PROJECT_DIR = Path(os.getenv("AI_STATION_PROJECT_DIR", "/opt/ai-station"))
OCR_MODELS_DIR = Path(os.getenv("AI_STATION_OCR_MODELS_DIR", "/srv/ai-station/models/ocr"))
OCR_UPLOAD_DIR = Path(os.getenv("AI_STATION_OCR_UPLOAD_DIR", "/srv/ai-station/data/ocr/uploads"))
OCR_OUTPUT_DIR = Path(os.getenv("AI_STATION_OCR_OUTPUT_DIR", "/srv/ai-station/data/ocr/outputs"))
OCR_TMP_DIR = Path(os.getenv("AI_STATION_OCR_TMP_DIR", "/srv/ai-station/data/ocr/tmp"))

OCR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OCR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OCR_TMP_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AI Station OCR Tool Server",
    version="0.1.0",
    description="Local OCR routing service for AI Station. Exposes OCR models as OpenAPI tools.",
)

OCR_MODELS = {
    "dots-mocr": {
        "label": "dots.mocr",
        "path": OCR_MODELS_DIR / "dots-mocr",
        "status": "runtime-pending",
        "preferred": True,
    },
    "dots-ocr": {
        "label": "dots.ocr",
        "path": OCR_MODELS_DIR / "dots-ocr",
        "status": "runtime-pending",
        "preferred": False,
    },
    "deepseek-ocr-2": {
        "label": "DeepSeek OCR 2",
        "path": OCR_MODELS_DIR / "deepseek-ocr-2",
        "status": "experimental-runtime-pending",
        "preferred": False,
    },
}


class OCRResult(BaseModel):
    job_id: str
    model: str
    input_filename: str
    output_dir: str
    text_path: str | None = None
    json_path: str
    status: Literal["completed", "failed"]
    message: str


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "ai-station-ocr",
        "models_dir": str(OCR_MODELS_DIR),
        "upload_dir": str(OCR_UPLOAD_DIR),
        "output_dir": str(OCR_OUTPUT_DIR),
    }


@app.get("/models")
def models():
    data = []
    for model_id, meta in OCR_MODELS.items():
        path = meta["path"]
        data.append({
            "id": model_id,
            "label": meta["label"],
            "preferred": meta["preferred"],
            "runtime_status": meta["status"],
            "path": str(path),
            "path_exists": path.exists(),
            "file_count": sum(1 for _ in path.rglob("*")) if path.exists() else 0,
        })
    return {"models": data}


def safe_filename(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    return cleaned[:180] or "upload"


def run_adapter(model: str, input_path: Path, output_dir: Path) -> dict:
    adapter = PROJECT_DIR / "apps" / "ocr" / "runtime" / f"{model}.sh"

    if not adapter.exists():
        return {
            "ok": False,
            "message": f"OCR runtime adapter is not implemented yet: {adapter}",
        }

    result = subprocess.run(
        ["bash", str(adapter), str(input_path), str(output_dir)],
        cwd=str(PROJECT_DIR),
        text=True,
        capture_output=True,
        timeout=1800,
        check=False,
    )

    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout[-8000:],
        "stderr": result.stderr[-8000:],
        "returncode": result.returncode,
    }


@app.post("/ocr", response_model=OCRResult)
async def ocr(
    file: UploadFile = File(...),
    model: str = Form("dots-mocr"),
):
    if model not in OCR_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown OCR model: {model}")

    meta = OCR_MODELS[model]
    if not meta["path"].exists():
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"OCR model path does not exist: {meta['path']}",
                "model": model,
            },
        )

    job_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    job_dir = OCR_OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_name = safe_filename(file.filename or "upload.bin")
    input_path = OCR_UPLOAD_DIR / f"{job_id}-{input_name}"

    with input_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    adapter_result = run_adapter(model, input_path, job_dir)

    json_path = job_dir / "result.json"
    text_path = job_dir / "result.md"

    payload = {
        "job_id": job_id,
        "model": model,
        "input_filename": input_name,
        "input_path": str(input_path),
        "output_dir": str(job_dir),
        "adapter_result": adapter_result,
    }

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if adapter_result.get("ok"):
        if not text_path.exists():
            text_path.write_text(adapter_result.get("stdout", ""), encoding="utf-8")

        return OCRResult(
            job_id=job_id,
            model=model,
            input_filename=input_name,
            output_dir=str(job_dir),
            text_path=str(text_path),
            json_path=str(json_path),
            status="completed",
            message="OCR completed.",
        )

    text_path.write_text(
        "# OCR failed\n\n"
        f"Model: {model}\n\n"
        f"Message: {adapter_result.get('message', '')}\n\n"
        "STDOUT:\n\n"
        f"{adapter_result.get('stdout', '')}\n\n"
        "STDERR:\n\n"
        f"{adapter_result.get('stderr', '')}\n",
        encoding="utf-8",
    )

    return OCRResult(
        job_id=job_id,
        model=model,
        input_filename=input_name,
        output_dir=str(job_dir),
        text_path=str(text_path),
        json_path=str(json_path),
        status="failed",
        message=adapter_result.get("message") or "OCR runtime failed. See output files.",
    )
