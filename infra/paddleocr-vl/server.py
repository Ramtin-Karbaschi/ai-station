"""Loopback PaddleOCR-VL-1.6 HTTP wrapper. POST /predict returns {"text": "..."}."""

from __future__ import annotations

import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODEL_DIR = Path(os.environ.get("PADDLEOCR_VL_MODEL_DIR", "/models/ocr/paddleocr-vl-1.6"))
HOST = os.environ.get("PADDLEOCR_VL_HOST", "0.0.0.0")
PORT = int(os.environ.get("PADDLEOCR_VL_PORT", "8093"))

_pipeline = None


def load_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    from transformers import AutoProcessor, AutoModelForVision2Seq

    processor = AutoProcessor.from_pretrained(str(MODEL_DIR), trust_remote_code=True)
    model = AutoModelForVision2Seq.from_pretrained(str(MODEL_DIR), trust_remote_code=True)
    device = "cuda" if os.environ.get("PADDLEOCR_VL_DEVICE", "cuda") != "cpu" else "cpu"
    model = model.to(device)
    _pipeline = (processor, model, device)
    return _pipeline


def infer(image_bytes: bytes) -> str:
    from PIL import Image

    processor, model, device = load_pipeline()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": "OCR this document. Preserve tables and reading order."},
            ],
        }
    ]
    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )
    inputs = {key: value.to(device) for key, value in inputs.items()}
    output_ids = model.generate(**inputs, max_new_tokens=2048)
    text = processor.batch_decode(output_ids, skip_special_tokens=True)[0]
    return text.strip()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"paddleocr-vl: {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in {"", "/health", "/v1/models"}:
            body = json.dumps({"status": "ok", "engine": "paddleocr-vl-1.6"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/predict":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length)
        try:
            text = infer(payload)
            body = json.dumps({"text": text, "engine": "paddleocr-vl-1.6"}).encode()
            self.send_response(200)
        except Exception as exc:
            body = json.dumps({"text": "", "error": type(exc).__name__}).encode()
            self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    load_pipeline()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"paddleocr-vl listening on {HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
