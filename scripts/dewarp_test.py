#!/usr/bin/env python3
"""Page-curl dewarping go/no-go experiment.

Cylindrical model: book-gutter curl displaces text vertically as a smooth
function of x only. Estimate d(x) from text-line positions, then flatten
with cv2.remap. Compare pipeline OCR (char count, mean confidence) on
original vs dewarped.
"""
import cv2, json, os, sys, time
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from pipeline import ocr_image, deskew  # noqa: E402

PAGES = os.path.join(BASE, "samples", "pages")
OUTDIR = os.path.join(BASE, "redpen", "dewarp_test")

TEST_PAGES = [
    "GMT00ST_1_BRAKE_00001.jpg",
    "GMT00ST_1_DRIVELINE_AXLE_00001.jpg",
    "GMT00ST_1_HVAC_00001.jpg",
    "GMT00ST_1_GENERALINFOMATION_00001.jpg",
    "GMT00ST_5_RESTRAINTS_00001.jpg",
]

NBINS = 60


def estimate_curl(gray):
    """Return d(x): vertical displacement in px, length NBINS, mean-zero."""
    h, w = gray.shape
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kx = max(40, w // 35)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kx, 5))
    closed = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel)
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # per-bin residual accumulator
    sums = np.zeros(NBINS)
    counts = np.zeros(NBINS)
    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < w * 0.12 or ch > 110 or cw / max(ch, 1) < 5:
            continue
        xs = np.linspace(x + cw * 0.05, x + cw * 0.95, 40).astype(int)
        xs = np.clip(xs, 0, w - 1)
        strip = closed[y:y + ch, :]
        centers = []
        for xi in xs:
            rows = np.where(strip[:, xi] > 0)[0]
            if len(rows):
                centers.append(np.median(rows) + y)
        if len(centers) < 15:
            continue
        centers = np.array(centers)
        resid = centers - np.median(centers)
        bins = np.clip((xs / w * NBINS).astype(int), 0, NBINS - 1)
        for bi, r in zip(bins, resid):
            sums[bi] += r
            counts[bi] += 1
    raw = np.divide(sums, counts, out=np.full(NBINS, np.nan), where=counts >= 3)
    # interpolate NaN bins
    idx = np.arange(NBINS)
    good = ~np.isnan(raw)
    if good.sum() < 8:
        return np.zeros(NBINS), 0.0
    curl = np.interp(idx, idx[good], raw[good])
    # gaussian smooth
    k = np.exp(-0.5 * (np.arange(-9, 10) / 4.0) ** 2)
    k /= k.sum()
    curl = np.convolve(np.pad(curl, 9, mode='edge'), k, mode='valid')
    amp = float(np.max(curl) - np.min(curl))
    curl -= curl.mean()
    return curl, amp


def dewarp_page(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    curl, amp = estimate_curl(gray)
    h, w = gray.shape
    # per-column displacement in px
    col_disp = np.interp(np.arange(w), np.linspace(0, w - 1, NBINS), curl)
    map_x, map_y = np.meshgrid(np.arange(w, dtype=np.float32),
                               np.arange(h, dtype=np.float32))
    map_y = map_y + col_disp[np.newaxis, :].astype(np.float32)
    out = cv2.remap(img, map_x, map_y, cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE)
    return out, amp


def ocr_body(img):
    """Pipeline-equivalent: deskew -> strip header -> OCR body."""
    dimg, _ = deskew(img)
    h = dimg.shape[0]
    strip = int(h * 0.10)
    body = dimg[strip:, :]
    t0 = time.time()
    boxes = ocr_image(body)
    dt = time.time() - t0
    chars = sum(len(b["text"]) for b in boxes)
    mean_conf = float(np.mean([b["conf"] for b in boxes])) if boxes else 0.0
    return {"nboxes": len(boxes), "chars": chars,
            "mean_conf": round(mean_conf, 4), "ocr_s": round(dt, 1)}


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    results = []
    for fn in TEST_PAGES:
        print(f"--- {fn}", flush=True)
        img = cv2.imread(os.path.join(PAGES, fn))
        t0 = time.time()
        dewarped, amp_orig = dewarp_page(img)
        dewarp_s = round(time.time() - t0, 1)
        # residual curl after dewarp (quality check)
        _, amp_resid = estimate_curl(cv2.cvtColor(dewarped, cv2.COLOR_BGR2GRAY))

        m_orig = ocr_body(img)
        m_dw = ocr_body(dewarped)

        rec = {"file": fn, "curl_amp_px": round(amp_orig, 1),
               "residual_curl_px": round(amp_resid, 1),
               "dewarp_s": dewarp_s, "original": m_orig, "dewarped": m_dw}
        dchars = m_dw["chars"] - m_orig["chars"]
        dconf = round(m_dw["mean_conf"] - m_orig["mean_conf"], 4)
        rec["delta_chars"] = dchars
        rec["delta_conf"] = dconf
        results.append(rec)
        print(f"  curl {amp_orig:.0f}px -> residual {amp_resid:.0f}px | "
              f"chars {m_orig['chars']} -> {m_dw['chars']} ({dchars:+d}) | "
              f"conf {m_orig['mean_conf']:.3f} -> {m_dw['mean_conf']:.3f} ({dconf:+.4f})",
              flush=True)

        # side-by-side with guide lines
        h, w = img.shape[:2]
        scale = 800 / w
        small_o = cv2.resize(img, (800, int(h * scale)))
        small_d = cv2.resize(dewarped, (800, int(h * scale)))
        sh = small_o.shape[0]
        for gy in np.linspace(sh * 0.15, sh * 0.9, 6):
            cv2.line(small_o, (0, int(gy)), (800, int(gy)), (0, 0, 255), 2)
            cv2.line(small_d, (0, int(gy)), (800, int(gy)), (0, 0, 255), 2)
        cv2.putText(small_o, "ORIGINAL", (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    1.2, (0, 0, 255), 3)
        cv2.putText(small_d, "DEWARPED", (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    1.2, (0, 0, 255), 3)
        side = np.hstack([small_o, small_d])
        cv2.imwrite(os.path.join(OUTDIR, fn.replace(".jpg", "_sidebyside.png")), side)

    with open(os.path.join(OUTDIR, "results.json"), "w") as f:
        json.dump(results, f, indent=1)
    # summary
    dc = [r["delta_chars"] for r in results]
    df = [r["delta_conf"] for r in results]
    print(f"\nMEAN delta chars: {np.mean(dc):+.0f} | MEAN delta conf: {np.mean(df):+.4f}")


if __name__ == "__main__":
    main()
