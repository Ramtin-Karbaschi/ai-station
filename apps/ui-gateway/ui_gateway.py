#!/usr/bin/env python3
import base64
import json
import mimetypes
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.getenv("AI_STATION_UI_GATEWAY_HOST", "0.0.0.0")
PORT = int(os.getenv("AI_STATION_UI_GATEWAY_PORT", "8890"))
UPSTREAM = os.getenv("AI_STATION_GATEWAY_UPSTREAM", "http://127.0.0.1:8888/v1").rstrip("/")
DOCLING_URL = os.getenv("AI_STATION_DOCLING_URL", "http://127.0.0.1:5001").rstrip("/")
OPENWEBUI_URL = os.getenv("AI_STATION_OPENWEBUI_URL", "http://127.0.0.1:3000").rstrip("/")
TIKA_URL = os.getenv("AI_STATION_TIKA_URL", "http://127.0.0.1:9998").rstrip("/")

MODEL_MAP = {
    "general-qwen3.6": "general-qwen3_6-35b-a3b",
    "thinking-deepseek-r1": "thinking-deepseek-r1-qwen-32b",
    "coding-qwen3-coder": "coder-qwen3-coder-30b-a3b",
    "coding-qwen3-coder-next": "coder-qwen3-coder-next-80b-a3b",
}

MODEL_NAMES = {
    "general-qwen3.6": "general-qwen3.6",
    "thinking-deepseek-r1": "thinking-deepseek-r1",
    "coding-qwen3-coder": "coding-qwen3-coder",
    "coding-qwen3-coder-next": "coding-qwen3-coder-next",
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


def extract_text_from_docling_response(data):
    if isinstance(data, dict):
        for key in ("md_content", "markdown", "text_content", "text"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        for value in data.values():
            found = extract_text_from_docling_response(value)
            if found:
                return found

    elif isinstance(data, list):
        for item in data:
            found = extract_text_from_docling_response(item)
            if found:
                return found

    return ""


def multipart_post_file(url: str, file_bytes: bytes, filename: str, mime: str, fields: dict, timeout: int = 300):
    boundary = "----AIStationBoundary" + uuid.uuid4().hex
    chunks = []

    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
        f"Content-Type: {mime or 'application/octet-stream'}\r\n\r\n".encode()
    )
    chunks.append(file_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())

    body = b"".join(chunks)

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


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

        req = urllib.request.Request(
            url,
            data=file_bytes,
            headers=headers,
            method="PUT",
        )

        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                text = r.read().decode("utf-8", errors="replace").strip()

            if text:
                return text

            last_error = f"Tika returned empty text with OCR language={lang or 'default'}"

        except Exception as e:
            last_error = repr(e)
            continue

    return f"[Tika extraction completed but no readable text was extracted. Last error: {last_error}]"


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

    with urllib.request.urlopen(req, timeout=120) as r:
        content_type = r.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip()
        return r.read(), content_type


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

    except Exception as e:
        return (
            f"\n\n[Attached image {index} could not be OCR-processed locally. "
            f"Error: {repr(e)}]\n"
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
                        text_parts.append(image_item_to_ocr_text(item, image_index, auth_header=auth_header))
                        image_index += 1

                    else:
                        # Preserve unknown textual items when possible.
                        if "text" in item and isinstance(item["text"], str):
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
            self._send_json(200, {
                "ok": True,
                "service": "ai-station-ui-gateway",
                "upstream": UPSTREAM,
                "docling": DOCLING_URL,
                "models": list(MODEL_MAP.keys()),
            })
            return

        if self.path in {"/v1/models", "/models"}:
            self._send_json(200, {
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
                                "description": "Local AI Station model with file upload, OCR/RAG, image OCR routing, and web search enabled."
                            }
                        },
                        "meta": {
                            "capabilities": MODEL_CAPABILITIES
                        }
                    }
                    for model_id in MODEL_MAP
                ],
            })
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
        except Exception as e:
            self._send_json(400, {"error": f"invalid json: {e}"})
            return

        requested_model = body.get("model")
        mapped_model = MODEL_MAP.get(requested_model)

        if not mapped_model:
            self._send_json(400, {
                "error": f"Model '{requested_model}' is not exposed by AI Station UI Gateway.",
                "available_models": list(MODEL_MAP.keys()),
            })
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
            with urllib.request.urlopen(req, timeout=900) as r:
                response_body = r.read()
                status = r.status
                content_type = r.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            response_body = e.read()
            status = e.code
            content_type = e.headers.get("Content-Type", "application/json")
        except Exception as e:
            self._send_json(502, {"error": repr(e), "upstream": upstream_url})
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
    print(f"Tika: {DOCLING_URL}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
