#!/usr/bin/env python3
"""Generate synthetic QC fixtures: page images + matching OCR JSONs.

Creates white pages with black rectangles (fake text lines) and per-page
OCR JSONs whose boxes match those rectangles. Used by CI to exercise the
QC gates end-to-end without the copyrighted test scans (see .gitignore:
test-samples/pages/ and test-samples/output/ are never committed).

Deterministic (seeded RNG) — same fixtures on every runner and OS.

Usage: python tests/make_qc_fixtures.py <outdir>
Writes:
    <outdir>/pages/pNN.png      page images (800x1000, black rect "ink")
    <outdir>/json/pNN.json       per-page OCR JSONs (boxes match the rects)
    <outdir>/manifest.json       {"pages": [{file, page_number}]} corpus order
"""
import json
import os
import random
import sys

W, H = 800, 1000
N_PAGES = 4
WORDS = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet "
         "kilo lima mike november oscar papa quebec romeo sierra").split()


def main():
    if len(sys.argv) != 2:
        print("usage: make_qc_fixtures.py <outdir>", file=sys.stderr)
        sys.exit(1)
    outdir = sys.argv[1]
    pages_dir = os.path.join(outdir, "pages")
    json_dir = os.path.join(outdir, "json")
    os.makedirs(pages_dir, exist_ok=True)
    os.makedirs(json_dir, exist_ok=True)

    import cv2
    import numpy as np

    rng = random.Random(20261007)
    manifest = []
    for pi in range(1, N_PAGES + 1):
        img = np.full((H, W, 3), 255, dtype=np.uint8)
        boxes, header_boxes = [], []
        # header strip box
        hx0, hy0 = 60, 40
        hx1, hy1 = 740, 90
        header_boxes.append({
            "box": [[hx0, hy0], [hx1, hy0], [hx1, hy1], [hx0, hy1]],
            "text": f"synthetic header page {pi}", "conf": 0.99})
        cv2.rectangle(img, (hx0 + 4, hy0 + 6), (hx1 - 4, hy1 - 6),
                      (0, 0, 0), -1)
        # body lines: non-overlapping rows with jitter
        y = 140
        line_no = 0
        while y < H - 80:
            line_no += 1
            x0 = 60 + rng.randint(0, 120)
            # wide short boxes (the D1-sensitive shape) mixed with squares
            if rng.random() < 0.6:
                x1 = x0 + rng.randint(220, 560)
                y1 = y + rng.randint(26, 40)
            else:
                x1 = x0 + rng.randint(60, 140)
                y1 = y + rng.randint(60, 120)
            x1 = min(x1, W - 60)
            text = " ".join(rng.sample(WORDS, rng.randint(2, 5)))
            boxes.append({
                "box": [[x0, y], [x1, y], [x1, y1], [x0, y1]],
                "text": text, "conf": 0.95})
            # ink rect slightly inside the OCR box, like real OCR geometry
            cv2.rectangle(img, (x0 + 3, y + 5), (x1 - 3, y1 - 5),
                          (0, 0, 0), -1)
            y = y1 + rng.randint(18, 46)

        name = f"p{pi:02d}.png"
        cv2.imwrite(os.path.join(pages_dir, name), img)
        pj = {"file": name, "page_number": str(pi), "width": W, "height": H,
              "boxes": boxes, "header_boxes": header_boxes,
              "n_boxes": len(boxes)}
        jpath = os.path.join(json_dir, f"p{pi:02d}.json")
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(pj, f)
        manifest.append({"file": jpath, "page_number": str(pi)})

    with open(os.path.join(outdir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump({"pages": manifest}, f, indent=1)
    print(f"fixtures: {N_PAGES} pages -> {outdir}")


if __name__ == "__main__":
    main()
