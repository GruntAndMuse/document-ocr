#!/usr/bin/env python3
"""Measure page-curl amplitude: for long horizontal text-line blobs, measure
max vertical deviation of the line's center from its endpoint chord."""
import cv2, glob, csv, sys
import numpy as np

def curl_score(img_path):
    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0, 0
    h, w = img.shape
    # work on body region (skip top 12% header)
    body = img[int(h*0.12):, :]
    bh, bw = body.shape
    _, th = cv2.threshold(body, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # merge chars into text lines: wide horizontal close
    kx = max(30, bw // 40)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kx, 7))
    closed = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel)
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    devs = []
    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        # long horizontal line-like blobs only
        if cw < bw * 0.25 or ch > 120 or cw / max(ch, 1) < 6:
            continue
        # sample vertical center across the blob width
        xs = np.linspace(x + cw*0.05, x + cw*0.95, 25).astype(int)
        col = closed[y:y+ch, :]
        centers = []
        for xi in xs:
            rows = np.where(col[:, xi] > 0)[0]
            if len(rows):
                centers.append(np.median(rows) + y)
        if len(centers) < 12:
            continue
        centers = np.array(centers)
        # smooth
        s = np.convolve(centers, np.ones(5)/5, mode='same')
        # deviation from endpoint chord
        chord = np.linspace(s[0], s[-1], len(s))
        devs.append(np.max(np.abs(s - chord)))
    if not devs:
        return 0.0, 0
    return float(np.median(devs)), len(devs)

if __name__ == '__main__':
    rows = []
    cats = {}
    with open('samples/pilot_sample.csv') as f:
        for r in csv.DictReader(f):
            cats[r['filename']] = r['category']
    for f in sorted(glob.glob('samples/pages/*.jpg')):
        fn = f.split('/')[-1]
        cat = cats.get(fn, '?')
        if cat not in ('troubleshooting', 'text', 'schematic_text', 'diagram'):
            continue
        score, nlines = curl_score(f)
        rows.append((score, nlines, fn, cat))
    rows.sort(reverse=True)
    print(f"{'score':>7} {'lines':>5}  file (category)")
    for s, n, fn, cat in rows[:15]:
        print(f"{s:7.1f} {n:5d}  {fn} ({cat})")
