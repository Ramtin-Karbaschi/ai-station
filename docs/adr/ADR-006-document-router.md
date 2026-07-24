# ADR-006: Document Router — Tika Default, Docling Trial for Complex PDFs

- Status: Accepted (Docling trial deferred)
- Date: 2026-07-23
- Updated: 2026-07-24

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
- Phase 5 golden fixtures now exist; Tika baseline scored 5/5 on the
  public-safe set (`benchmarks/results/20260724/documents/tika-golden-v1.json`).
  No failing fixture class yet justifies installing Docling.

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

## Phase 5 evidence (2026-07-24)

Tika baseline on the public-safe golden set:
`benchmarks/results/20260724/documents/tika-golden-v1.json`
(5/5 fixtures passed structural checks). No Docling install is justified
until a fixture class fails Tika (or a harder scanned-PDF OCR set is
added). Router design remains the long-term path; production stays Tika.
