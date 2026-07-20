#!/usr/bin/env python3
import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.getenv("AI_STATION_UI_GATEWAY_HOST", "0.0.0.0")
PORT = int(os.getenv("AI_STATION_UI_GATEWAY_PORT", "8890"))
UPSTREAM = os.getenv("AI_STATION_GATEWAY_UPSTREAM", "http://127.0.0.1:8888/v1").rstrip("/")
OPENWEBUI_URL = os.getenv("AI_STATION_OPENWEBUI_URL", "http://127.0.0.1:3000").rstrip("/")
TIKA_URL = os.getenv("AI_STATION_TIKA_URL", "http://127.0.0.1:9998").rstrip("/")

# Open WebUI model ids -> gateway catalog ids
MODEL_MAP = {
    "general-qwen3.6": "general-qwen3_6-35b-a3b",
    "local-general": "general-qwen3_6-35b-a3b",
    "local-coder": "coder-qwen3-coder-30b-a3b",
    "local-reasoning": "reasoning-deepseek-r1-32b",
    "local-vision": "vision-qwen3-vl-32b",
}

MODEL_NAMES = {
    "general-qwen3.6": "General | Qwen3.6 35B A3B",
    "local-general": "Local General",
    "local-coder": "Local Coder",
    "local-reasoning": "Local Reasoning",
    "local-vision": "Local Vision",
}

MODEL_CAPABILITIES = {
    "vision": True,
    "file_upload": True,
    "file_context": True,
    "web_search": True,
    "image_generation": False,
    "code_interpreter": False,
    "terminal": False,
}


def guess_ext(mime: str) -> str:
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/tiff": ".tiff",
        "image/bmp": ".bmp",
        "application/pdf": ".pdf",
    }
    return mapping.get(mime, mimetypes.guess_extension(mime or "") or ".bin")


def tika_extract_bytes(file_bytes: bytes, filename: str, mime: str) -> str:
    url = f"{TIKA_URL}/tika"
    language_headers = ["fas+eng", "fas", "eng", ""]
    last_error = None

    for lang in language_headers:
        headers = {
            "Accept": "text/plain; charset=utf-8",
            "Content-Type": mime or "application/octet-stream",
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if lang:
            headers["X-Tika-OCRLanguage"] = lang

        req = urllib.request.Request(url, data=file_bytes, headers=headers, method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=600) as response:
                text = response.read().decode("utf-8", errors="replace").strip()
            if text:
                return text
            last_error = f"Tika returned empty text with OCR language={lang or 'default'}"
        except Exception as exc:
            last_error = repr(exc)
            continue

    return (
        "[Tika extraction completed but no readable text was extracted. "
        f"Last error: {last_error}]"
    )


def parse_data_url(url: str):
    match = re.match(r"^data:([^;]+);base64,(.*)$", url, re.DOTALL)
    if not match:
        return None
    mime = match.group(1)
    b64 = match.group(2)
    return base64.b64decode(b64), mime


def fetch_url_bytes(url: str, auth_header: str | None = None):
    if url.startswith("/"):
        url = OPENWEBUI_URL + url

    req = urllib.request.Request(url)
    if auth_header:
        req.add_header("Authorization", auth_header)

    with urllib.request.urlopen(req, timeout=120) as response:
        content_type = response.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip()
        return response.read(), content_type


def get_image_url_from_item(item: dict):
    typ = item.get("type")

    if typ == "image_url":
        image_url = item.get("image_url")
        if isinstance(image_url, dict):
            return image_url.get("url")
        if isinstance(image_url, str):
            return image_url

    if typ in {"input_image", "image"}:
        for key in ("image_url", "url", "data"):
            value = item.get(key)
            if isinstance(value, dict) and "url" in value:
                return value["url"]
            if isinstance(value, str):
                return value

    return None


def image_item_to_ocr_text(item: dict, index: int, auth_header: str | None = None) -> str:
    url = get_image_url_from_item(item)
    if not url:
        return f"[Attached image {index}: could not locate image data.]"

    try:
        parsed = parse_data_url(url)
        if parsed:
            file_bytes, mime = parsed
        else:
            file_bytes, mime = fetch_url_bytes(url, auth_header=auth_header)

        ext = guess_ext(mime)
        filename = f"attached-image-{index}{ext}"
        ocr_text = tika_extract_bytes(file_bytes, filename, mime)
        return (
            f"\n\n[Attached image {index} processed by local Apache Tika OCR]\n"
            f"{ocr_text}\n"
            f"[/Attached image {index} OCR]\n"
        )
    except Exception as exc:
        return (
            f"\n\n[Attached image {index} could not be OCR-processed locally. "
            f"Error: {repr(exc)}]\n"
        )


def sanitize_messages(messages, auth_header=None):
    cleaned = []

    for msg in messages:
        msg = dict(msg)
        content = msg.get("content")

        if isinstance(content, list):
            text_parts = []
            image_index = 1

            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type")
                    if item_type == "text":
                        text_parts.append(item.get("text", ""))
                    elif item_type in {"image_url", "input_image", "image"}:
                        text_parts.append(
                            image_item_to_ocr_text(item, image_index, auth_header=auth_header)
                        )
                        image_index += 1
                    elif "text" in item and isinstance(item["text"], str):
                        text_parts.append(item["text"])
                elif isinstance(item, str):
                    text_parts.append(item)

            msg["content"] = "\n".join(x for x in text_parts if x).strip()

        cleaned.append(msg)

    return cleaned


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        if self.path in {"/", "/health"}:
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "ai-station-ui-gateway",
                    "upstream": UPSTREAM,
                    "tika": TIKA_URL,
                    "models": list(MODEL_MAP.keys()),
                },
            )
            return

        if self.path in {"/v1/models", "/models"}:
            self._send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": model_id,
                            "object": "model",
                            "created": 0,
                            "owned_by": "ai-station",
                            "name": MODEL_NAMES[model_id],
                            "info": {
                                "meta": {
                                    "capabilities": MODEL_CAPABILITIES,
                                    "description": (
                                        "Local AI Station model with file upload, "
                                        "Tika OCR/RAG, and web search enabled."
                                    ),
                                }
                            },
                            "meta": {"capabilities": MODEL_CAPABILITIES},
                        }
                        for model_id in MODEL_MAP
                    ],
                },
            )
            return

        self._send_json(404, {"error": "not found", "path": self.path})

    def do_POST(self):
        if self.path not in {"/v1/chat/completions", "/chat/completions"}:
            self._send_json(404, {"error": "unsupported endpoint", "path": self.path})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)

        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            self._send_json(400, {"error": f"invalid json: {exc}"})
            return

        requested_model = body.get("model")
        mapped_model = MODEL_MAP.get(requested_model)
        if not mapped_model:
            self._send_json(
                400,
                {
                    "error": f"Model '{requested_model}' is not exposed by AI Station UI Gateway.",
                    "available_models": list(MODEL_MAP.keys()),
                },
            )
            return

        body["model"] = mapped_model

        if isinstance(body.get("messages"), list):
            body["messages"] = sanitize_messages(
                body["messages"],
                auth_header=self.headers.get("Authorization"),
            )

        upstream_url = f"{UPSTREAM}/chat/completions"
        req = urllib.request.Request(
            upstream_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": self.headers.get("Authorization", "Bearer local-not-used"),
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=900) as response:
                response_body = response.read()
                status = response.status
                content_type = response.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as exc:
            response_body = exc.read()
            status = exc.code
            content_type = exc.headers.get("Content-Type", "application/json")
        except Exception as exc:
            self._send_json(502, {"error": repr(exc), "upstream": upstream_url})
            return

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"AI Station UI Gateway listening on http://{HOST}:{PORT}", flush=True)
    print(f"Upstream: {UPSTREAM}", flush=True)
    print(f"Tika: {TIKA_URL}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
