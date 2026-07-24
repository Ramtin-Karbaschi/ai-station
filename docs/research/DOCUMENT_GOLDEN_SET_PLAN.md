# Document extraction golden-set plan (Phase 5)

Golden fixtures are non-sensitive and live under
`benchmarks/datasets/documents/`.

## Fixture classes

1. Simple office document (`01-simple-office.txt`)
2. Clean digital PDF (`02-clean-digital.pdf`)
3. Multi-column / table-like layout (`03-multicolumn.txt`)
4. Scanned Persian placeholder (`04-persian-scan-placeholder.txt`)
5. Failure/timeout probe (`05-timeout-probe.txt`)

Manifest: `benchmarks/datasets/documents/golden_manifest.json`

## Structural checks

- required headings / tokens
- Persian character presence where required
- digit/table cell counts for layout fixtures
- latency budget for the timeout probe

## Runner

~~~bash
python3 benchmarks/runners/run_document_golden.py \
  --out benchmarks/results/YYYYMMDD/documents/tika-golden-v1.json
~~~

## Decision gate (ADR-006)

Keep Tika as default. Trial Docling only for fixture classes where the Tika
baseline fails structural checks and Docling shows measured wins under the
CPU standard pipeline.
