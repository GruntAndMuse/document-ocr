#!/usr/bin/env python3
"""Demo searchable PDF: scan image as background, OCR boxes as invisible
selectable text on top. Proves highlight/select works on the real output.
Usage: make_demo_pdf.py [--pages DIR] <out.pdf> <page1.json> [page2.json ...]
"""
import argparse
import json, os, sys
import fitz  # pymupdf
import cv2

BASE = os.path.dirname(os.path.abspath(__file__))
PAGES = os.path.join(BASE, "samples", "pages")
JPEG_QUALITY = int(os.environ.get("DEMO_JPEG_Q", "85"))

def fit_font(txt, wid, hgt):
    """Largest helvetica size that fits inside (wid, hgt): cap-height ~0.72*fs,
    avg char width ~0.55*fs. Keeps invisible text from spilling into neighbors
    (overlapping spans break tap/drag selection on mobile viewers)."""
    if not txt or wid <= 1 or hgt <= 1:
        return 0.0
    fs_h = hgt * 0.85
    fs_w = wid / (0.55 * len(txt))
    return max(1.0, min(fs_h, fs_w))

def place_box_text(page, b):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = b["box"]
    # axis-aligned bbox: slanted parallelogram quads can make corner-pair
    # width go negative, silently dropping the box — use min/max instead
    xs = [x0, x1, x2, x3]
    ys = [y0, y1, y2, y3]
    rx0, rx1 = min(xs), max(xs)
    ry0, ry1 = min(ys), max(ys)
    wid, hgt = rx1 - rx0, ry1 - ry0
    txt = b["text"].strip()
    if not txt:
        return
    # D1 fix (2026-10-05, ported from the GMT800 production run): the
    # invisible text must be CENTERED on the OCR box, not hung from its
    # bottom edge. Previously the baseline was placed at ry1 while
    # fit_font() sized glyphs well below box height, so search highlights
    # sat ~ (hgt - glyph_h)/2 below the ink — very visible on short
    # schematic labels. Helvetica cap-height ~= 0.716*fs; centering caps
    # on the box vertical center puts the highlight on the words.
    cx, cy = (rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0
    try:
        if hgt > 2.5 * wid:
            # vertical label: rotate; text length runs along box height.
            # Center the true advance length on the box center.
            fs = fit_font(txt, hgt, wid)
            if fs <= 0:
                return
            text_len = fitz.Font("helv").text_length(txt, fontsize=fs)
            page.insert_text((cx + 0.39 * fs, cy + text_len / 2.0), txt,
                             fontsize=fs, fontname="helv",
                             render_mode=3, rotate=90)
        else:
            fs = fit_font(txt, wid, hgt)
            if fs <= 0:
                return
            page.insert_text((rx0, cy + 0.358 * fs), txt, fontsize=fs,
                             fontname="helv", render_mode=3)
    except Exception:
        pass

def add_page(doc, pj, pages_dir=PAGES):
    img_path = os.path.join(pages_dir, pj["file"])
    img = cv2.imread(img_path)
    h, w = img.shape[:2]
    # boxes are stored in original full-page coordinates; image goes in as-is
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    page = doc.new_page(width=w, height=h)
    page.insert_image(page.rect, stream=buf.tobytes())
    # invisible selectable text at each OCR box, sized to fit inside the box
    for b in pj.get("boxes", []):
        place_box_text(page, b)
    for b in pj.get("header_boxes", []):
        place_box_text(page, b)
    # label
    page.insert_textbox(fitz.Rect(10, 10, w - 10, 40),
                        f"{pj['file']}  ·  book page {pj.get('page_number')}",
                        fontsize=20, fontname="helv", color=(1, 0, 0))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default=PAGES, help="page scans dir")
    ap.add_argument("out")
    ap.add_argument("jsons", nargs="+")
    args = ap.parse_args()
    doc = fitz.open()
    for jf in args.jsons:
        with open(jf) as fh:
            add_page(doc, json.load(fh), args.pages)
    doc.save(args.out)
    print(f"wrote {args.out} ({os.path.getsize(args.out)//1024}KB, {doc.page_count} pages)")

if __name__ == "__main__":
    main()
