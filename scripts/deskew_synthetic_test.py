#!/usr/bin/env python3
"""Synthetic test for pipeline.py deskew() angle convention and
remap_body_boxes() inverse correctness.

Method: build a fake text page, apply a KNOWN skew rotation, run the REAL
deskew() imported from pipeline.py (not a copy), and check:
  Q1: does deskew() return the correct corrective angle? (sign convention)
  Q2: does the REAL remap_body_boxes() put boxes back within 2px? (round-trip)

The old version of this test pasted a copy of deskew() into the test file,
so it tested its own copy instead of the real implementation. This version
imports from pipeline.py — if pipeline.py changes, the test follows.

Run:  python scripts/deskew_synthetic_test.py
Exit 0 = all pass. Exit 1 = any failure.
"""
import math
import os
import sys

import cv2
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from pipeline import deskew, remap_body_boxes  # noqa: E402 — the REAL ones


def make_page(w=1200, h=900, seed=0):
    img = np.full((h, w, 3), 255, np.uint8)
    rng = np.random.default_rng(seed)
    boxes = []
    for row in range(40, h - 40, 30):
        x = 60 + int(rng.integers(0, 40))
        while x < w - 140:
            bw = int(rng.integers(40, 170))
            bh = 14
            y = row + int(rng.integers(-2, 3))
            cv2.rectangle(img, (x, y), (x + bw, y + bh), (0, 0, 0), -1)
            boxes.append((x, y, x + bw, y + bh))
            x += bw + int(rng.integers(8, 26))
    return img, boxes


def apply_known_skew(img, cw_deg):
    """Simulate a scan skewed cw_deg degrees CLOCKWISE.
    getRotationMatrix2D positive = CCW, so CW skew = negative angle."""
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), -cw_deg, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_NEAREST,
                          borderValue=(255, 255, 255))


def rot_pt(x, y, cx, cy, deg_ccw):
    a = math.radians(deg_ccw)
    ca, sa = math.cos(a), math.sin(a)
    return (cx + (x - cx) * ca - (y - cy) * sa,
            cy + (x - cx) * sa + (y - cy) * ca)


def residual_angle(img):
    """Independent check: minAreaRect angle of the (possibly) deskewed page,
    normalized the same way. Near 0 => text is horizontal."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(bw < 128))
    ang = cv2.minAreaRect(coords)[-1]
    return ang + 90 if ang < -45 else ang


def main():
    print(f"{'true CW skew':>12} | {'deskew angle':>12} | {'expected':>9} | "
          f"{'residual':>8} | {'roundtrip px':>12} | verdict")
    print("-" * 80)
    all_pass = True
    for skew in [3.0, -3.0, 10.0, -10.0, 1.0]:
        img, boxes = make_page()
        h, w = img.shape[:2]
        skewed = apply_known_skew(img, skew)
        out, angle_d = deskew(skewed)  # REAL pipeline.py deskew()
        # Q1: to undo a CW skew of `skew`, deskew must rotate CCW by `skew`,
        # i.e. angle_d should equal +skew (getRotationMatrix2D CCW-positive).
        expected = skew
        angle_ok = abs(angle_d - expected) < 0.6
        res = residual_angle(out)
        # Q2: full round-trip using the REAL remap_body_boxes().
        # In the real pipeline, remap maps boxes from deskewed space back
        # to the ORIGINAL (skewed) scan coordinates. So ground truth for
        # the round-trip is the skewed position, not the pre-skew position.
        M_skew = cv2.getRotationMatrix2D((w / 2, h / 2), -skew, 1.0)
        M_skew_inv = cv2.invertAffineTransform(M_skew)
        M_deskew = cv2.getRotationMatrix2D((w // 2, h // 2), angle_d, 1.0)
        M_deskew_inv = cv2.invertAffineTransform(M_deskew)

        def xform(M, x, y):
            return (M[0, 0] * x + M[0, 1] * y + M[0, 2],
                    M[1, 0] * x + M[1, 1] * y + M[1, 2])

        max_err = 0.0
        for (x0, y0, x1, y1) in boxes[:60]:
            corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
            test_boxes = []
            exp_coords = []
            for (x, y) in corners:
                xs, ys = xform(M_skew_inv, x, y)      # skewed scan coords
                xd, yd = xform(M_deskew_inv, xs, ys)  # deskewed coords
                pt = [xd, yd]
                test_boxes.append({"box": [pt, pt, pt, pt]})
                exp_coords.append((xs, ys))  # remap targets the skewed original
            remapped = remap_body_boxes(test_boxes, w, h, 0, False, angle_d)
            for tb, (ex, ey) in zip(remapped, exp_coords):
                xr, yr = tb["box"][0]
                max_err = max(max_err, abs(xr - ex), abs(yr - ey))
        rt_ok = max_err < 2.0
        verdict = "PASS" if (angle_ok and rt_ok) else "FAIL"
        if verdict == "FAIL":
            all_pass = False
        print(f"{skew:12.1f} | {angle_d:12.2f} | {expected:9.1f} | "
              f"{res:8.2f} | {max_err:12.2f} | {verdict}")

    print("-" * 80)
    if all_pass:
        print("OVERALL: PASS — deskew corrects skew, boxes round-trip <2px")
        return 0
    print("OVERALL: FAIL — deskew angle convention is wrong; do NOT ship as-is")
    return 1


if __name__ == "__main__":
    sys.exit(main())
