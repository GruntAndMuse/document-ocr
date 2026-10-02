# REQUIREMENTS

## Operating systems

| OS | Status |
|---|---|
| Linux | Tested (primary development platform) |
| Windows 10/11 | Code is platform-agnostic (pathlib, no shell calls) but **untested** — please report issues |
| macOS | Same as Windows — should work, not yet verified |

## Software

- **Python 3.10+** (3.12 tested)
- **pip** (no conda, no Docker, no system packages required)
- Dependencies from `scripts/requirements.txt` (all pinned):

| Package | Version | Why |
|---|---|---|
| numpy | 2.5.3 | Array math |
| onnxruntime | 1.30.0 | OCR model inference |
| opencv-python-headless | 5.0.0.93 | Image processing (deskew, CLAHE) |
| pillow | 12.3.0 | Image I/O |
| pymupdf | 1.28.2 | PDF generation |
| PyYAML | 6.0.3 | Config files |
| rapidocr-onnxruntime | 1.4.4 | OCR engine (downloads model on first run) |

Install: `pip install -r scripts/requirements.txt`

The OCR model weights (~100MB) download automatically on first run from
the RapidOCR project. After that, everything works offline.

## Hardware

- **RAM:** ~500MB per page during processing. The OCR model stays loaded.
- **CPU:** Any modern multi-core CPU. ~10-30 seconds per page.
  No GPU required or used.
- **Disk:** ~2GB for venv + model weights, plus space for your scans
  and output PDFs.
- **Rule of thumb:** a 300-page manual takes roughly 1-3 hours of OCR time
  on a typical laptop. The pipeline resumes if interrupted.

## What it can do

- Deskew (straighten) rotated scans
- Enhance contrast (CLAHE) for faded prints
- OCR with bounding boxes in original page coordinates
- Handle rotated content (landscape diagrams in portrait pages)
- Extract page numbers from headers
- Apply domain wordlists (fix known OCR corruptions)
- Build searchable PDFs with invisible text layer
- QC visualization (select-all simulation)

## What it can't do (yet)

- **Handwriting** — printed text only. Handwritten notes will produce garbage.
- **Very low resolution** — below ~150 DPI, accuracy drops sharply. 300 DPI recommended.
- **Complex multi-column layouts** — reading order may be wrong on
  magazine-style layouts. Single-column documents work best.
- **Non-Latin scripts** — the default OCR model is Latin-script. Other
  models exist but aren't integrated yet. See [ROADMAP.md](ROADMAP.md).

## Security

This tool is designed with privacy as architecture, not a feature:

- **No network calls.** The codebase makes zero HTTP requests (verified by audit).
  The only download is the OCR model on first run, from the RapidOCR project.
- **No telemetry.** No usage tracking, no analytics, no crash reporting.
- **No cloud.** Everything runs on your machine. Your documents never leave it.
- **No credentials.** Nothing to configure, no API keys, no accounts.

Verify it yourself: disconnect from the internet after setup and run the
pipeline. It works. See [SECURITY.md](SECURITY.md).
