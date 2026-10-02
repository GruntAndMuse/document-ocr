# Changelog

All notable changes to doc-ocr. Format: [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Unified `doc-ocr` command with subcommands (ocr, build, check, prescreen, sample)
- `--profile` flag for domain-specific config (default, service-manual)
- Generic default config and wordlist (service manual tuning moved to profile)
- Friendly error messages — no tracebacks for user errors
- `doc-ocr build` now skips report/progress JSONs instead of crashing
- QUICKSTART.md, REQUIREMENTS.md, ABOUT.md, ROADMAP.md, CONTRIBUTING.md
- SECURITY.md with privacy commitment and self-verification instructions
- Windows batch wrapper (`doc-ocr.bat`)

## [0.1.0] - 2026-10-02

### Added
- Initial public release
- Config-driven OCR pipeline (deskew, CLAHE, RapidOCR, wordlist)
- Category routes: schematic, schematic_text, connector_pinout, troubleshooting, text, diagram, blank, damaged
- Searchable PDF builder with invisible text layer
- Dewarp option for page-curl readability
- QC tools: select-all simulation (`check`), placement pre-screen
- Stratified pilot sampler
- Service manual profile (validated: 100/100 pilot pages, zero errors)
