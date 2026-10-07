#!/usr/bin/env python3
"""QC gates test suite: every gate gets a pass case and a fail case,
including the D1 text-layer centering regression test (the coordinator
noted CI never exercised the centering fix — this is that test).

Run:  python tests/test_qc_gates.py
Exit 0 = all pass. Exit 1 = any failure. No pytest needed — plain asserts
with PASS/FAIL lines, same style as tests/test_regression.py.

All fixtures are synthetic (built in a temp dir). Fast, offline, no OCR.
"""
import importlib.util
import json
import os
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))          # tests/
ROOT = os.path.dirname(BASE)                              # document-ocr/
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, ROOT)

import fitz  # noqa: E402
import qc_gates as Q  # noqa: E402


def _load_place_box_text():
    spec = importlib.util.spec_from_file_location(
        "mdp", os.path.join(SCRIPTS, "make_demo_pdf.py"))
    mdp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mdp)
    return mdp.place_box_text, mdp.fit_font


PLACE_FIXED, FIT_FONT = _load_place_box_text()


def place_box_text_broken(page, b):
    """The pre-D1 bug, replicated for the regression test: invisible text
    hung from the box BOTTOM edge (baseline at ry1), and the old vertical
    branch that underestimated advance length."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = b["box"]
    xs = [x0, x1, x2, x3]
    ys = [y0, y1, y2, y3]
    rx0, rx1 = min(xs), max(xs)
    ry0, ry1 = min(ys), max(ys)
    wid, hgt = rx1 - rx0, ry1 - ry0
    txt = b["text"].strip()
    if not txt:
        return
    if hgt > 2.5 * wid:
        fs = FIT_FONT(txt, hgt, wid)
        if fs <= 0:
            return
        page.insert_text((rx0, ry1), txt, fontsize=fs, fontname="helv",
                         render_mode=3, rotate=90)
    else:
        fs = FIT_FONT(txt, wid, hgt)
        if fs <= 0:
            return
        page.insert_text((rx0, ry1), txt, fontsize=fs, fontname="helv",
                         render_mode=3)


def mkbox(x0, y0, x1, y1, text):
    return {"box": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "text": text}


# short wide schematic label (the D1-sensitive shape) + a vertical label
SYNTH_BOXES = [
    mkbox(100, 200, 340, 232, "Fuel Pump Relay"),
    mkbox(400, 300, 424, 560, "RESISTOR"),
    mkbox(100, 700, 500, 736, "body text line here"),
]


def build_pdf(path, pages, placer=PLACE_FIXED):
    """pages: list of (W, H, boxes). Returns path."""
    doc = fitz.open()
    for W, H, boxes in pages:
        pg = doc.new_page(width=W, height=H)
        for b in boxes:
            placer(pg, b)
    doc.save(path)
    doc.close()
    return path


def write_json(path, boxes, page_number="1", W=800, H=1000):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"file": os.path.basename(path).replace(".json", ""),
                   "page_number": page_number, "width": W, "height": H,
                   "boxes": boxes, "header_boxes": []}, f)


def write_png(path, seed):
    import cv2
    import numpy as np
    rng = np.random.RandomState(seed)
    img = rng.randint(0, 255, (16, 16, 3), dtype=np.uint8)
    cv2.imwrite(path, img)


RESULTS = []


def check(name, fn):
    try:
        fn()
    except AssertionError as e:
        RESULTS.append((name, False, str(e)))
        print(f"FAIL {name}: {e}")
    except Exception as e:
        RESULTS.append((name, False, f"{type(e).__name__}: {e}"))
        print(f"FAIL {name}: {type(e).__name__}: {e}")
    else:
        RESULTS.append((name, True, ""))
        print(f"PASS {name}")


# --------------------------------------------------------------------------
# Gate 1 — bbox alignment (+ the D1 regression test)
# --------------------------------------------------------------------------
def t_bbox_passes_on_fixed_placement():
    d = tempfile.mkdtemp()
    pdf = build_pdf(os.path.join(d, "fixed.pdf"),
                    [(800, 1000, SYNTH_BOXES)])
    pj = [{"file": "p1", "page_number": "1", "width": 800, "height": 1000,
           "boxes": SYNTH_BOXES, "header_boxes": []}]
    doc = fitz.open(pdf)
    try:
        r = Q.gate_bbox_alignment(doc, pj, [0])
    finally:
        doc.close()
    assert r["passed"], f"fixed placement should pass: {r['detail']} {r['evidence']}"
    assert r["evidence"]["mean_abs_offset_px"] < Q.G1_MEAN_OFFSET_PX


def t_bbox_fails_on_broken_placement():
    # D1 REGRESSION TEST: the old baseline-at-bottom placement must fail.
    d = tempfile.mkdtemp()
    pdf = build_pdf(os.path.join(d, "broken.pdf"),
                    [(800, 1000, SYNTH_BOXES)], placer=place_box_text_broken)
    pj = [{"file": "p1", "page_number": "1", "width": 800, "height": 1000,
           "boxes": SYNTH_BOXES, "header_boxes": []}]
    doc = fitz.open(pdf)
    try:
        r = Q.gate_bbox_alignment(doc, pj, [0])
    finally:
        doc.close()
    assert not r["passed"], \
        f"broken (pre-D1) placement must FAIL the gate, got: {r['detail']}"


def t_bbox_missing_span_fails():
    d = tempfile.mkdtemp()
    pdf = build_pdf(os.path.join(d, "empty.pdf"), [(800, 1000, [])])
    pj = [{"file": "p1", "page_number": "1", "width": 800, "height": 1000,
           "boxes": SYNTH_BOXES, "header_boxes": []}]
    doc = fitz.open(pdf)
    try:
        r = Q.gate_bbox_alignment(doc, pj, [0])
    finally:
        doc.close()
    assert not r["passed"], "boxes with no placed spans must fail"


# --------------------------------------------------------------------------
# Gate 2 — file integrity
# --------------------------------------------------------------------------
def t_integrity_pass():
    d = tempfile.mkdtemp()
    pdf = build_pdf(os.path.join(d, "ok.pdf"), [(800, 1000, SYNTH_BOXES)])
    r = Q.gate_file_integrity(pdf, 1)
    assert r["passed"], r["detail"]


def t_integrity_corrupt_file():
    # fitz is lenient (rebuilds broken xrefs), so "corrupt" here means
    # bytes that are not a PDF at all — e.g. a truncated download that
    # got an HTML error page instead.
    import random
    d = tempfile.mkdtemp()
    bad = os.path.join(d, "bad.pdf")
    random.seed(7)
    with open(bad, "wb") as f:
        f.write(bytes(random.getrandbits(8) for _ in range(500)))
    r = Q.gate_file_integrity(bad, 1)
    assert not r["passed"], "corrupt (non-PDF) file must fail integrity"


def t_integrity_count_mismatch():
    d = tempfile.mkdtemp()
    pdf = build_pdf(os.path.join(d, "ok.pdf"), [(800, 1000, SYNTH_BOXES)])
    r = Q.gate_file_integrity(pdf, 99)
    assert not r["passed"], "page-count mismatch must fail integrity"


def t_integrity_missing_file():
    r = Q.gate_file_integrity("/nonexistent/x.pdf", 1)
    assert not r["passed"]


# --------------------------------------------------------------------------
# Gate 3 — dewarp parity
# --------------------------------------------------------------------------
def t_parity_pass():
    d = tempfile.mkdtemp()
    pdf = build_pdf(os.path.join(d, "a.pdf"), [(800, 1000, SYNTH_BOXES)])
    pj = [{"file": "p1", "page_number": "1", "width": 800, "height": 1000,
           "boxes": SYNTH_BOXES, "header_boxes": []}]
    doc = fitz.open(pdf)
    try:
        r = Q.gate_dewarp_parity(doc, pdf, pj, [0])
    finally:
        doc.close()
    assert r["passed"], r["detail"]


def t_parity_count_mismatch():
    d = tempfile.mkdtemp()
    pdf1 = build_pdf(os.path.join(d, "a.pdf"), [(800, 1000, SYNTH_BOXES)])
    pdf2 = build_pdf(os.path.join(d, "b.pdf"),
                     [(800, 1000, SYNTH_BOXES), (800, 1000, SYNTH_BOXES)])
    pj = [{"file": "p1", "page_number": "1", "width": 800, "height": 1000,
           "boxes": SYNTH_BOXES, "header_boxes": []}]
    doc = fitz.open(pdf1)
    try:
        r = Q.gate_dewarp_parity(doc, pdf2, pj, [0])
    finally:
        doc.close()
    assert not r["passed"], "page-count mismatch must fail parity"


def t_parity_skipped_without_originals():
    d = tempfile.mkdtemp()
    pdf = build_pdf(os.path.join(d, "a.pdf"), [(800, 1000, SYNTH_BOXES)])
    pj = [{"file": "p1", "page_number": "1", "width": 800, "height": 1000,
           "boxes": SYNTH_BOXES, "header_boxes": []}]
    doc = fitz.open(pdf)
    try:
        r = Q.gate_dewarp_parity(doc, None, pj, [0])
    finally:
        doc.close()
    assert r["passed"] and "skipped" in r["detail"].lower(), \
        "parity without originals must skip, not fail"


# --------------------------------------------------------------------------
# Gate 4 — text encoding
# --------------------------------------------------------------------------
def t_encoding_clean_passes():
    assert Q.check_page_text(
        "the quick brown fox jumps over the lazy dog near the river",
        3, "the quick brown fox") == []


def t_encoding_replacement_char_fails():
    assert Q.check_page_text(
        "some text here \ufffd and more text to be long enough ok", 2,
        "some text") != []


def t_encoding_private_use_fails():
    assert Q.check_page_text(
        "some text here \ue000 and more text to be long enough ok", 2,
        "some text") != []


def t_encoding_control_chars_fail():
    assert Q.check_page_text("text\x01\x02" + "y" * 40, 1, "text") != []


def t_encoding_cjk_mojibake_fails():
    assert Q.check_page_text(
        "hello \u4e2d world, more text here to be long", 2,
        "hello world") != []
    # ...but genuine CJK source text is fine
    assert Q.check_page_text(
        "hello \u4e2d world, more text here to be long", 2,
        "hello \u4e2d world") == []


def t_encoding_missing_text_fails():
    assert Q.check_page_text("tiny", 5, "tiny") != []
    # no boxes -> no minimum: blank pages are fine
    assert Q.check_page_text("", 0, "") == []


def t_encoding_gate_end_to_end():
    d = tempfile.mkdtemp()
    pdf = build_pdf(os.path.join(d, "t.pdf"), [(800, 1000, SYNTH_BOXES)])
    pj = [{"file": "p1", "page_number": "1", "width": 800, "height": 1000,
           "boxes": SYNTH_BOXES, "header_boxes": []}]
    doc = fitz.open(pdf)
    try:
        r = Q.gate_text_encoding(doc, pj, [0])
    finally:
        doc.close()
    assert r["passed"], r["detail"]


# --------------------------------------------------------------------------
# Gate 5 — duplicates / missing
# --------------------------------------------------------------------------
def _pdf_with_images(d, png_paths):
    pdf = os.path.join(d, "img.pdf")
    doc = fitz.open()
    for p in png_paths:
        pg = doc.new_page(width=200, height=200)
        pg.insert_image(pg.rect, filename=p)
    doc.save(pdf)
    doc.close()
    return pdf


def t_dup_clean_passes():
    d = tempfile.mkdtemp()
    a, b = os.path.join(d, "a.png"), os.path.join(d, "b.png")
    write_png(a, 1)
    write_png(b, 2)
    pdf = _pdf_with_images(d, [a, b])
    doc = fitz.open(pdf)
    try:
        pj = [{"file": "p1", "page_number": "1"},
              {"file": "p2", "page_number": "2"}]
        r = Q.gate_dup_missing(doc, pj, None)
    finally:
        doc.close()
    assert r["passed"], r["detail"]


def t_dup_duplicate_image_fails():
    d = tempfile.mkdtemp()
    a = os.path.join(d, "a.png")
    write_png(a, 1)
    pdf = _pdf_with_images(d, [a, a])
    doc = fitz.open(pdf)
    try:
        pj = [{"file": "p1", "page_number": "1"},
              {"file": "p2", "page_number": "2"}]
        r = Q.gate_dup_missing(doc, pj, None)
    finally:
        doc.close()
    assert not r["passed"], "duplicate page image must fail"


def t_dup_page_gap_fails():
    d = tempfile.mkdtemp()
    a, b, c = (os.path.join(d, f"{s}.png") for s in "abc")
    for p, s in zip((a, b, c), (1, 2, 3)):
        write_png(p, s)
    pdf = _pdf_with_images(d, [a, b, c])
    doc = fitz.open(pdf)
    try:
        pj = [{"file": "p1", "page_number": "1"},
              {"file": "p2", "page_number": "2"},
              {"file": "p4", "page_number": "4"}]
        r = Q.gate_dup_missing(doc, pj, None)
    finally:
        doc.close()
    assert not r["passed"], f"page-number gap must fail: {r['detail']}"


def t_dup_count_mismatch_fails():
    d = tempfile.mkdtemp()
    a, b = os.path.join(d, "a.png"), os.path.join(d, "b.png")
    write_png(a, 1)
    write_png(b, 2)
    pdf = _pdf_with_images(d, [a, b])
    doc = fitz.open(pdf)
    try:
        pj = [{"file": "p1", "page_number": "1"}]
        r = Q.gate_dup_missing(doc, pj, None)
    finally:
        doc.close()
    assert not r["passed"], "PDF/JSON count mismatch must fail"


# --------------------------------------------------------------------------
# driver: run_gates end to end
# --------------------------------------------------------------------------
def t_run_gates_all_pass():
    d = tempfile.mkdtemp()
    pdf = build_pdf(os.path.join(d, "all.pdf"),
                    [(800, 1000, SYNTH_BOXES), (800, 1000, SYNTH_BOXES)])
    j1 = os.path.join(d, "p1.json")
    j2 = os.path.join(d, "p2.json")
    write_json(j1, SYNTH_BOXES, "1")
    write_json(j2, SYNTH_BOXES, "2")
    results = Q.run_gates(pdf, [j1, j2])
    failed = [r for r in results if not r["passed"]]
    assert len(results) == 5, f"expected 5 gates, got {len(results)}"
    assert not failed, f"gates failed: {[(r['gate'], r['detail']) for r in failed]}"


def t_run_gates_fail_fast_on_broken_pdf():
    d = tempfile.mkdtemp()
    j = os.path.join(d, "p1.json")
    write_json(j, SYNTH_BOXES, "1")
    results = Q.run_gates(os.path.join(d, "nope.pdf"), [j])
    assert results[0]["gate"] == "file_integrity"
    assert not results[0]["passed"]
    assert all(not r["passed"] for r in results[1:]), \
        "remaining gates must not pass when integrity fails"


TESTS = [
    ("bbox passes on fixed (D1) placement", t_bbox_passes_on_fixed_placement),
    ("bbox FAILS on broken (pre-D1) placement [regression]",
     t_bbox_fails_on_broken_placement),
    ("bbox fails when spans are missing", t_bbox_missing_span_fails),
    ("integrity passes on good PDF", t_integrity_pass),
    ("integrity fails on corrupt (non-PDF) file", t_integrity_corrupt_file),
    ("integrity fails on page-count mismatch", t_integrity_count_mismatch),
    ("integrity fails on missing file", t_integrity_missing_file),
    ("parity passes on identical PDFs", t_parity_pass),
    ("parity fails on page-count mismatch", t_parity_count_mismatch),
    ("parity skips without originals PDF", t_parity_skipped_without_originals),
    ("encoding: clean text passes", t_encoding_clean_passes),
    ("encoding: U+FFFD fails", t_encoding_replacement_char_fails),
    ("encoding: private-use fails", t_encoding_private_use_fails),
    ("encoding: control chars fail", t_encoding_control_chars_fail),
    ("encoding: CJK mojibake fails, genuine CJK passes",
     t_encoding_cjk_mojibake_fails),
    ("encoding: missing text fails, blank page passes",
     t_encoding_missing_text_fails),
    ("encoding gate end-to-end", t_encoding_gate_end_to_end),
    ("dup/missing: clean passes", t_dup_clean_passes),
    ("dup/missing: duplicate image fails", t_dup_duplicate_image_fails),
    ("dup/missing: page-number gap fails", t_dup_page_gap_fails),
    ("dup/missing: count mismatch fails", t_dup_count_mismatch_fails),
    ("run_gates: all 5 pass end-to-end", t_run_gates_all_pass),
    ("run_gates: fail-fast on broken PDF", t_run_gates_fail_fast_on_broken_pdf),
]


def main():
    print(f"running {len(TESTS)} QC-gate tests...")
    for name, fn in TESTS:
        check(name, fn)
    npass = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{npass}/{len(RESULTS)} tests passed")
    sys.exit(0 if npass == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
