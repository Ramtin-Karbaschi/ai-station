# Document extraction golden-set plan (Phase 5 scaffold)

Golden fixtures must be non-sensitive. Suggested classes:

1. Simple office document (Tika expected to win or tie)
2. Clean digital PDF
3. Multi-column PDF with tables
4. Scanned Persian page (OCR path)
5. Failure/timeout fixture

Measure extraction quality with structural checks (required headings,
table cell counts, Persian character presence), not visual impressions.

Docling remains behind a router until this set exists and Tika baseline
scores are recorded.
