#!/usr/bin/env python3
"""QC gates: the GMT800 production audit as build-failing gates.

Five gates, each returning pass/fail + evidence. A gate failure FAILS the
build — there is no warn-only mode. A gate that only warns is a suggestion,
and this pipeline's standard is "best in the world" (Dennis, 2026-10-05).

The gates mirror the audit that caught the D1 text-layer misplacement on the
GMT800 production run (see ~/workspace/gmt800-ocr-test/bbox-fix-log.md):

  1. bbox_alignment  Text-layer centering on sampled pages. Invisible text
                     must be CENTERED on each OCR box (the D1 fix), not hung
                     from its bottom edge. Measures vertical center offset
                     between each OCR box and its placed text span.
  2. file_integrity  The PDF opens, page count matches the manifest (or the
                     JSON set), file is non-empty, last page is readable.
                     Catches corruption/truncation.
  3. dewarp_parity   Dewarped<->original PDFs: same page count, same order
                     (embedded-image dimensions vs per-page JSON width/height
                     on sampled pages). Skipped when no originals PDF is given.
  4. text_encoding   Sampled pages: text extracts readably — no U+FFFD, no
                     private-use CID garbage, no excess control chars, no CJK
                     mojibake, and no systemically-missing text layers.
  5. dup_missing     No duplicate embedded page images (md5); no gaps in the
                     book page-number sequence; PDF page count matches input.

Usage:
    qc_gates.py --pdf final.pdf --json-dir output/
    qc_gates.py --pdf dewarped.pdf --originals-pdf orig.pdf \\
                --jsons output/a.json output/b.json --manifest manifest.json
    doc-ocr qc --pdf final.pdf --json-dir output/

Exit code 0 = all gates pass. Exit code 1 = any gate fails.
"""
import argparse
import hashlib
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE))
from gruntandmuse_shared import friendly_errors  # noqa: E402

import fitz  # noqa: E402  (pymupdf)

# --------------------------------------------------------------------------
# Fail thresholds. Strict by design — Dennis: "don't want known flaws
# hitting the wild." The D1 bug this guards against shifted highlights
# +22px on a ~77px box; the fix brought it to -1px. Anything near the
# old failure mode must fail loudly.
# --------------------------------------------------------------------------
# Gate 1: mean |vertical center offset| over exclusively-matched boxes.
G1_MEAN_OFFSET_PX = 4.0
# Gate 1: a single box this far off its ink is individually bad.
G1_BAD_BOX_PX = 10.0
# Gate 1: ...and this fraction of bad boxes fails the gate.
G1_BAD_BOX_FRAC = 0.02
# Gate 1: span must overlap the OCR box this much to count as its match.
G1_MIN_OVERLAP = 0.5
# Gate 1: spans much bigger than the box are merged lines — measured
# separately, not counted as centering evidence either way.
G1_MERGE_AREA_RATIO = 2.0

# Gate 4: a page whose JSON has text boxes but extracts almost nothing has
# a broken/empty text layer (ToUnicode failure, blank layer, etc).
G4_MIN_CHARS = 20
# Gate 4: control chars (beyond \n and \t) above this fraction = garbage.
G4_MAX_CONTROL_FRAC = 0.01

DEFAULT_SAMPLE = 12


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def box_rect(box):
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return (min(xs), min(ys), max(xs), max(ys))


def rect_area(r):
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def rect_inter(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)


def overlap_coef(a, b):
    """intersection / min(area) — 1.0 when the smaller is fully inside."""
    m = min(rect_area(a), rect_area(b))
    return rect_inter(a, b) / m if m > 0 else 0.0


def page_spans(page):
    """All non-blank text spans on a page: (bbox_tuple, text)."""
    out = []
    for blk in page.get_text("dict")["blocks"]:
        if blk["type"] != 0:
            continue
        for ln in blk["lines"]:
            for sp in ln["spans"]:
                if sp["text"].strip():
                    out.append((tuple(sp["bbox"]), sp["text"]))
    return out


def load_page_jsons(json_paths):
    pages = []
    for jp in json_paths:
        with open(jp, encoding="utf-8") as f:
            pages.append(json.load(f))
    return pages


def json_boxes(pj):
    """All text boxes (body + header) with non-blank text."""
    out = []
    for key in ("boxes", "header_boxes"):
        for b in pj.get(key, []) or []:
            if b.get("text", "").strip() and b.get("box"):
                out.append(b)
    return out


def sample_indices(n_pages, n_sample):
    """Deterministic evenly-spaced page indices (0-based)."""
    if n_pages <= n_sample:
        return list(range(n_pages))
    step = n_pages / n_sample
    return sorted({min(n_pages - 1, int(i * step)) for i in range(n_sample)})


def result(name, passed, evidence, detail):
    return {"gate": name, "passed": bool(passed),
            "evidence": evidence, "detail": detail}


# --------------------------------------------------------------------------
# Gate 1 — bbox alignment (the D1 fix, as a gate)
# --------------------------------------------------------------------------
def gate_bbox_alignment(doc, page_jsons, sample_idx):
    """Vertical center offset between each OCR box and its placed span.

    The D1 defect hung invisible text from the box BOTTOM edge, so search
    highlights sat below the ink (up to +22px on short schematic labels).
    The fix centers cap-height on the box center. This gate re-measures
    that offset on sampled pages: mean |offset| must stay small.

    Scope: PDFs built by this pipeline's builders, which place one
    invisible span per OCR box (place_box_text). Line-merged text layers
    (e.g. the GMT800 volume builders) don't preserve per-box geometry —
    box-level centering is not measurable on those, and they are out of
    scope here. Validated: the gate FAILS the real pre-D1 production PDF
    (16.9px mean on Dennis's fuel-pump page) and PASSES pipeline output.
    """
    offsets = []       # (page_no, text, offset_px)
    missing = []       # boxes with no overlapping span at all
    merged = 0         # boxes whose span is a merged line (not measured)
    n_boxes = 0
    for pi in sample_idx:
        pj = page_jsons[pi]
        boxes = json_boxes(pj)
        n_boxes += len(boxes)
        if not boxes:
            continue
        spans = page_spans(doc[pi])
        for b in boxes:
            r = box_rect(b["box"])
            if rect_area(r) <= 0:
                continue
            best, best_c = None, 0.0
            for s_bbox, _ in spans:
                c = overlap_coef(r, s_bbox)
                if c > best_c:
                    best, best_c = s_bbox, c
            if best is None or best_c < 0.05:
                missing.append({"page": pi + 1,
                                "text": b["text"][:40]})
                continue
            if best_c < G1_MIN_OVERLAP:
                continue  # weak match — neither evidence nor failure
            if rect_area(best) > G1_MERGE_AREA_RATIO * rect_area(r):
                merged += 1
                continue  # merged line span — centering not measurable here
            box_cy = (r[1] + r[3]) / 2.0
            span_cy = (best[1] + best[3]) / 2.0
            offsets.append((pi + 1, b["text"][:40], span_cy - box_cy))

    ev = {"pages_sampled": len(sample_idx),
          "boxes_seen": n_boxes,
          "boxes_measured": len(offsets),
          "boxes_merged_skipped": merged,
          "boxes_no_span": len(missing)}
    if missing:
        ev["missing_examples"] = missing[:8]
    if not offsets:
        # Nothing measurable: with boxes present but no exclusive span
        # matches, centering is unverifiable — fail closed, not open.
        if n_boxes:
            return result("bbox_alignment", False, ev,
                          f"no exclusively-matched spans on {len(sample_idx)} "
                          f"sampled pages ({n_boxes} boxes) — centering "
                          f"unverifiable")
        return result("bbox_alignment", True, ev,
                      "no text boxes on sampled pages — nothing to measure")

    abs_off = [abs(o) for _, _, o in offsets]
    mean_off = sum(abs_off) / len(abs_off)
    bad = [(p, t, o) for p, t, o in offsets if abs(o) > G1_BAD_BOX_PX]
    bad_frac = len(bad) / len(offsets)
    ev.update({"mean_abs_offset_px": round(mean_off, 2),
               "max_abs_offset_px": round(max(abs_off), 2),
               "bad_boxes": len(bad),
               "bad_box_frac": round(bad_frac, 4)})
    if bad:
        ev["bad_examples"] = [
            {"page": p, "text": t, "offset_px": round(o, 1)}
            for p, t, o in bad[:8]]

    if mean_off > G1_MEAN_OFFSET_PX:
        return result("bbox_alignment", False, ev,
                      f"mean |offset| {mean_off:.1f}px > {G1_MEAN_OFFSET_PX}px "
                      f"— text layer not centered on ink (D1 regression)")
    if bad_frac > G1_BAD_BOX_FRAC:
        return result("bbox_alignment", False, ev,
                      f"{len(bad)}/{len(offsets)} boxes off by "
                      f">{G1_BAD_BOX_PX}px — text layer misaligned")
    return result("bbox_alignment", True, ev,
                  f"mean |offset| {mean_off:.1f}px over {len(offsets)} boxes")


# --------------------------------------------------------------------------
# Gate 2 — file integrity
# --------------------------------------------------------------------------
def gate_file_integrity(pdf_path, expected_pages):
    ev = {"pdf": os.path.basename(pdf_path)}
    if not os.path.exists(pdf_path):
        return result("file_integrity", False, ev, "PDF not found")
    size = os.path.getsize(pdf_path)
    ev["size_bytes"] = size
    if size == 0:
        return result("file_integrity", False, ev, "PDF is zero bytes")
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return result("file_integrity", False, ev,
                      f"PDF does not open: {e}")
    ev["page_count"] = len(doc)
    ev["expected_pages"] = expected_pages
    n_pages = len(doc)
    if expected_pages is not None and n_pages != expected_pages:
        doc.close()
        return result("file_integrity", False, ev,
                      f"page count {n_pages} != expected {expected_pages} "
                      f"(truncation or manifest mismatch)")
    try:
        doc[-1].get_text()
    except Exception as e:
        doc.close()
        return result("file_integrity", False, ev,
                      f"last page unreadable (truncated file?): {e}")
    doc.close()
    return result("file_integrity", True, ev,
                  f"{ev['page_count']} pages, opens cleanly")


# --------------------------------------------------------------------------
# Gate 3 — dewarped <-> original parity
# --------------------------------------------------------------------------
def gate_dewarp_parity(doc, originals_pdf_path, page_jsons, sample_idx):
    ev = {}
    if not originals_pdf_path:
        ev["skipped"] = "no --originals-pdf given"
        return result("dewarp_parity", True, ev,
                      "skipped: no originals PDF provided")
    if not os.path.exists(originals_pdf_path):
        return result("dewarp_parity", False, ev,
                      f"originals PDF not found: {originals_pdf_path}")
    try:
        orig = fitz.open(originals_pdf_path)
    except Exception as e:
        return result("dewarp_parity", False, ev,
                      f"originals PDF does not open: {e}")
    ev["pages"] = len(doc)
    ev["originals_pages"] = len(orig)
    n_orig = len(orig)
    if n_orig != len(doc):
        orig.close()
        return result("dewarp_parity", False, ev,
                      f"page count {len(doc)} != originals {n_orig}")
    # order check: embedded image dimensions must match the per-page JSON
    # width/height on sampled pages (dewarp remaps in place — dims unchanged)
    mismatches = []
    for pi in sample_idx:
        pj = page_jsons[pi]
        jw, jh = pj.get("width"), pj.get("height")
        if not jw or not jh:
            continue
        for pg in (doc[pi], orig[pi]):
            for img in pg.get_images(full=True):
                info = doc.extract_image(img[0])
                if (info["width"], info["height"]) != (jw, jh):
                    mismatches.append(
                        {"page": pi + 1, "json_dims": [jw, jh],
                         "image_dims": [info["width"], info["height"]]})
                    break
    orig.close()
    ev["dim_mismatches"] = len(mismatches)
    if mismatches:
        ev["examples"] = mismatches[:8]
        return result("dewarp_parity", False, ev,
                      "page order/content mismatch vs originals")
    return result("dewarp_parity", True, ev,
                  f"{len(doc)} pages, order verified on "
                  f"{len(sample_idx)} sampled pages")


# --------------------------------------------------------------------------
# Gate 4 — text encoding sanity
# --------------------------------------------------------------------------
_REPLACEMENT = "\ufffd"
_PRIVATE_USE = re.compile("[\ue000-\uf8ff\U000F0000-\U0010FFFF]")
_CJK = re.compile("[\u4e00-\u9fff]")
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def check_page_text(text, n_box_text, src_text):
    """Encoding problems on one page's extracted text. Returns a list of
    problem descriptions (empty = clean). Factored out so tests can feed
    crafted strings directly — some broken encodings don't survive a
    font round-trip, but real-world PDFs carry them in the raw bytes."""
    problems = []
    stripped = text.strip()
    if n_box_text and len(stripped) < G4_MIN_CHARS:
        problems.append(
            f"systemically missing text: JSON has {n_box_text} text boxes "
            f"but page extracts {len(stripped)} chars")
        return problems
    if _REPLACEMENT in text:
        problems.append("U+FFFD replacement chars — broken ToUnicode/encoding")
    if _PRIVATE_USE.search(text):
        problems.append("private-use chars (U+E000-U+F8FF) — CID garbage")
    ctrl = len(_CONTROL.findall(text))
    if text and ctrl / len(text) > G4_MAX_CONTROL_FRAC:
        problems.append(f"excess control chars ({ctrl}/{len(text)})")
    if _CJK.search(text) and not _CJK.search(src_text):
        problems.append("CJK chars in extraction with none in OCR source "
                        "— mojibake")
    return problems


def gate_text_encoding(doc, page_jsons, sample_idx):
    problems = []
    chars_total = 0
    for pi in sample_idx:
        pj = page_jsons[pi]
        text = doc[pi].get_text()
        chars_total += len(text)
        n_box_text = sum(1 for b in json_boxes(pj))
        src = " ".join(b["text"] for b in json_boxes(pj))
        for issue in check_page_text(text, n_box_text, src):
            problems.append({"page": pi + 1, "issue": issue})
    ev = {"pages_sampled": len(sample_idx),
          "chars_extracted": chars_total,
          "problems": len(problems)}
    if problems:
        ev["examples"] = problems[:8]
        return result("text_encoding", False, ev,
                      f"{len(problems)} encoding problem(s) on sampled pages")
    return result("text_encoding", True, ev,
                  f"{chars_total} chars extracted cleanly on "
                  f"{len(sample_idx)} sampled pages")


# --------------------------------------------------------------------------
# Gate 5 — duplicate / missing pages
# --------------------------------------------------------------------------
def _page_image_md5s(doc):
    """md5 of every embedded image per page: {page_no: [md5, ...]}."""
    out = {}
    for pi in range(len(doc)):
        md5s = []
        for img in doc[pi].get_images(full=True):
            try:
                info = doc.extract_image(img[0])
                md5s.append(hashlib.md5(info["image"]).hexdigest())
            except Exception:
                continue
        out[pi + 1] = md5s
    return out


def _page_number_gaps(page_jsons):
    """Gaps in the book page-number sequence. Handles plain ints and
    chapter-page forms like '6-659' (grouped per chapter). Returns a list
    of gap descriptions; unparseable numbers are reported, not failed."""
    raw = [pj.get("page_number") for pj in page_jsons]
    raw = [str(p).strip() for p in raw if p]
    gaps, unparseable = [], []
    # plain integers?
    try:
        nums = sorted({int(p) for p in raw})
        if nums:
            for a, b in zip(nums, nums[1:]):
                if b - a > 1:
                    gaps.append(f"missing {a + 1}..{b - 1}")
            return gaps, unparseable
    except ValueError:
        pass
    # chapter-page form?
    groups = {}
    for p in raw:
        m = re.fullmatch(r"(\d+)[\-–](\d+)", p)
        if not m:
            unparseable.append(p)
            continue
        groups.setdefault(m.group(1), set()).add(int(m.group(2)))
    for ch, nums in sorted(groups.items()):
        nums = sorted(nums)
        for a, b in zip(nums, nums[1:]):
            if b - a > 1:
                gaps.append(f"chapter {ch}: missing {a + 1}..{b - 1}")
    return gaps, unparseable


def gate_dup_missing(doc, page_jsons, manifest_pages):
    ev = {}
    # duplicates: identical embedded page images
    seen = {}
    dups = []
    for pg_no, md5s in _page_image_md5s(doc).items():
        for md5 in md5s:
            if md5 in seen:
                dups.append({"md5": md5[:12],
                             "pages": sorted({seen[md5], pg_no})})
            else:
                seen[md5] = pg_no
    ev["duplicate_pairs"] = len(dups)
    if dups:
        ev["examples"] = dups[:8]
    # missing: PDF pages vs inputs
    expected = (len(manifest_pages) if manifest_pages is not None
                else len(page_jsons))
    ev["pdf_pages"] = len(doc)
    ev["expected_pages"] = expected
    count_ok = len(doc) == expected
    # gaps in the page-number sequence. The manifest defines the expected
    # set when given (production: the full document); otherwise the input
    # JSONs are the complete set. A *sample* corpus must be given a manifest
    # with corpus sequence numbers — book-page gaps in a sample are not
    # missing pages.
    if manifest_pages is not None:
        seq_jsons = [{"page_number": p.get("page_number")}
                     for p in manifest_pages]
    else:
        seq_jsons = page_jsons
    gaps, unparseable = _page_number_gaps(seq_jsons)
    ev["page_number_gaps"] = gaps
    if unparseable:
        ev["unparseable_page_numbers"] = unparseable[:8]

    if dups:
        return result("dup_missing", False, ev,
                      f"{len(dups)} duplicate page image(s)")
    if not count_ok:
        return result("dup_missing", False, ev,
                      f"PDF has {len(doc)} pages, expected {expected}")
    if gaps:
        return result("dup_missing", False, ev,
                      f"page-number gaps: {'; '.join(gaps[:4])}")
    return result("dup_missing", True, ev,
                  f"{len(doc)} pages, no duplicates, no sequence gaps")


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def collect_jsons(args):
    if args.jsons:
        paths = args.jsons
    elif args.json_dir:
        if not os.path.isdir(args.json_dir):
            raise ValueError(f"JSON dir not found: {args.json_dir}")
        paths = sorted(
            os.path.join(args.json_dir, f)
            for f in os.listdir(args.json_dir)
            if f.endswith(".json"))
        # skip report/progress files — same rule as `doc-ocr build`
        kept = []
        for p in paths:
            try:
                with open(p, encoding="utf-8") as fh:
                    d = json.load(fh)
                if isinstance(d, dict) and "file" in d:
                    kept.append(p)
            except Exception:
                pass
        paths = kept
    else:
        raise ValueError("need --json-dir or --jsons (per-page OCR JSONs)")
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise ValueError(f"{len(missing)} JSON(s) not found "
                         f"(first: {missing[0]})")
    if not paths:
        raise ValueError("no per-page OCR JSONs found")
    return paths


def load_manifest(path):
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    pages = d.get("pages", [])
    if not isinstance(pages, list) or not pages:
        raise ValueError(f"manifest has no pages list: {path}")
    return pages


def run_gates(pdf_path, json_paths, manifest_path=None,
              originals_pdf_path=None, n_sample=DEFAULT_SAMPLE):
    page_jsons = load_page_jsons(json_paths)
    manifest_pages = load_manifest(manifest_path)
    expected = (len(manifest_pages) if manifest_pages is not None
                else len(page_jsons))

    results = []
    # gate 2 first: nothing else is meaningful on a broken file
    r2 = gate_file_integrity(pdf_path, expected)
    results.append(r2)
    if not r2["passed"]:
        for name in ("bbox_alignment", "dewarp_parity",
                     "text_encoding", "dup_missing"):
            results.append(result(
                name, False, {"skipped": "file_integrity failed"},
                "skipped: PDF failed the integrity gate"))
        return results

    doc = fitz.open(pdf_path)
    try:
        sample_idx = sample_indices(len(doc), n_sample)
        results.append(gate_bbox_alignment(doc, page_jsons, sample_idx))
        results.append(gate_dewarp_parity(doc, originals_pdf_path,
                                          page_jsons, sample_idx))
        results.append(gate_text_encoding(doc, page_jsons, sample_idx))
        results.append(gate_dup_missing(doc, page_jsons, manifest_pages))
    finally:
        doc.close()
    return results


@friendly_errors
def main():
    ap = argparse.ArgumentParser(
        description="QC gates: build-failing quality checks for searchable "
                    "PDFs (the GMT800 production audit as code).")
    ap.add_argument("--pdf", required=True, help="searchable PDF under test")
    ap.add_argument("--json-dir", help="dir of per-page OCR JSONs")
    ap.add_argument("--jsons", nargs="*",
                    help="per-page OCR JSONs in PDF page order "
                         "(alternative to --json-dir)")
    ap.add_argument("--manifest",
                    help="JSON manifest {\"pages\": [{file, page_number}]}")
    ap.add_argument("--originals-pdf",
                    help="original-scan PDF for the dewarp-parity gate")
    ap.add_argument("--sample", type=int, default=DEFAULT_SAMPLE,
                    help="pages sampled for bbox/encoding gates "
                         f"(default {DEFAULT_SAMPLE})")
    ap.add_argument("--report", help="write JSON report to this path")
    args = ap.parse_args()

    if not os.path.exists(args.pdf):
        raise ValueError(f"PDF not found: {args.pdf}")
    json_paths = collect_jsons(args)

    results = run_gates(args.pdf, json_paths, args.manifest,
                        args.originals_pdf, args.sample)

    failed = [r for r in results if not r["passed"]]
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"[{mark}] {r['gate']}: {r['detail']}")
    print(f"\n{len(results) - len(failed)}/{len(results)} gates passed")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"pdf": args.pdf, "gates": results,
                       "passed": not failed}, f, indent=1)
        print(f"report: {args.report}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
