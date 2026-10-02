#!/usr/bin/env python3
"""GMT800 OCR pilot runner — config-driven, category routes from pipeline.yaml.
Usage: venv/bin/python pipeline.py [--sample CSV] [--pages DIR] [--out DIR]
                                   [--report NAME]
Defaults run the pilot (samples/pilot_sample.csv -> output/). Production
passes its own page list, pages dir, and output dir; pilot behavior is
unchanged when no flags are given.
Reads: config/pipeline.yaml, config/wordlist.txt
Writes: <out>/<basename>.json per page + <out>/<report>.json
"""
import argparse, csv, json, os, re, sys, time
import cv2
import numpy as np
import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
PAGES = os.path.join(BASE, "samples", "pages")
OUT = os.path.join(BASE, "output")
# WHY: DOC_OCR_CONFIG lets the doc-ocr CLI select a profile's config dir
# (e.g. profiles/service-manual/) without code changes. Falls back to the
# scripts dir's own config/ for standalone use.
_CONFIG_DIR = os.environ.get("DOC_OCR_CONFIG",
                             os.path.join(BASE, "config"))
CFG = os.path.join(_CONFIG_DIR, "pipeline.yaml")
WORDLIST = os.path.join(_CONFIG_DIR, "wordlist.txt")
SAMPLE = os.path.join(BASE, "samples", "pilot_sample.csv")

def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)

def load_wordlist(path):
    fixes, canonical = {}, []
    for raw in open(path):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("="):
            canonical.append(line[1:])
        elif ">" in line:
            w, r = line.split(">", 1)
            fixes[w] = r
    return fixes, canonical

_OCR = None
def get_ocr():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    return _OCR

def deskew(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(bw < 128))
    if len(coords) < 100:
        return img, 0.0
    angle = cv2.minAreaRect(coords)[-1]
    angle = angle + 90 if angle < -45 else angle
    if abs(angle) < 0.3:
        return img, 0.0
    (h, w) = img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_REPLICATE), angle

def normalize(img, clip=2.0):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)

def ocr_image(img):
    res = get_ocr()(img)
    boxes = []
    if res and res[0]:
        for box, text, conf in res[0]:
            boxes.append({"box": [list(map(int, p)) for p in box],
                          "text": text, "conf": float(conf)})
    return boxes

def remap_body_boxes(boxes, W, H, strip, rotated, deskew_angle):
    """Map body-OCR boxes back to original full-page coordinates.

    OCR runs on the body image: full image -> deskew -> cut header strip ->
    (schematics) rotate 90cw. Boxes come back in that final space; invert it:
    unrotate -> undeskew -> re-add strip offset.
    Each box is {"box": [[x0,y0],[x1,y1],[x2,y2],[x3,y3]], ...}; corners are
    remapped in place and the box dicts are returned.
    """
    import math
    Wb, Hb = W, H - strip  # body dims before rotation
    for b in boxes:
        pts = b["box"]
        if rotated:
            # inverse of 90cw: (xr,yr) -> (yr, Hb-1-xr)
            pts = [[y, Hb - 1 - x] for x, y in pts]
        # to full-deskewed space, then inverse deskew rotation about center
        pts = [[x, y + strip] for x, y in pts]
        if deskew_angle:
            a = math.radians(-deskew_angle)
            ca, sa = math.cos(a), math.sin(a)
            cx, cy = W / 2.0, H / 2.0
            pts = [[cx + (x - cx) * ca - (y - cy) * sa,
                    cy + (x - cx) * sa + (y - cy) * ca] for x, y in pts]
        b["box"] = [[round(x, 1), round(y, 1)] for x, y in pts]
    return boxes

def extract_page_number(htext, cfg):
    """Primary pattern, then OCR-tolerant fallback. Returns (number, confident)."""
    m = re.search(cfg["header"]["page_pattern"], htext)
    if m:
        return m.group(0).replace(" ", ""), True
    if not cfg["header"].get("page_fallback"):
        return None, False
    # normalize common OCR confusions, then look for chapter-page shape
    norm = htext
    for a, b in [("o", "0"), ("O", "0"), ("l", "1"), ("I", "1")]:
        norm = norm.replace(a, b)
    # chapter digit, separator-ish, 1-3 page digits — anchored away from words
    m = re.search(r"(?<![A-Za-z])(\d)\s*[-–—\s]\s*(\d{1,3})(?![A-Za-z])", norm)
    if m:
        return f"{m.group(1)}-{m.group(2)}", False  # found but not confident
    return None, False

def apply_wordlist(text, fixes):
    for w, r in fixes.items():
        text = text.replace(w, r)
    return text

def process_page(fn, cat, cfg, fixes, canonical, pages_dir=PAGES):
    t0 = time.time()
    img = cv2.imread(os.path.join(pages_dir, fn))
    if img is None:
        return {"file": fn, "category": cat, "error": "unreadable"}
    h, w = img.shape[:2]
    route = cfg["routes"].get(cat, [])
    # route keys are nested oddly by the tiny parser; normalize
    steps = []
    if isinstance(route, dict):
        for k, v in route.items():
            steps.append(k)
    elif isinstance(route, list):
        for s in route:
            steps.append(s if isinstance(s, str) else next(iter(s)))

    if cfg["preprocess"].get("deskew"):
        img, angle = deskew(img)
    else:
        angle = 0.0
    if cfg["preprocess"].get("contrast") == "clahe":
        img = normalize(img, cfg["preprocess"].get("clahe_clip", 2.0))
    h, w = img.shape[:2]

    result = {"file": fn, "category": cat, "width": w, "height": h,
              "deskew_angle": round(angle, 2), "steps": steps}
    strip = int(h * cfg["header"]["strip_fraction"])
    header_img = img[0:strip, :]
    body_img = img[strip:, :]

    if "split_header" in steps or "log_rescan_ticket" in steps:
        hboxes = ocr_image(header_img)
        for b in hboxes:
            b["text"] = apply_wordlist(b["text"], fixes)
        htext = " ".join(b["text"] for b in hboxes)
        page_num, confident = extract_page_number(htext, cfg)
        result["page_number"] = page_num
        result["page_number_confident"] = confident
        if page_num and not confident:
            result["review_flag"] = "page-number ambiguous"
        result["header_text"] = htext[:200]
        # header boxes -> full-page coords (strip=0: header sits at top, no
        # unrotate) so page numbers / header text are searchable in the PDF
        W0, H0 = w, h
        remap_body_boxes(hboxes, W0, H0, 0, rotated=False, deskew_angle=angle)
        result["header_boxes"] = hboxes

    if "log_rescan_ticket" in steps:
        result["rescan_ticket"] = True
        result["elapsed_s"] = round(time.time() - t0, 1)
        return result

    if "rotate_body" in steps:
        body_img = cv2.rotate(body_img, cv2.ROTATE_90_CLOCKWISE)
        result["body_rotated"] = "90cw"

    if "ocr_body" in steps or "table_cells" in steps:
        bboxes = ocr_image(body_img)
        for b in bboxes:
            b["text"] = apply_wordlist(b["text"], fixes)
        # boxes are in processed-body space; remap to full-page coordinates
        # so search/highlight overlays land on the original scan
        W0, H0 = result["width"], result["height"]
        strip = int(H0 * cfg["header"]["strip_fraction"])
        remap_body_boxes(bboxes, W0, H0, strip,
                         rotated="rotate_body" in steps,
                         deskew_angle=angle)
        result["boxes"] = bboxes
        result["body_text"] = " ".join(b["text"] for b in bboxes)
        result["n_boxes"] = len(bboxes)
        low = cfg["qa"]["flag_low_conf_below"]
        result["low_conf_boxes"] = sum(1 for b in bboxes if b["conf"] < low)
        # canonical-term survival check
        found = result["body_text"]
        result["canonical_missing"] = [c for c in canonical
                                       if c not in found and len(c) > 2]

    result["elapsed_s"] = round(time.time() - t0, 1)
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default=SAMPLE, help="page-list CSV")
    ap.add_argument("--pages", default=PAGES, help="page images dir")
    ap.add_argument("--out", default=OUT, help="per-page JSON output dir")
    ap.add_argument("--report", default="pilot_report.json",
                    help="summary report filename")
    ap.add_argument("--progress-every", type=int, default=50,
                    help="checkpoint progress file every N pages")
    args = ap.parse_args()

    cfg = load_config(CFG)
    fixes, canonical = load_wordlist(WORDLIST)
    os.makedirs(args.out, exist_ok=True)
    with open(args.sample) as f:
        rows = list(csv.DictReader(f))
    # resume: skip pages that already have output JSON
    todo = [r for r in rows
            if not os.path.exists(os.path.join(args.out, r["filename"] + ".json"))]
    done_before = len(rows) - len(todo)
    if done_before:
        print(f"resuming: {done_before} already done, {len(todo)} to go", flush=True)
    progress_path = os.path.join(args.out, "progress.json")
    report = {"pages": [], "started": time.strftime("%Y-%m-%d %H:%M %Z"),
              "sample": args.sample}
    for i, r in enumerate(todo):
        fn, cat = r["filename"], r["category"]
        n = done_before + i + 1
        print(f"[{n}/{len(rows)}] {fn} ({cat})", flush=True)
        try:
            res = process_page(fn, cat, cfg, fixes, canonical, args.pages)
        except Exception as e:
            res = {"file": fn, "category": cat, "error": str(e)[:200]}
        report["pages"].append(res)
        with open(os.path.join(args.out, fn + ".json"), "w") as f:
            json.dump(res, f)
        if n % args.progress_every == 0:
            with open(progress_path, "w") as f:
                json.dump({"done": n, "total": len(rows),
                           "at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                           "last_file": fn}, f)
    # summary
    cats = {}
    for p in report["pages"]:
        c = cats.setdefault(p["category"], {"n": 0, "page_found": 0,
                                            "boxes": 0, "low_conf": 0,
                                            "errors": 0})
        c["n"] += 1
        if p.get("page_number"):
            c["page_found"] += 1
        c["boxes"] += p.get("n_boxes", 0)
        c["low_conf"] += p.get("low_conf_boxes", 0)
        if p.get("error"):
            c["errors"] += 1
    report["summary"] = cats
    with open(os.path.join(args.out, args.report), "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps(cats, indent=1))

if __name__ == "__main__":
    main()
