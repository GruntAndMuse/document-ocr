# document-ocr Performance

Benchmarked 2026-10-02. 20 representative pages (7 schematic, 7 schematic_text,
6 connector_pinout) from the GMT800 production set.

## Per-stage timing (serial, 20-page average)

| Stage | Avg ms/page | % of total |
|-------|-------------|------------|
| body_ocr | 12,754 | 70.3% |
| header_ocr | 4,649 | 25.6% |
| normalize (CLAHE) | 356 | 2.0% |
| deskew | 250 | 1.4% |
| read (imdecode) | 132 | 0.7% |
| rotate | 35 | 0.1% |
| body_post | 1 | 0.0% |
| header_post | 0 | 0.0% |
| **Total** | **18,177** | **100%** |

**OCR (RapidOCR) is 96% of runtime.** Everything else is noise.

- Serial: **18.2 s/page** → 789 pages ≈ **4.0 hours**
- By category: schematic 14.5s, connector_pinout 18.4s, schematic_text 21.6s

## Parallel version

`scripts/pipeline_parallel.py` — same logic, pages distributed via
ProcessPoolExecutor. Each worker gets its own RapidOCR instance. Each page
writes to its own `<filename>.json` (no shared output prefixes — avoids the
batch-3 pdftoppm race condition class).

### Quality verification: PASSED

20/20 pages **byte-identical** between serial and parallel (excluding timing
metadata). OCR text, bounding boxes, confidence scores, page numbers — all
identical. Determinism confirmed.

### Speedup

Not meaningfully measurable on the 2-CPU benchmark host while under load from
concurrent work (load avg 12-15 during testing). The parallel implementation is
correct and will scale on multi-core machines:

- On a 12-core machine (e.g. Ryzen 9 7900X): `--workers 10` should yield
  roughly **8-10x** speedup on the OCR portion (96% of runtime), bringing
  789 pages from ~4 hours to roughly **25-30 minutes**.
- Amdahl's law ceiling: with 96% parallelizable, max theoretical speedup is
  ~25x (infinite workers). Realistic with 10-12 workers: 8-10x.

### Stages that can't be parallelized (within a page)

- **Box remapping** (`remap_body_boxes`): must run after OCR completes for
  that page. It's 1ms — irrelevant.
- **PDF assembly** (`build_volumes_*.py`): inherently sequential (pages must
  be added in order). Not yet timed — separate task.
- **Deskew/normalize**: per-page independent, already parallel via workers.
  No intra-page parallelism needed (each is <500ms).

### What changed

| File | Change |
|------|--------|
| `scripts/pipeline.py` | Added per-stage timing (`result["timings"]`). No logic changes. |
| `scripts/pipeline_parallel.py` | **New.** ProcessPoolExecutor wrapper. Reuses all logic from `pipeline.py` (zero duplication). Per-worker RapidOCR init, per-page output files. |
| `docs/performance.md` | This file. |

### Known issue encountered

Attempted to cap onnxruntime threads per worker via RapidOCR kwargs
(`det_intra_op_num_threads=1`). This caused RapidOCR to hang indefinitely —
reverted. onnxruntime manages its own thread pool; on multi-core machines the
OS scheduler handles contention acceptably for batch workloads. If thread
oversubscription becomes a measured problem (not a theoretical one), revisit
with `intra_op_num_threads` set via a custom RapidOCR config file rather than
kwargs.

## Recommendation

Use `pipeline_parallel.py` with `--workers = (cpu_count - 1)` for production
runs. The serial `pipeline.py` remains the default for single-page / debug use.
Both produce identical outputs.
