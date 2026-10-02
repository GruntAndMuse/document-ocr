# Roadmap

Where doc-ocr is going. Living document — changes as we learn.

## Now: Core pipeline (done)

Scan → OCR → searchable PDF, with config-driven page-type routes,
domain wordlists, and QC tooling. Validated on 100-page pilot (100/100).

## Next

### Generic profiles
More pre-tuned profiles beyond service-manual:
- **textbook** — chapters, figures, index-style page numbers
- **magazine** — multi-column layout handling
- **archival** — faded print, varied quality, date-stamp extraction
- Community contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md)

### Better tables
Connector pinouts and troubleshooting trees work, but complex merged-cell
tables are still rough. Cell-boundary detection is the next accuracy push.

### Alias system
Search for "ground" and find "GND". Search for "brake light" and find
"stop lamp". A normalization layer over the raw OCR text, with exact
source text always ranked above aliases. (Planned for the S10 rewire.)

### More languages
The OCR engine supports non-Latin models. Integrating them as a config
option (not a code change) is on the list.

## Later

### Search index
Beyond per-PDF search: a SQLite index across a whole manual set, with
page-number cross-references. The S10 rewire already prototypes this.

### The library vision
A community pattern for building personal searchable libraries from
documents you own — same pipeline, shared profiles, your content stays
yours.

### Android app
Snap a document photo → OCR on-device → searchable PDF. No Termux, one-tap UX. Uses the same pipeline, wrapped via Capacitor.

### Accessibility
GUI/file picker with progress bars and plain-English output. Large touch targets, high contrast, screen-reader labels, keyboard navigation. Community translations via gettext (Spanish first). Spoken-language output options (local TTS default, cloud opt-in).

## What we won't do

- Cloud features. Your documents stay on your machine. Ever.
- Telemetry. We don't want your data.
- Paywalled features. MIT means MIT.
- Rushed releases. Slow is smooth, smooth is fast.

---

*Last updated: 2026-10-02*
