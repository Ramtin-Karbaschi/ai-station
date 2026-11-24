"""Document intelligence routing: Tika first, PaddleOCR-VL for hard pages, Tesseract fallback.

Rerankers are never part of this pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

ExtractFn = Callable[[bytes, str, str], str]

DIGITAL_MIMES = frozenset(
    {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.oasis.opendocument.text",
        "text/plain",
        "text/html",
        "text/markdown",
        "application/rtf",
    }
)
IMAGE_MIMES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/tiff",
        "image/bmp",
        "image/gif",
    }
)
COMPLEX_CLASSES = frozenset(
    {
        "scanned_persian",
        "scanned_english",
        "table",
        "formula",
        "chart",
        "screenshot",
        "rotated",
        "poor_scan",
        "mixed_persian_english",
        "image",
    }
)


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    engine: str
    fallback_used: bool
    reason: str
    document_class: str


def classify_document(filename: str, mime: str, document_class: str | None = None) -> str:
    if document_class:
        return document_class
    lowered = (filename or "").lower()
    mime_l = (mime or "").lower()
    if mime_l in IMAGE_MIMES or lowered.endswith(
        (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp")
    ):
        return "image"
    if mime_l in DIGITAL_MIMES or lowered.endswith(
        (".pdf", ".doc", ".docx", ".odt", ".txt", ".html", ".md", ".rtf")
    ):
        return "digital"
    return "unknown"


def digital_text_is_good(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < 80:
        return False
    if stripped.startswith("[Tika extraction completed but no readable text"):
        return False
    printable = sum(1 for ch in stripped if ch.isprintable() or ch.isspace())
    return (printable / max(len(stripped), 1)) >= 0.55


def extract_document(
    file_bytes: bytes,
    filename: str,
    mime: str,
    *,
    tika_fn: ExtractFn,
    paddle_fn: ExtractFn | None = None,
    tesseract_fn: ExtractFn | None = None,
    document_class: str | None = None,
    paddle_available: bool = False,
) -> ExtractionResult:
    mime_class = classify_document(filename, mime)
    classified = document_class or mime_class
    tika_text = tika_fn(file_bytes, filename, mime)
    caller_marked_complex = document_class in COMPLEX_CLASSES
    if (
        mime_class == "digital"
        and not caller_marked_complex
        and classified not in COMPLEX_CLASSES
        and digital_text_is_good(tika_text)
    ):
        return ExtractionResult(
            text=tika_text,
            engine="tika",
            fallback_used=False,
            reason="digitally extractable text from Apache Tika",
            document_class=classified,
        )
    if (
        caller_marked_complex
        or classified in COMPLEX_CLASSES
        or mime_class == "image"
        or not digital_text_is_good(tika_text)
    ):
        if paddle_available and paddle_fn is not None:
            paddle_text = paddle_fn(file_bytes, filename, mime)
            if digital_text_is_good(paddle_text):
                return ExtractionResult(
                    text=paddle_text,
                    engine="paddleocr-vl-1.6",
                    fallback_used=False,
                    reason="layout/scan/complex page routed to PaddleOCR-VL-1.6",
                    document_class=classified,
                )
    tess_fn = tesseract_fn or tika_fn
    tess_text = tess_fn(file_bytes, filename, mime)
    distinct_tesseract = (
        tesseract_fn is not None and tesseract_fn is not tika_fn
    )
    engine = "tesseract" if distinct_tesseract else "tika-ocr"
    return ExtractionResult(
        text=tess_text,
        engine=engine,
        fallback_used=True,
        reason="PaddleOCR-VL unavailable or empty; Tesseract fas+eng via Tika OCR",
        document_class=classified,
    )


def describe_pipeline() -> Mapping[str, str]:
    return {
        "digital": "Apache Tika",
        "image_or_scan": "PaddleOCR-VL-1.6",
        "fallback": "Tesseract fas+eng via Tika OCR",
        "never": "reranker",
    }
