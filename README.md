# doc-ocr

Turn scanned document pages into **searchable PDFs**: the original scan as
the visible image, OCR text placed invisibly underneath so you can search,
highlight, and select exactly where the words are.

## The problem

You have a stack of scanned pages — a service manual, a textbook, archival
documents. They're images. You can't search them, can't copy text, can't
jump to a page number. This pipeline fixes that.

## How it works

```
page scans (JPG/PNG)
    → doc-ocr ocr        # deskew, enhance, OCR → per-page JSON
    → doc-ocr build      # JSON → searchable PDF (invisible text layer)
    → doc-ocr check      # QC: verify text aligns with the scan
    → doc-ocr qc         # QC gates: the production audit as build-failing checks
```

Every step is config-driven. Page types (text, tables, rotated diagrams)
get different processing routes from `config/pipeline.yaml` — never from
code. Swap the config to adapt it to your documents.

## Quick start

See [QUICKSTART.md](QUICKSTART.md) for the beginner-friendly walkthrough.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r scripts/requirements.txt

# OCR your pages (CSV columns: filename,category,chapter)
./doc-ocr ocr --pages ./scans --sample pages.csv --out output/

# Build the searchable PDF
./doc-ocr build --pages ./scans -o manual.pdf output/*.json

# QC one page: blue must hug the black text
./doc-ocr check manual.pdf 1 ./scans/page1.jpg qc.png
```

## Profiles

Different document types need different tuning. Profiles live in `profiles/`:

- **default** — generic documents (text, tables, diagrams)
- **service-manual** — vehicle service manuals (rotated schematics,
  pinout tables, wire-color wordlist). Validated: 100/100 pilot pages.

```bash
./doc-ocr ocr --profile service-manual --pages ./scans --sample pages.csv
```

Make your own: `cp -r profiles/service-manual profiles/my-docs`, then edit
the YAML and wordlist. See [profiles/service-manual/README.md](profiles/service-manual/README.md).

## Documentation

| Doc | What |
|---|---|
| [QUICKSTART.md](QUICKSTART.md) | Zero-experience walkthrough with screenshots |
| [REQUIREMENTS.md](REQUIREMENTS.md) | OS, dependencies, hardware, what it can/can't do |
| [ABOUT.md](ABOUT.md) | Why this exists |
| [ROADMAP.md](ROADMAP.md) | Where it's going |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to help |
| [CHANGELOG.md](CHANGELOG.md) | What changed and why |
| [SECURITY.md](SECURITY.md) | Privacy commitment |

## Privacy

Everything runs on your machine. No network calls, no telemetry, no cloud.
Your documents never leave your computer. See [SECURITY.md](SECURITY.md).

## Important: copyright

This pipeline is FOSS (MIT). The documents you process with it may not be —
don't redistribute scanned copyrighted material. Use it on documents you own
or have the right to process.

## License

MIT — see [LICENSE](LICENSE).
