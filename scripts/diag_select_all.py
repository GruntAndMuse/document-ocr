#!/usr/bin/env python3
"""Select-all diagnostic: simulate Ctrl+A on a PDF page and draw every
invisible text span as a highlight rectangle on the scan.

What it shows, fast:
  - blue rect = placed invisible text (what select-all would highlight)
  - it should hug the visible black text exactly: no gaps, no overhang
  - overhang/merged rects = placement bug (overlapping spans break mobile selection)

Usage: venv/bin/python diag_select_all.py <pdf> <page_num_1based> <scan_jpg> <out_png>
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE))
from gruntandmuse_shared import friendly_errors  # noqa: E402

import fitz
import cv2
import numpy as np


@friendly_errors
def main():
    if len(sys.argv) != 5:
        raise ValueError(
            "usage: diag_select_all.py <pdf> <page_num_1based> "
            "<scan_jpg> <out_png>")
    pdf_path, page_no, scan_path, out_path = sys.argv[1:5]
    try:
        page_no = int(page_no) - 1
    except ValueError:
        raise ValueError(
            f"page number must be an integer, got: {sys.argv[2]!r}")
    if page_no < 0:
        raise ValueError(f"page number must be >= 1, got: {sys.argv[2]!r}")

    try:
        d = fitz.open(pdf_path)
    except Exception:
        raise ValueError(f"couldn't open as a PDF: {pdf_path}")
    if page_no >= len(d):
        raise ValueError(
            f"page {page_no + 1} out of range: PDF has {len(d)} page(s)")
    pg = d[page_no]
    W, H = pg.rect.width, pg.rect.height

    img = cv2.imread(scan_path)
    if img is None:
        raise ValueError(f"couldn't read scan image: {scan_path}")
    ih, iw = img.shape[:2]
    sx, sy = iw / W, ih / H

    overlay = img.copy()
    n = 0
    for blk in pg.get_text("dict")["blocks"]:
        if blk["type"] != 0:
            continue
        for line in blk["lines"]:
            for s in line["spans"]:
                x0, y0, x1, y1 = s["bbox"]
                p0 = (int(x0 * sx), int(y0 * sy))
                p1 = (int(x1 * sx), int(y1 * sy))
                cv2.rectangle(overlay, p0, p1, (255, 0, 0), -1)
                n += 1

    # translucent blue highlight over the scan
    alpha = 0.45
    img = cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)

    # thin outlines so rect edges are visible even where they merge
    for blk in pg.get_text("dict")["blocks"]:
        if blk["type"] != 0:
            continue
        for line in blk["lines"]:
            for s in line["spans"]:
                x0, y0, x1, y1 = s["bbox"]
                cv2.rectangle(img, (int(x0 * sx), int(y0 * sy)),
                              (int(x1 * sx), int(y1 * sy)), (255, 0, 0), 2)

    # downscale for quick viewing
    v = cv2.resize(img, (900, int(900 * ih / iw)), interpolation=cv2.INTER_AREA)
    if not cv2.imwrite(out_path, v):
        raise ValueError(f"couldn't write output image: {out_path}")
    print(f"{n} spans drawn -> {out_path}")


if __name__ == "__main__":
    main()
