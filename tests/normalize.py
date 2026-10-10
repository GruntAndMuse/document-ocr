#!/usr/bin/env python3
"""Shared normalization for the doc-ocr regression gate.

The pipeline's per-page JSON contains run-to-run volatile fields
(`timings`, `elapsed_s`). Everything else (box text, box geometry,
confidence scores, header/body text, counts) is deterministic and is
what the golden files pin down.
"""
import json

# Keys that legitimately change on every run and carry no OCR signal.
VOLATILE_KEYS = ("timings", "elapsed_s")


def normalize_page_json(raw):
    """Strip volatile keys; return a plain dict ready for canonical dump."""
    data = dict(raw)
    for key in VOLATILE_KEYS:
        data.pop(key, None)
    return data


def canonical_dump(data):
    """Deterministic serialization: sorted keys, fixed indent, LF, trailing NL."""
    return json.dumps(data, indent=2, sort_keys=True,
                      ensure_ascii=False) + "\n"


def load_golden(path):
    with open(path, encoding="utf-8") as f:
        return canonical_dump(normalize_page_json(json.load(f)))


def load_produced(path):
    with open(path, encoding="utf-8") as f:
        return canonical_dump(normalize_page_json(json.load(f)))
