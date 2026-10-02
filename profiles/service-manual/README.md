# Service Manual Profile

Example domain profile for vehicle service manuals. This is the profile
the pipeline was originally built and validated against (100/100 pages,
zero errors on the pilot sample).

## What's in this profile

- **pipeline.yaml** — routes tuned for service manual page types:
  - `schematic` — rotated wiring diagrams (body text runs bottom-to-top)
  - `schematic_text` — normal-orientation schematic content
  - `connector_pinout` — connector pinout tables
  - `troubleshooting` — diagnostic trouble trees
  - `text`, `diagram`, `blank`, `damaged` — standard types
- **wordlist.txt** — automotive domain corrections and canonical terms
  (wire color abbreviations, connector IDs, etc.)

## Using this profile

```bash
doc-ocr ocr --profile service-manual --sample pages.csv --pages ./scans
```

Or copy this directory as a starting point for your own domain:

```bash
cp -r profiles/service-manual profiles/my-domain
# then edit profiles/my-domain/pipeline.yaml and wordlist.txt
```

## Growing the wordlist

The `wrong>right` section grows from red-pen reviews: every time a human
corrects OCR output, add the corruption here. The `=` canonical terms are
never auto-rewritten — they're checked after OCR and flagged if corrupted.

## Note on source material

This profile was built for the author's personal service manual collection.
The pipeline is FOSS (MIT); the manuals it was tested on are copyrighted
by their publishers. Don't redistribute scanned manual content — use this
profile on manuals you own or have the right to process.
