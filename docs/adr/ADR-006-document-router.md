# ADR-006: Document Router — Tika Default, PaddleOCR-VL for Hard Pages

- Status: Accepted (PaddleOCR-VL-1.6 weights and local image exist;
  production stays Tika + Tesseract until a golden-set report and the
  `ocr-vl` GPU profile can run)
- Date: 2026-07-23
- Updated: 2026-08-27

## Context

Apache Tika + Tesseract (fas+eng) is the verified extraction path. It
loses table structure, reading order, and layout on scans and complex
pages. The 2026-07 Docling trial stayed deferred. The 2026 upgrade
replaces that deferred VLM path with **PaddleOCR-VL-1.6** for hard
pages only.

## Options considered

1. Tika only (status quo).
2. Replace Tika with PaddleOCR-VL for every file.
3. Router: Tika for digitally extractable office/PDF text; PaddleOCR-VL-1.6
   for scans, images, tables, formulas, charts, screenshots, rotation,
   mixed Persian/English, and poor scans; Tesseract fas+eng via Tika OCR
   when PaddleOCR-VL is down or empty.

## Decision

Option 3. Rerankers are never part of this pipeline.

PaddleOCR-VL arrives as an isolated, digest-pinned, localhost-only,
off-by-default profile. Until that image and weights exist, the router
falls through to Tesseract. Do not add floating tags. Weights and the
local `ai-station/paddleocr-vl:1.6` image now exist; keep the profile
off while llama.cpp occupies the GPU.

## Evidence

- Tika golden set 2026-07-24: 5/5 public-safe fixtures
  (`benchmarks/results/20260724/documents/tika-golden-v1.json`).
- PaddleOCR-VL-1.6 weights are on disk and the local image is built.
  The `ocr-vl` Compose profile is not the live default until a golden-set
  report exists and the GPU is free. Until then `paddle_available=false`
  returns traffic to Tika/Tesseract.

## Rollback

`paddle_available=false` returns all traffic to Tika/Tesseract. Remove
the PaddleOCR Compose profile.

## Acceptance criteria

- Golden-set report comparing Tika vs PaddleOCR-VL per document class.
- Router promoted only for classes with measured wins.
- Unit tests in `tests/test_document_router.py` stay green.
