# SECURITY

## Our commitment

**Your documents never leave your computer.**

This isn't a feature. It's architecture. Dennis did physical security in
the Army and prides himself on it — the pipeline reflects that.

## What we promise

- **No network calls.** The codebase makes zero HTTP requests. Verified by
  audit (grep the source — `grep -ri "urllib\|requests\|http" scripts/`).
  The only download is the OCR model weights on first run, fetched by the
  RapidOCR library from its own project. After that, fully offline.
- **No telemetry.** No usage tracking, no analytics, no crash reporting,
  no phone-home. We don't want your data.
- **No cloud.** Everything runs locally. There is no server component,
  no account system, no sync.
- **No credentials.** Nothing to configure. No API keys, no tokens.
- **Your scans stay yours.** Input images are read, output PDFs are written.
  Nothing is transmitted anywhere.

## Verify it yourself

Disconnect from the internet after `pip install` and run the pipeline:

```bash
# Linux: run with networking disabled
unshare -n ./doc-ocr ocr --pages my-scans --sample pages.csv
```

It works. That's the proof.

## Dependencies

All dependencies are pinned in `scripts/requirements.txt` and are
well-known open-source packages (OpenCV, NumPy, PyMuPDF, RapidOCR).
No obfuscated code, no binary blobs except the OCR model weights
(ONNX format, from the open-source RapidOCR project).

## Reporting issues

If you find anything that phones home, open an issue. That's a
release-blocking bug, not a feature request.

## Reporting a security vulnerability

If you find a security bug, don't open a public issue — use GitHub's
**private vulnerability reporting** (Security tab → "Report a vulnerability"),
or email security@gruntandmuse.com.
Include what you found, how to reproduce it, and what you think the impact is.
We'll acknowledge within 7 days and keep you posted until it's fixed.
No bug bounty (we're a two-man pro-bono shop), but you'll get credit in the
changelog unless you'd rather stay anonymous.

## Copyright note

This pipeline is MIT licensed. The documents you process with it are
your responsibility — don't redistribute copyrighted scanned material.
