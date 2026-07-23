# ADR-006: Document Router — Tika Default, Docling Trial for Complex PDFs

- Status: Proposed
- Date: 2026-07-23

## Context

Apache Tika + Tesseract (fas+eng) is the verified extraction path. It
loses table structure, reading order, and layout on complex PDFs. Docling
(MIT, IBM-backed) adds layout models, TableFormer table structure, and
optional VLM pipelines.

## Options considered

1. Tika only (status quo).
2. Replace Tika with Docling.
3. Router: Tika for office formats and simple digital PDFs; Docling
   (standard pipeline, CPU) for complex/layout-heavy PDFs; OCR-aware path
   for scanned Persian documents; controlled fallback to Tika on Docling
   failure or timeout.

## Evidence

- Tika's format breadth (1000+ types) exceeds Docling's; removal would
  regress office-format coverage.
- Independent 2026 comparisons show Docling's strengths on structured
  PDFs but also hallucination risk in its VLM pipeline on dense numeric
  tables — the standard (non-VLM) pipeline is the safer default.
- Docling's VLM pipeline would compete for the GPU against the
  single-heavy-model policy; the CPU standard pipeline does not.
- No golden extraction test set exists yet, so quality claims are
  currently unmeasurable here.

## Decision

Adopt option 3, gated: build the golden test set first (non-sensitive
fixtures including Persian scans, tables, multi-column layouts), measure
Tika's baseline extraction quality, then trial Docling standard pipeline
behind the router in Phase 5. The VLM pipeline stays research-only.

## Consequences

- A routing decision point enters the document plane; failures must be
  visible (metrics + structured logs), not silent fallbacks.

## Risks

- Docling model downloads add supply-chain surface: pin versions and
  checksums like model artifacts.
- Cold-start latency of Docling models on CPU: measure before enabling.

## Rollback

Router flag returns all traffic to Tika; Docling container removed with
its Compose profile.

## Acceptance criteria

- Golden-set report comparing extraction quality (not visual impressions)
  for Tika vs Docling per document class; router promoted only for classes
  with measured wins.
