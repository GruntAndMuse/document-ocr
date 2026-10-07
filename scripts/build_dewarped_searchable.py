#!/usr/bin/env python3
"""Dewarped searchable pages: visible image dewarped for readability,
OCR boxes (from the proven original-scan OCR) mapped through the same
warp so the invisible text layer stays aligned.

Coordinate logic: dewarp shifts content vertically by col_disp[x]
(output row y shows input row y+col_disp[x]), so an original point
(x, y) lands at (x, y - col_disp[x]) in the dewarped image.
Boxes are stored in original full-page coords; the demo places the raw
(non-deskewed) image, so mapping is direct.

Usage: venv/bin/python build_dewarped_searchable.py [--pages DIR] [--label STR]
       [--jpeg-q N] <out.pdf> <page1.json> ...
Defaults match the pilot layout; production passes its own pages dir.
"""
import argparse, json, os, sys
import cv2
import numpy as np
import fitz

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE))
from gruntandmuse_shared import friendly_errors  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from dewarp_test import estimate_curl  # noqa: E402
import importlib.util
spec = importlib.util.spec_from_file_location(
    "mdp", os.path.join(BASE, "make_demo_pdf.py"))
mdp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mdp)

PAGES = os.path.join(BASE, "samples", "pages")
NBINS = 60


def column_displacement(gray):
    """Per-column vertical shift col_disp[x]: content moves UP by this
    amount in the dewarped image (matches dewarp_test.dewarp_page)."""
    h, w = gray.shape
    curl, _ = estimate_curl(gray)
    return np.interp(np.arange(w), np.linspace(0, w - 1, NBINS), curl)


def map_boxes(boxes, col_disp):
    w = len(col_disp)
    out = []
    for b in boxes:
        nb = []
        for x, y in b["box"]:
            xi = min(max(int(round(x)), 0), w - 1)
            nb.append([float(x), float(y) - float(col_disp[xi])])
        c = dict(b)
        c["box"] = nb
        out.append(c)
    return out


def add_dewarped_page(doc, pj, pages_dir=PAGES, label="DEWARPED", jpeg_q=85):
    img_path = os.path.join(pages_dir, pj["file"])
    img = cv2.imread(img_path)
    if img is None:
        print(f"  WARN: unreadable image {img_path}, skipping", flush=True)
        return False
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    col_disp = column_displacement(gray)

    # dewarp visible image (same remap as dewarp_test.dewarp_page)
    h, w = gray.shape
    map_x, map_y = np.meshgrid(np.arange(w, dtype=np.float32),
                               np.arange(h, dtype=np.float32))
    map_y = map_y + col_disp[np.newaxis, :].astype(np.float32)
    dw = cv2.remap(img, map_x, map_y, cv2.INTER_CUBIC,
                   borderMode=cv2.BORDER_REPLICATE)

    ok, buf = cv2.imencode(".jpg", dw, [cv2.IMWRITE_JPEG_QUALITY, jpeg_q])
    page = doc.new_page(width=w, height=h)
    page.insert_image(page.rect, stream=buf.tobytes())

    for key in ("boxes", "header_boxes"):
        for b in map_boxes(pj.get(key, []), col_disp):
            mdp.place_box_text(page, b)
    page.insert_textbox(fitz.Rect(10, 10, w - 10, 40),
                        f"{pj['file']}  ·  {label}  ·  book page {pj.get('page_number')}",
                        fontsize=20, fontname="helv", color=(0, 0.5, 0))
    return True


@friendly_errors
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default=PAGES)
    ap.add_argument("--label", default="DEWARPED")
    ap.add_argument("--jpeg-q", type=int, default=85)
    ap.add_argument("--qc", action="store_true",
                    help="run the QC gates after building; a gate failure "
                         "fails this command (exit 1)")
    ap.add_argument("--json-dir",
                    help="dir of per-page OCR JSONs (alternative to paths)")
    ap.add_argument("out")
    ap.add_argument("jsons", nargs="*")
    args = ap.parse_args()

    jsons = mdp.collect_jsons(args.json_dir, args.jsons)
    if not jsons:
        raise ValueError("no per-page OCR JSONs found "
                         "(--json-dir or JSON paths required)")

    doc = fitz.open()
    skipped = 0
    for i, jf in enumerate(jsons):
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(jsons)}]", flush=True)
        with open(jf) as fh:
            pj = json.load(fh)
        if pj.get("error") or pj.get("rescan_ticket"):
            skipped += 1
            continue
        if not add_dewarped_page(doc, pj, args.pages, args.label, args.jpeg_q):
            skipped += 1
    doc.save(args.out)
    print(f"wrote {args.out} ({os.path.getsize(args.out)//1024}KB, "
          f"{doc.page_count} pages, skipped {skipped})")

    if args.qc:
        # Post-build hook: the GMT800 production audit as build-failing
        # gates. Known flaws don't ship — gate failure fails the build.
        import subprocess
        qc = os.path.join(BASE, "qc_gates.py")
        rc = subprocess.run(
            [sys.executable, qc, "--pdf", args.out,
             "--jsons"] + jsons).returncode
        if rc != 0:
            print("QC gates FAILED — not shipping this PDF", flush=True)
            sys.exit(1)
        print("QC gates passed", flush=True)


if __name__ == "__main__":
    main()
