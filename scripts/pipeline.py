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
# WHY: friendly_errors lives in the pipeline root next to the scripts dir.
# Adding it to sys.path lets every script share one error-handling helper.
sys.path.insert(0, os.path.dirname(BASE))
from gruntandmuse_shared import friendly_errors  # noqa: E402
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
        cfg = yaml.safe_load(f)
    # Validate header.strip_fraction at load — a bad value segfaults
    # OpenCV later instead of raising a clean Python error.
    sf = cfg.get("header", {}).get("strip_fraction", 0.15)
    if not isinstance(sf, (int, float)) or not (0 <= sf < 1.0):
        raise ValueError(
            f"config header.strip_fraction must be in [0, 1), got {sf!r}")
    return cfg

def load_wordlist(path):
    fixes, canonical = {}, []
    for raw in open(path):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("="):
            canonical.append(line[1:].strip())
        elif ">" in line:
            w, r = line.split(">", 1)
            fixes[w.strip()] = r.strip()
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
    # WHY: minAreaRect returns [-90, 0) in the *opposite* sign convention from
    # getRotationMatrix2D (CCW-positive). Without negation, deskew rotates the
    # page the wrong way and DOUBLES the skew (verified 2026-10-10 with
    # scripts/deskew_synthetic_test.py: 3 deg skew -> -3.00 angle, 6 deg
    # residual). Negate to get the true corrective rotation.
    angle = -(90 + angle) if angle < -45 else -angle
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
    # WHY word boundaries: blind substring replace corrupts real words
    # (e.g. "amp>AMP" turned "camp" into "cAMP"). OCR confusions are
    # whole-token errors, so replacements match whole tokens only.
    for w, r in fixes.items():
        if w:
            text = re.sub(r"\b" + re.escape(w) + r"\b", lambda m: r, text)
    return text

def process_page(fn, cat, cfg, fixes, canonical, pages_dir=PAGES):
    t0 = time.time()
    timings = {}
    def mark(stage, t_start):
        timings[stage] = round((time.time() - t_start) * 1000, 1)

    ts = time.time()
    img_path = os.path.join(pages_dir, fn)
    # Symlink + size guards: resolve the real path and confirm it's inside
    # pages_dir (a symlink could point anywhere); refuse absurd file sizes
    # before cv2.imread allocates memory for a decompression bomb.
    real = os.path.realpath(img_path)
    if not real.startswith(os.path.realpath(pages_dir) + os.sep):
        return {"file": fn, "category": cat, "error": "unsafe path"}
    if os.path.getsize(real) > 100 * 1024 * 1024:
        return {"file": fn, "category": cat, "error": "image too large"}
    img = cv2.imread(real)
    mark("read_ms", ts)
    if img is None:
        return {"file": fn, "category": cat, "error": "unreadable"}
    h, w = img.shape[:2]
    if h * w > 12000 * 12000:
        return {"file": fn, "category": cat, "error": "image dimensions too large"}
    h, w = img.shape[:2]
    if cat not in cfg["routes"]:
        raise ValueError(
            f"unknown category {cat!r} for page {fn!r} — valid: "
            f"{', '.join(sorted(cfg['routes']))}")
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
        ts = time.time()
        img, angle = deskew(img)
        mark("deskew_ms", ts)
    else:
        angle = 0.0
    if cfg["preprocess"].get("contrast") == "clahe":
        ts = time.time()
        img = normalize(img, cfg["preprocess"].get("clahe_clip", 2.0))
        mark("normalize_ms", ts)
    h, w = img.shape[:2]

    result = {"file": fn, "category": cat, "width": w, "height": h,
              "deskew_angle": round(angle, 2), "steps": steps}
    strip = int(h * cfg["header"]["strip_fraction"])
    header_img = img[0:strip, :]
    body_img = img[strip:, :]

    if "split_header" in steps or "log_rescan_ticket" in steps:
        ts = time.time()
        hboxes = ocr_image(header_img)
        mark("header_ocr_ms", ts)
        ts = time.time()
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
        mark("header_post_ms", ts)

    if "log_rescan_ticket" in steps:
        result["rescan_ticket"] = True
        result["elapsed_s"] = round(time.time() - t0, 1)
        return result

    if "rotate_body" in steps:
        ts = time.time()
        body_img = cv2.rotate(body_img, cv2.ROTATE_90_CLOCKWISE)
        mark("rotate_ms", ts)
        result["body_rotated"] = "90cw"

    if "ocr_body" in steps or "table_cells" in steps:
        ts = time.time()
        bboxes = ocr_image(body_img)
        mark("body_ocr_ms", ts)
        ts = time.time()
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
        mark("body_post_ms", ts)

    result["timings"] = timings
    result["elapsed_s"] = round(time.time() - t0, 1)
    return result

REQUIRED_CSV_COLS = ("filename", "category")

def validate_inputs(args):
    """Fail fast with a plain-English error before any OCR work starts."""
    if not os.path.isfile(args.sample):
        if os.path.isdir(args.sample):
            raise ValueError(
                f"sample path is a directory, not a CSV file: {args.sample}")
        raise ValueError(f"sample CSV not found: {args.sample}")
    if not os.path.isdir(args.pages):
        raise ValueError(
            f"pages directory not found: {args.pages}\n"
            "       point --pages at the folder holding your page scans")


def load_sample_rows(path):
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        missing = [c for c in REQUIRED_CSV_COLS
                   if not reader.fieldnames or c not in reader.fieldnames]
        if missing:
            have = ", ".join(reader.fieldnames or ["(empty file)"])
            raise ValueError(
                f"sample CSV is missing required column(s): "
                f"{', '.join(missing)} (has: {have})")
    # WHY validate here, before any OCR work: a "../" filename would read
    # outside the pages dir and write outside the output dir (path traversal),
    # and a duplicate would silently overwrite the first page's JSON.
    seen = set()
    for r in rows:
        fn = r["filename"]
        if "/" in fn or "\\" in fn or ".." in fn or "\x00" in fn:
            raise ValueError(
                f"unsafe filename in CSV: {fn!r} — use plain file names, "
                f"not paths")
        if fn in seen:
            raise ValueError(f"duplicate filename in CSV: {fn!r}")
        seen.add(fn)
    return rows


@friendly_errors
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
    if args.progress_every < 1:
        raise ValueError("--progress-every must be 1 or more")

    cfg = load_config(CFG)
    fixes, canonical = load_wordlist(WORDLIST)
    validate_inputs(args)
    os.makedirs(args.out, exist_ok=True)
    rows = load_sample_rows(args.sample)
    # resume: skip pages that already have a *successful* output JSON.
    # Pages that errored (or died mid-write leaving a corrupt partial file)
    # are retried instead of being skipped forever.
    def needs_work(r):
        p = os.path.join(args.out, r["filename"] + ".json")
        if not os.path.exists(p):
            return True
        try:
            with open(p) as f:
                return "error" in json.load(f)
        except Exception:
            return True
    # clean up stale temp files from crashed runs
    for f in os.listdir(args.out):
        if f.endswith(".json.tmp"):
            os.remove(os.path.join(args.out, f))
    todo = [r for r in rows if needs_work(r)]
    done_before = len(rows) - len(todo)
    if done_before:
        print(f"resuming: {done_before} already done, {len(todo)} to go", flush=True)
    progress_path = os.path.join(args.out, "progress.json")
    report = {"pages": [], "started": time.strftime("%Y-%m-%d %H:%M %Z"),
              "sample": args.sample}
    # WHY: a resumed run must report on ALL pages, not just this run's.
    # Load already-successful pages so the final summary is complete.
    todo_fns = {r["filename"] for r in todo}
    for r in rows:
        if r["filename"] not in todo_fns:
            with open(os.path.join(args.out, r["filename"] + ".json")) as f:
                report["pages"].append(json.load(f))
    for i, r in enumerate(todo):
        fn, cat = r["filename"], r["category"]
        n = done_before + i + 1
        print(f"[{n}/{len(rows)}] {fn} ({cat})", flush=True)
        try:
            res = process_page(fn, cat, cfg, fixes, canonical, args.pages)
        except Exception as e:
            res = {"file": fn, "category": cat, "error": str(e)[:200]}
        report["pages"].append(res)
        # WHY tmp + os.replace: a crash mid-write must never leave a partial
        # .json that resume mistakes for a finished page.
        out_path = os.path.join(args.out, fn + ".json")
        tmp_path = out_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(res, f)
        os.replace(tmp_path, out_path)
        if n % args.progress_every == 0:
            with open(progress_path + ".tmp", "w") as f:
                json.dump({"done": n, "total": len(rows),
                           "at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                           "last_file": fn}, f)
            os.replace(progress_path + ".tmp", progress_path)
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
    report_path = os.path.join(args.out, args.report)
    with open(report_path + ".tmp", "w") as f:
        json.dump(report, f, indent=1)
    os.replace(report_path + ".tmp", report_path)
    print(json.dumps(cats, indent=1))

if __name__ == "__main__":
    main()
