"""Local full-pipeline PaddleOCR-VL document service.

It accepts an image or multipage PDF and returns versioned JSON or a ZIP
evidence bundle with structured pages, true source crops, two PDF outputs,
cross-engine comparisons, numeric canaries, and a human-review queue.
"""

from __future__ import annotations

import csv
import difflib
import html
import io
import json
import os
import re
import statistics
import struct
import subprocess
import importlib.util
import tempfile
import threading
import time
import zipfile
from collections import defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

try:
    from ocr_quality import digits as _quality_digits
    from ocr_quality import evaluate_canaries as _quality_evaluate_canaries
    from ocr_quality import normalize_canary_text
    from ocr_quality import plain_text as _quality_plain_text
    from ocr_quality import review_queue as _quality_review_queue
except ModuleNotFoundError:  # direct test/module loading outside the image workdir
    _quality_spec = importlib.util.spec_from_file_location("ocr_quality", Path(__file__).with_name("ocr_quality.py"))
    if not _quality_spec or not _quality_spec.loader:
        raise
    _quality_module = importlib.util.module_from_spec(_quality_spec)
    _quality_spec.loader.exec_module(_quality_module)
    _quality_digits = _quality_module.digits
    _quality_evaluate_canaries = _quality_module.evaluate_canaries
    normalize_canary_text = _quality_module.normalize_canary_text
    _quality_plain_text = _quality_module.plain_text
    _quality_review_queue = _quality_module.review_queue

HOST = os.environ.get("PADDLEOCR_VL_HOST", "0.0.0.0")
PORT = int(os.environ.get("PADDLEOCR_VL_PORT", "8093"))
PIPELINE_VERSION = os.environ.get("PADDLEOCR_VL_PIPELINE_VERSION", "v1.6")
BACKEND_URL = os.environ.get("PADDLEOCR_VL_BACKEND_URL", "").strip()
MAX_BODY_BYTES = int(os.environ.get("PADDLEOCR_VL_MAX_BODY_BYTES", "268435456"))
SCHEMA_VERSION = "ai-station.ocr-document.v1"
ENGINE = "paddleocr-vl-1.6-full-pipeline"
FIGURE_LABELS = frozenset({"image", "figure", "chart", "table", "formula"})
NON_TEXT_LABELS = frozenset({"image", "figure", "chart"})

_pipeline: Any | None = None
_pipeline_lock = threading.Lock()


def _jsonable(value: Any) -> Any:
    """Convert result values without serializing full page-image arrays."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        converted: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"input_img", "output_img"}:
                continue
            converted[str(key)] = _jsonable(item)
        return converted
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return str(value)


def _image_size(value: Any) -> tuple[int, int] | None:
    if hasattr(value, "size") and isinstance(value.size, tuple) and len(value.size) == 2:
        return int(value.size[0]), int(value.size[1])
    shape = getattr(value, "shape", None)
    if shape is not None and len(shape) >= 2:
        return int(shape[1]), int(shape[0])
    return None


def _result_page_size(source_raw: dict[str, Any]) -> tuple[int, int] | None:
    width, height = source_raw.get("width"), source_raw.get("height")
    if isinstance(width, (int, float)) and isinstance(height, (int, float)) and width > 0 and height > 0:
        return int(width), int(height)
    candidates: list[Any] = []
    candidates.extend(source_raw.get(key) for key in ("input_img", "output_img"))
    pre = source_raw.get("doc_preprocessor_res")
    if isinstance(pre, dict):
        candidates.extend(pre.get(key) for key in ("input_img", "output_img"))
    for candidate in candidates:
        if candidate is not None and (size := _image_size(candidate)):
            return size
    return None


def load_pipeline() -> Any:
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    from paddleocr import PaddleOCRVL

    backend: dict[str, Any] = {}
    if BACKEND_URL:
        backend = {
            "vl_rec_backend": "vllm-server",
            "vl_rec_server_url": BACKEND_URL,
            "vl_rec_api_model_name": "PaddleOCR-VL-1.6-0.9B",
            "vl_rec_max_concurrency": 4,
        }
    _pipeline = PaddleOCRVL(
        pipeline_version=PIPELINE_VERSION,
        device="gpu",
        use_doc_orientation_classify=True,
        use_doc_unwarping=False,
        use_layout_detection=True,
        use_chart_recognition=True,
        use_seal_recognition=True,
        use_ocr_for_image_block=True,
        **backend,
    )
    return _pipeline


def _markdown_text(result: Any) -> str:
    markdown = getattr(result, "markdown", None)
    if not isinstance(markdown, dict):
        return ""
    value = markdown.get("markdown_texts", "")
    return "\n\n".join(str(item) for item in value) if isinstance(value, list) else str(value or "")


def _layout_scores(raw: dict[str, Any]) -> list[dict[str, Any]]:
    layout = raw.get("layout_det_res")
    if not isinstance(layout, dict):
        return []
    boxes = layout.get("boxes") or layout.get("bboxes") or []
    if boxes and all(isinstance(box, dict) for box in boxes):
        return [
            {
                "bbox": _jsonable(box.get("coordinate") or box.get("bbox") or []),
                "score": float(box["score"]) if box.get("score") is not None else None,
                "label": str(box.get("label")) if box.get("label") is not None else None,
            }
            for box in boxes
        ]
    scores = layout.get("scores") or []
    labels = layout.get("labels") or layout.get("label_names") or []
    return [
        {
            "bbox": _jsonable(box),
            "score": float(scores[index]) if index < len(scores) else None,
            "label": str(labels[index]) if index < len(labels) else None,
        }
        for index, box in enumerate(boxes)
    ]


def _bbox_distance(left: Iterable[float], right: Iterable[float]) -> float:
    left_values, right_values = list(left), list(right)
    return (
        sum(abs(float(a) - float(b)) for a, b in zip(left_values, right_values))
        if len(left_values) == len(right_values) == 4
        else float("inf")
    )


def _structured_page(result: Any, ordinal: int) -> dict[str, Any]:
    source_raw = getattr(result, "json", {})
    source_raw = source_raw if isinstance(source_raw, dict) else {}
    if isinstance(source_raw.get("res"), dict):
        source_raw = source_raw["res"]
    raw = _jsonable(source_raw)
    layout = _layout_scores(raw)
    blocks: list[dict[str, Any]] = []
    for fallback_order, block in enumerate(raw.get("parsing_res_list") or []):
        if not isinstance(block, dict):
            continue
        bbox = block.get("block_bbox") or block.get("bbox") or []
        nearest = min(layout, key=lambda item: _bbox_distance(bbox, item["bbox"]), default=None)
        confidence = nearest.get("score") if nearest else None
        blocks.append(
            {
                "id": int(block.get("block_id", fallback_order)),
                "reading_order": block.get("block_order", fallback_order),
                "label": str(block.get("block_label", "unknown")),
                "bbox": bbox,
                "text": str(block.get("block_content", "") or ""),
                "confidence": confidence,
                "confidence_source": "layout_detector" if confidence is not None else None,
                "recognition_confidence": None,
                "recognition_confidence_note": "Generative VLM has no calibrated text confidence.",
            }
        )
    size = _result_page_size(source_raw)
    page_index = raw.get("page_index")
    return {
        "page_number": int(page_index) + 1 if isinstance(page_index, int) else ordinal,
        "pixel_size": list(size) if size else None,
        "text": _markdown_text(result),
        "vl_markdown": _markdown_text(result),
        "blocks": sorted(
            blocks,
            key=lambda item: (
                item["reading_order"] is None,
                item["reading_order"] if item["reading_order"] is not None else item["id"],
            ),
        ),
        "engine_payload": raw,
    }


def _plain_text(markdown: str) -> str:
    return _quality_plain_text(markdown)


def _evaluate_canaries(pages: list[dict[str, Any]], canaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _quality_evaluate_canaries(pages, canaries)


def _tesseract_page(png: bytes, page_number: int) -> dict[str, Any]:
    command = ["tesseract", "stdin", "stdout", "-l", "fas+eng", "--psm", "3", "tsv"]
    completed = subprocess.run(command, input=png, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode != 0:
        return {
            "page_number": page_number,
            "text": "",
            "words": [],
            "mean_confidence": None,
            "error": completed.stderr.decode("utf-8", "replace")[-1000:],
        }
    reader = csv.DictReader(io.StringIO(completed.stdout.decode("utf-8", "replace")), delimiter="\t")
    words: list[dict[str, Any]] = []
    lines: dict[tuple[int, int, int], list[str]] = defaultdict(list)
    confidences: list[float] = []
    for row in reader:
        text = (row.get("text") or "").strip()
        try:
            confidence = float(row.get("conf") or -1)
        except ValueError:
            confidence = -1
        if not text or confidence < 0:
            continue
        left, top = int(row.get("left") or 0), int(row.get("top") or 0)
        width, height = int(row.get("width") or 0), int(row.get("height") or 0)
        key = (int(row.get("block_num") or 0), int(row.get("par_num") or 0), int(row.get("line_num") or 0))
        words.append(
            {
                "text": text,
                "bbox": [left, top, left + width, top + height],
                "confidence": confidence / 100.0,
                "line_id": list(key),
            }
        )
        confidences.append(confidence / 100.0)
        lines[key].append(text)
    return {
        "page_number": page_number,
        "text": "\n".join(" ".join(parts) for parts in lines.values()),
        "words": words,
        "mean_confidence": statistics.fmean(confidences) if confidences else None,
        "error": None,
    }


def _digits(text: str) -> list[str]:
    return _quality_digits(text)


def _png_size(png: bytes) -> tuple[int, int]:
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
        raise ValueError("expected PNG bytes with an IHDR header")
    return struct.unpack(">II", png[16:24])


def _fuse_page(page: dict[str, Any], tesseract: dict[str, Any], png: bytes) -> None:
    """Fuse VLM layout/text with Tesseract evidence without inventing confidence.

    The VLM remains primary.  When the engines disagree on digits and the
    conventional OCR evidence is reasonably confident, the complete affected
    block is selected from Tesseract.  This is deliberately conservative: a
    digit error is much more consequential for engineering citations than a
    stylistic spelling variation.
    """
    paddle_width, paddle_height = _page_scale(page, png)
    tess_width, tess_height = _png_size(png)
    sx, sy = paddle_width / tess_width, paddle_height / tess_height
    words = tesseract.get("words") or []
    selected_text: list[str] = []
    for block in page.get("blocks", []):
        bbox = block.get("bbox") or []
        vl_text = str(block.get("text") or "")
        if str(block.get("label", "")).lower() in NON_TEXT_LABELS:
            block["vl_text"] = vl_text
            block["tesseract_text"] = ""
            block["tesseract_confidence"] = None
            block["fusion_similarity"] = 0.0
            block["digit_disagreement"] = False
            block["selected_engine"] = ENGINE
            block["selection_reason"] = "non_text_layout_block"
            selected_text.append(vl_text)
            continue
        if len(bbox) != 4:
            selected_text.append(vl_text)
            continue
        x0, y0, x1, y1 = (float(value) for value in bbox)
        matching = []
        for word in words:
            wx0, wy0, wx1, wy1 = (float(value) for value in word.get("bbox", []))
            center_x, center_y = (wx0 + wx1) * sx / 2, (wy0 + wy1) * sy / 2
            if x0 - 4 <= center_x <= x1 + 4 and y0 - 4 <= center_y <= y1 + 4:
                matching.append(word)
        by_line: dict[tuple[int, ...], list[dict[str, Any]]] = defaultdict(list)
        for word in matching:
            by_line[tuple(word.get("line_id") or [])].append(word)
        tess_text = "\n".join(" ".join(str(word["text"]) for word in line) for line in by_line.values())
        confidences = [float(word["confidence"]) for word in matching if word.get("confidence") is not None]
        tess_confidence = statistics.fmean(confidences) if confidences else None
        normalized_vl = normalize_canary_text(_plain_text(vl_text))
        normalized_tess = normalize_canary_text(tess_text)
        fusion_similarity = (
            difflib.SequenceMatcher(None, normalized_vl, normalized_tess, autojunk=False).ratio()
            if normalized_vl and normalized_tess
            else 0.0
        )
        length_ratio = len(normalized_vl) / len(normalized_tess) if normalized_tess else 0.0
        digit_disagreement = _digits(vl_text) != _digits(tess_text) and bool(_digits(vl_text) or _digits(tess_text))
        select_tesseract = bool(
            tess_text
            and (
                not _plain_text(vl_text)
                or (
                    digit_disagreement
                    and tess_confidence is not None
                    and tess_confidence >= 0.70
                    and fusion_similarity >= 0.55
                    and 0.5 <= length_ratio <= 2.0
                )
            )
        )
        block["vl_text"] = vl_text
        block["tesseract_text"] = tess_text
        block["tesseract_confidence"] = tess_confidence
        block["fusion_similarity"] = fusion_similarity
        block["digit_disagreement"] = digit_disagreement
        block["selected_engine"] = "tesseract-5-fas+eng" if select_tesseract else ENGINE
        block["selection_reason"] = "digit_disagreement_with_textual_alignment" if select_tesseract else "vl_primary"
        block["text"] = tess_text if select_tesseract else vl_text
        selected_text.append(block["text"])
    page["text"] = "\n\n".join(text for text in selected_text if text)
    page["fusion_policy"] = "VLM primary; high-confidence Tesseract block selected on digit disagreement."


def _suspicious_full_page_table(page: dict[str, Any]) -> bool:
    size = page.get("pixel_size") or []
    if len(size) != 2 or not size[0] or not size[1]:
        return False
    page_area = float(size[0]) * float(size[1])
    for block in page.get("blocks", []):
        if str(block.get("label", "")).lower() != "table":
            continue
        bbox = block.get("bbox") or []
        if len(bbox) != 4:
            continue
        area = max(0.0, float(bbox[2]) - float(bbox[0])) * max(0.0, float(bbox[3]) - float(bbox[1]))
        if area / page_area >= 0.45:
            return True
    return False


def _apply_page_ocr_fallback(page: dict[str, Any], fallback: dict[str, Any]) -> None:
    text = str(fallback.get("text") or "").strip()
    if not text:
        return
    for block in page.get("blocks", []):
        block["artifact_only"] = True
    width, height = page.get("pixel_size") or [1, 1]
    page.setdefault("blocks", []).append(
        {
            "id": max((int(block.get("id", 0)) for block in page.get("blocks", [])), default=0) + 1,
            "reading_order": 0,
            "label": "page_ocr_fallback",
            "bbox": [0, 0, width, height],
            "text": text,
            "confidence": None,
            "confidence_source": None,
            "recognition_confidence": None,
            "recognition_confidence_note": "Generative VLM has no calibrated text confidence.",
            "selected_engine": ENGINE,
            "selection_reason": "full_page_ocr_after_suspicious_table_layout",
            "digit_disagreement": False,
            "artifact_only": False,
        }
    )
    page["text"] = text
    page["layout_fallback"] = {
        "reason": "table_block_covered_at_least_45_percent_of_page",
        "prompt_label": "ocr",
        "original_text": page.get("vl_markdown", ""),
        "engine_payload": fallback.get("engine_payload"),
    }


def _render_pages(source_path: Path, dpi: int) -> tuple[int, list[bytes]]:
    import fitz

    document = fitz.open(source_path)
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    rendered = [page.get_pixmap(matrix=matrix, alpha=False).tobytes("png") for page in document]
    count = document.page_count
    document.close()
    return count, rendered


def _compare_pages(pages: list[dict[str, Any]], tesseract_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tess_by_page = {page["page_number"]: page for page in tesseract_pages}
    comparisons = []
    for page in pages:
        tess = tess_by_page.get(page["page_number"], {})
        primary = normalize_canary_text(_plain_text(page.get("text", "")))
        secondary = normalize_canary_text(tess.get("text", ""))
        comparisons.append(
            {
                "page_number": page["page_number"],
                "paddleocr_vl_characters": len(primary),
                "tesseract_characters": len(secondary),
                "normalized_sequence_similarity": difflib.SequenceMatcher(None, primary, secondary, autojunk=False).ratio(),
                "tesseract_mean_confidence": tess.get("mean_confidence"),
            }
        )
    return comparisons


def _review_queue(
    pages: list[dict[str, Any]], comparisons: list[dict[str, Any]], canaries: list[dict[str, Any]], expected_pages: int
) -> list[dict[str, Any]]:
    return _quality_review_queue(pages, comparisons, canaries, expected_pages)


def _font_path() -> str | None:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoNaskhArabic-Regular.ttf",
    )
    return next((path for path in candidates if Path(path).is_file()), None)


def _page_scale(page: dict[str, Any], png: bytes) -> tuple[int, int]:
    if page.get("pixel_size"):
        width, height = page["pixel_size"]
        if width and height:
            return int(width), int(height)
    from PIL import Image

    with Image.open(io.BytesIO(png)) as image:
        return image.size


def _pdf_rect(block_bbox: list[float], pixel_size: tuple[int, int], pdf_rect: Any) -> Any:
    import fitz

    x0, y0, x1, y1 = (float(value) for value in block_bbox)
    width, height = pixel_size
    return fitz.Rect(
        pdf_rect.x0 + x0 * pdf_rect.width / width,
        pdf_rect.y0 + y0 * pdf_rect.height / height,
        pdf_rect.x0 + x1 * pdf_rect.width / width,
        pdf_rect.y0 + y1 * pdf_rect.height / height,
    )


def _is_exportable_figure(block: dict[str, Any]) -> bool:
    """Exclude diagnostic layout artifacts from user-facing crop exports."""
    return str(block.get("label", "unknown")).lower() in FIGURE_LABELS and not bool(block.get("artifact_only"))


def _insert_hidden_text(page: Any, rect: Any, value: str, fontfile: str | None) -> None:
    """Place extractable Unicode text inside its source block, invisibly."""
    import fitz

    try:
        from bidi.algorithm import get_display
    except ImportError:  # pragma: no cover - compatibility fallback for minimal images
        get_display = None

    lines = [line.strip() for line in _plain_text(value).splitlines() if line.strip()]
    if not lines:
        return
    line_height = max(2.0, rect.height / max(len(lines), 1))
    for index, line in enumerate(lines):
        # PyMuPDF's simple text writer emits RTL glyphs in visual order.  Feed
        # RTL strings in visual order so extraction returns the logical order.
        if any("\u0600" <= char <= "\u06ff" for char in line):
            if get_display is not None:
                emitted = get_display(line)
            else:
                emitted = line[::-1]
                emitted = re.sub(r"[0-9\u06f0-\u06f9\u0660-\u0669]+", lambda match: match.group(0)[::-1], emitted)
        else:
            emitted = line
        approximate_width = max(len(line) * 0.55, 1.0)
        font_size = max(2.0, min(10.0, line_height * 0.75, rect.width / approximate_width))
        baseline = min(rect.y1 - 0.5, rect.y0 + (index + 0.8) * line_height)
        kwargs: dict[str, Any] = {
            "fontsize": font_size,
            "render_mode": 3,
            "overlay": True,
        }
        if fontfile:
            kwargs.update({"fontname": "DejaVuSans", "fontfile": fontfile})
        page.insert_text(fitz.Point(rect.x0, baseline), emitted, **kwargs)


def _write_artifacts(source_path: Path, output_dir: Path, pages: list[dict[str, Any]], rendered: list[bytes]) -> dict[str, Any]:
    import fitz
    from PIL import Image

    source = fitz.open(source_path)
    searchable = fitz.open(stream=source.tobytes(), filetype="pdf")
    reconstructed = fitz.open()
    crops_dir = output_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    fontfile = _font_path()
    crop_manifest: list[dict[str, Any]] = []
    for index, source_page in enumerate(source):
        structured, png = pages[index], rendered[index]
        pixel_size = _page_scale(structured, png)
        target_page = reconstructed.new_page(width=source_page.rect.width, height=source_page.rect.height)
        target_page.draw_rect(target_page.rect, color=None, fill=(1, 1, 1), overlay=False)
        source_image = Image.open(io.BytesIO(png)).convert("RGB")
        for block in structured.get("blocks", []):
            bbox = block.get("bbox") or []
            if len(bbox) != 4:
                continue
            rect, text, label = _pdf_rect(bbox, pixel_size, source_page.rect), block.get("text", ""), str(block.get("label", "unknown")).lower()
            artifact_only = bool(block.get("artifact_only"))
            if text and not artifact_only and label not in NON_TEXT_LABELS:
                _insert_hidden_text(searchable[index], rect, text, fontfile)
            # Layout models occasionally label an entire watermarked page as a
            # table.  Such blocks are retained as diagnostic evidence, but
            # must never become exported figure/table crops.
            if _is_exportable_figure(block):
                scale_x = source_image.width / pixel_size[0]
                scale_y = source_image.height / pixel_size[1]
                left, top, right, bottom = [
                    int(round(value))
                    for value in (
                        bbox[0] * scale_x,
                        bbox[1] * scale_y,
                        bbox[2] * scale_x,
                        bbox[3] * scale_y,
                    )
                ]
                left, right = max(0, min(left, source_image.width - 1)), max(left + 1, min(right, source_image.width))
                top, bottom = max(0, min(top, source_image.height - 1)), max(top + 1, min(bottom, source_image.height))
                crop = source_image.crop((left, top, right, bottom))
                filename = f"page-{index + 1:04d}-block-{int(block['id']):04d}-{label}.png"
                crop_path = crops_dir / filename
                crop.save(crop_path, format="PNG")
                target_page.insert_image(rect, filename=str(crop_path), keep_proportion=False)
                crop_manifest.append({"page": index + 1, "block_id": block["id"], "label": label, "bbox": bbox, "path": f"crops/{filename}"})
            elif text and not artifact_only:
                direction = "rtl" if any("\u0600" <= char <= "\u06ff" for char in text) else "ltr"
                body = f'<div dir="{direction}" style="text-align:{"right" if direction == "rtl" else "left"}">{html.escape(text).replace(chr(10), "<br>")}</div>'
                if hasattr(target_page, "insert_htmlbox"):
                    target_page.insert_htmlbox(rect, body, css="body{font-family:sans-serif;font-size:9pt;line-height:1.15;}", scale_low=0.25, overlay=True)
                else:
                    kwargs = {"fontsize": max(5.0, min(14.0, rect.height * 0.65)), "overlay": True}
                    if fontfile:
                        kwargs.update({"fontname": "DejaVuSans", "fontfile": fontfile})
                    target_page.insert_textbox(rect, text, **kwargs)
        source_image.close()
    searchable_path, reconstructed_path = output_dir / "searchable-original.pdf", output_dir / "reconstructed-selectable.pdf"
    searchable.save(searchable_path, garbage=4, deflate=True)
    reconstructed.save(reconstructed_path, garbage=4, deflate=True)
    source.close()
    searchable.close()
    reconstructed.close()
    return {"searchable_pdf": searchable_path.name, "reconstructed_pdf": reconstructed_path.name, "crops": crop_manifest}


def parse_document(
    payload: bytes, filename: str, *, dpi: int, canaries: list[dict[str, Any]], make_bundle: bool
) -> tuple[dict[str, Any], bytes | None]:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
        suffix = ".pdf" if payload.startswith(b"%PDF") else ".png"
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="ai-station-ocr-") as temporary:
        temp_dir, source_path = Path(temporary), Path(temporary) / f"source{suffix}"
        source_path.write_bytes(payload)
        pipeline = load_pipeline()
        with _pipeline_lock:
            paddle_results = list(
                pipeline.predict(
                    input=str(source_path),
                    use_doc_orientation_classify=True,
                    use_doc_unwarping=False,
                    use_layout_detection=True,
                    use_chart_recognition=True,
                    use_seal_recognition=True,
                    use_ocr_for_image_block=True,
                    format_block_content=True,
                    max_new_tokens=4000,
                    temperature=0.0,
                )
            )
        pages = [_structured_page(result, index + 1) for index, result in enumerate(paddle_results)]
        expected_pages, rendered = _render_pages(source_path, dpi)
        tesseract_pages = [_tesseract_page(png, index + 1) for index, png in enumerate(rendered)]
        for page, tesseract, png in zip(pages, tesseract_pages, rendered):
            _fuse_page(page, tesseract, png)
        for index, (page, png) in enumerate(zip(pages, rendered), 1):
            if not _suspicious_full_page_table(page):
                continue
            fallback_path = temp_dir / f"page-{index:04d}-ocr-fallback.png"
            fallback_path.write_bytes(png)
            with _pipeline_lock:
                fallback_results = list(
                    pipeline.predict(
                        input=str(fallback_path),
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_layout_detection=False,
                        prompt_label="ocr",
                        format_block_content=True,
                        max_new_tokens=4000,
                        temperature=0.0,
                    )
                )
            if fallback_results:
                _apply_page_ocr_fallback(page, _structured_page(fallback_results[0], index))
        comparisons = _compare_pages(pages, tesseract_pages)
        canary_results = _evaluate_canaries(pages, canaries)
        queue = _review_queue(pages, comparisons, canary_results, expected_pages)
        response: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "engine": ENGINE,
            "pipeline_version": PIPELINE_VERSION,
            "source": {"filename": filename, "bytes": len(payload), "pages": expected_pages},
            "pages": pages,
            "comparison": {
                "engines": [ENGINE, "tesseract-5-fas+eng"],
                "pages": comparisons,
                "tesseract": tesseract_pages,
            },
            "canaries": canary_results,
            "review_queue": queue,
            "acceptance": {
                "zero_page_loss": len(pages) == expected_pages,
                "all_canaries_passed": all(item["passed"] for item in canary_results),
                "human_review_required": bool(queue),
                "engineering_citation_ready": not queue,
            },
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        bundle_bytes: bytes | None = None
        if make_bundle:
            bundle_dir = temp_dir / "bundle"
            bundle_dir.mkdir()
            response["artifacts"] = _write_artifacts(source_path, bundle_dir, pages, rendered)
            (bundle_dir / "structured.json").write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
            (bundle_dir / "review-queue.json").write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
            pages_dir = bundle_dir / "pages"
            pages_dir.mkdir()
            for page in pages:
                (pages_dir / f"page-{page['page_number']:04d}.md").write_text(page.get("text", ""), encoding="utf-8")
            (bundle_dir / "manifest.json").write_text(
                json.dumps(
                    {"schema_version": SCHEMA_VERSION, "source": response["source"], "artifacts": response["artifacts"], "acceptance": response["acceptance"]},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for path in sorted(bundle_dir.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(bundle_dir).as_posix())
            bundle_bytes = buffer.getvalue()
        return response, bundle_bytes


class Handler(BaseHTTPRequestHandler):
    server_version = "AIStationOCR/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"paddleocr-vl: {fmt % args}", flush=True)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, value: dict[str, Any]) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/")
        if path in {"", "/health", "/v1/models"}:
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "engine": ENGINE,
                    "pipeline_version": PIPELINE_VERSION,
                    "schema_version": SCHEMA_VERSION,
                    "pipeline_loaded": _pipeline is not None,
                    "recognition_backend": "vllm-server" if BACKEND_URL else "paddle-dynamic",
                },
            )
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") not in {"/predict", "/v1/documents:parse"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_content_length"})
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE if length > MAX_BODY_BYTES else HTTPStatus.BAD_REQUEST
            self._send_json(status, {"error": "invalid_body_size", "max_body_bytes": MAX_BODY_BYTES})
            return
        payload, query = self.rfile.read(length), parse_qs(parsed.query)
        filename = Path(self.headers.get("X-Filename", "document.pdf")).name
        make_bundle = query.get("bundle", ["0"])[0].lower() in {"1", "true", "yes"}
        try:
            dpi = max(150, min(400, int(query.get("dpi", ["300"])[0])))
            canaries = json.loads(self.headers.get("X-OCR-Canaries", "[]"))
            if not isinstance(canaries, list):
                raise ValueError("canaries must be a list")
            result, bundle = parse_document(payload, filename, dpi=dpi, canaries=canaries, make_bundle=make_bundle)
            self._send(HTTPStatus.OK, bundle, "application/zip") if make_bundle and bundle is not None else self._send_json(HTTPStatus.OK, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request", "detail": str(exc)})
        except Exception as exc:
            print(f"paddleocr-vl: request failed: {type(exc).__name__}: {exc}", flush=True)
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "document_processing_failed", "exception": type(exc).__name__, "detail": str(exc)},
            )


def main() -> None:
    # Startup fails if the complete pipeline cannot initialize. A recognizer-
    # only or partially downloaded service must never report healthy.
    load_pipeline()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"{ENGINE} listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
