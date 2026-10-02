# doc-ocr Test Report

**Date:** 2026-10-02
**Scope:** Public-release hardening of the GMT800 OCR pipeline → `doc-ocr`

## What was tested

### Core pipeline (6 real pages, service-manual profile)
Pages: text, blank, troubleshooting, diagram, schematic (rotated), connector_pinout.
Source: GMT800 brake chapter scans (author's collection — not included in repo).

| Stage | Result |
|---|---|
| `doc-ocr ocr` | 6/6 pages, 0 errors, all page numbers found |
| `doc-ocr build` | 6-page PDF, 6.6MB, 0 skipped |
| `doc-ocr check` | 179 spans drawn, alignment verified |

### Bug found and fixed during testing

**Build crashed on report JSONs.** `doc-ocr build output/*.json` globbed the
report JSON (`test6_report.json`) alongside per-page JSONs. The build script
did `pj["file"]` → `KeyError: 'file'` → traceback → exit 2.

**Fix:** `doc-ocr build` now inspects each JSON, keeps only ones with a
`"file"` key (per-page format), and prints:
`doc-ocr build: skipping 1 non-page JSON (report/progress files)`.
Verified: build succeeds, correct 6 pages in output.

This is exactly the class of bug the "impossible to fuck up" principle targets
— a user doing the obvious thing (`output/*.json`) should not get a traceback.

### Error-path testing (all clean)

| Input | Output | Exit |
|---|---|---|
| `--pages /nonexistent` | `error: pages directory not found` + hint | 1 |
| `--sample /nonexistent.csv` | `error: sample CSV not found` + hint | 1 |
| `build` with no JSONs | `error: no OCR JSON files specified` + hint | 1 |
| `check` with bad PDF path | `error: PDF not found` | 1 |
| Unknown `--profile` | `error: unknown profile` + available list | 1 |

No tracebacks on any user error. Every error includes a hint.

### Sampler rewrite

The original `sampler.py` had hardcoded personal paths
(`~/workspace/gmt800-ocr-test/...`) and GM-specific category targets.
Rewrote as a general tool:
- `--manifest`, `--out`, `--n`, `--seed`, `--targets` flags
- Proportional sampling with floor of 1 per category
- Deterministic stride (not random) for sequence spread
- Tested: 5-page manifest → 4-page sample, correct stratification

### Security audit

```
grep -ri "urllib|requests|http|socket|urlopen" scripts/*.py → (none)
```

Zero network imports in the pipeline scripts. The `doc-ocr` CLI uses
`subprocess` only to invoke local scripts (not network). The only download
is the RapidOCR ONNX model on first run, handled by the RapidOCR library
itself. Verified offline operation is architecturally sound.

### What wasn't tested

- **Windows/macOS** — code is platform-agnostic but only ran on Linux
- **CloudCompare-equivalent** — N/A (no external binary needed for OCR)
- **Large batches** (100+ pages) — pilot ran 100 pages on the original;
  the public CLI wraps the same code paths
- **Non-Latin scripts** — documented as unsupported in REQUIREMENTS.md

## Files

- Test pages: `test-samples/pages/` (6 JPGs, author's scans — not for redistribution)
- Test outputs: `test-samples/output2/`, `test-samples/test6.pdf`
- QC image: `test-samples/qc_p1.png`
- Screenshots: `docs/screenshots/` (4 annotated PNGs + generator script)
