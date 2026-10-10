# doc-ocr regression golden MANIFEST

Regression gate for the document-ocr pipeline: 10 representative service-manual
pages, OCR'd once by the pipeline itself; `test_regression.py` re-runs the
pipeline and fails on any byte-level difference.

## Golden generation

- **Date:** 2026-10-02 23:02 UTC
- **Pipeline version:** 0.1.0 (released 2026-10-02) + `[Unreleased]` work from
  CHANGELOG.md. (The pipeline directory is not a git repo, so there is no
  commit hash; md5 fingerprints of the exact code/config used are below.)
- **Command used to generate:**
  `venv/bin/python scripts/pipeline_parallel.py --sample tests/regression_sample.csv --pages ~/workspace/gmt800-ocr-test/production/pages --out <tmp> --workers 2 --config-dir profiles/service-manual`
  (i.e. the same code path as `doc-ocr ocr --profile service-manual`; the
  parallel runner reuses `pipeline.py`'s `process_page` and its own docstring
  states same inputs produce byte-identical outputs.)
- **Config profile:** `profiles/service-manual` (validated tuning for these pages)
- **Normalization:** `tests/normalize.py` strips volatile keys (`timings`,
  `elapsed_s`) and serializes canonically (sorted keys, indent 2, LF,
  trailing newline). Everything else — box text, box geometry, confidence
  scores, header/body text, counts — is pinned exactly.

## Source page mapping

| Golden file     | Source page scan                              | Type             | Chapter          | Boxes |
|-----------------|-----------------------------------------------|------------------|------------------|-------|
| `page-01.json`  | `GMT00ST_1_BRAKE_00007.jpg`                   | schematic        | BRAKE            | 187   |
| `page-02.json`  | `GMT00ST_1_BRAKE_00158.jpg`                   | connector_pinout | BRAKE            | 109   |
| `page-03.json`  | `GMT00ST_1_DRIVELINE_AXLE_00185.jpg`          | schematic_text   | DRIVELINE        | 96    |
| `page-04.json`  | `GMT00ST_3_ENGINE_00966.jpg`                  | schematic        | ENGINE           | 116   |
| `page-05.json`  | `GMT00ST_3_ENGINE_01708.jpg`                  | schematic_text   | ENGINE           | 231   |
| `page-06.json`  | `GMT00ST_3_ENGINE_01414.jpg`                  | connector_pinout | ENGINE           | 105   |
| `page-07.json`  | `GMT00ST_4_BODYACCESSORIES_00441.jpg`         | schematic        | BODYACCESSORIES  | 110   |
| `page-08.json`  | `GMT00ST_4_BODYACCESSORIES_00547.jpg`         | connector_pinout | BODYACCESSORIES  | 174   |
| `page-09.json`  | `GMT00ST_1_STEERING_00218.jpg`                | schematic        | STEERING         | 77    |
| `page-10.json`  | `GMT00ST_5_RESTRAINTS_00072.jpg`              | schematic_text   | RESTRAINTS       | 90    |

Selection notes: covers all 3 page categories across 6 chapters; includes a
dense connector pinout page (page-08, 174 boxes) and schematic_text pages with
rotated bottom-to-top text (e.g. page-05, the largest at 231 boxes).

## Pipeline fingerprints at generation time (md5)

- `scripts/pipeline.py` — `59ca352fd6ebac02ace52859696a8685`
- `scripts/pipeline_parallel.py` — `16f049dac933f1ed4edeff86265e4aad`
- `profiles/service-manual/pipeline.yaml` — `61ac98fe905b204ab180085ab9af0cf0`
- `profiles/service-manual/wordlist.txt` — `01554fddc5f3b5a148039280e781013e`
- `tests/normalize.py` — `6bcf33f0ceffce53c502a40e6353bae5`
- `tests/regression_sample.csv` — `b56481c68a15438dceb47797644a067e`

## Regenerating goldens

Only regenerate when a pipeline change is *intended* to alter OCR output
(new model, config retune, bug fix). Re-run the generation command above,
rebuild `golden/page-NN.json` via `tests/normalize.py`, update this manifest
(date, fingerprints), and record *why* the goldens moved in the CHANGELOG.
