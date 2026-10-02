#!/usr/bin/env python3
"""Pre-screen the 48-page red-pen searchable PDF for OCR placement quality.

For each page in redpen48.json:
  - recall: fraction of OCR boxes (boxes + header_boxes) that have a placed
    text span substantially overlapping them (overlap coefficient > 0.5,
    i.e. the smaller of box/span is mostly inside the larger)
  - overhang: fraction of spans whose bbox extends >25% beyond their
    best-matching box in any direction (catches merged/overflowing spans)
  - boxes_no_span: boxes with effectively no overlapping span
  - body recall per vertical third + header recall, for region diagnosis

The 48pp PDF is half-resolution: JSON box coords are scaled by 0.5.
Writes redpen/prescreen.json (per-page metrics + worst-first ranking).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf as fitz  # noqa: N812

BASE = os.path.dirname(os.path.abspath(__file__))
S = 0.5  # 48pp PDF scale factor


def rect_of_box(box):
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return (min(xs) * S, min(ys) * S, max(xs) * S, max(ys) * S)


def area(r):
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def inter(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)


def overlap_coef(a, b):
    """intersection / min(area) — 1.0 when the smaller is fully inside the larger."""
    m = min(area(a), area(b))
    return inter(a, b) / m if m > 0 else 0.0


def main():
    files = json.load(open(os.path.join(BASE, "redpen", "redpen48.json")))
    doc = fitz.open(os.path.join(BASE, "redpen", "redpen-searchable.pdf"))
    assert len(doc) == len(files), f"pdf pages {len(doc)} != files {len(files)}"

    pages = []
    for idx, fn in enumerate(files):
        pj = json.load(open(os.path.join(BASE, "output", fn + ".json")))
        allb = []  # (rect, kind, text)
        for b in pj.get("boxes", []):
            if b.get("text", "").strip():
                allb.append((rect_of_box(b["box"]), "body", b["text"].strip()))
        for b in pj.get("header_boxes", []):
            if b.get("text", "").strip():
                allb.append((rect_of_box(b["box"]), "header", b["text"].strip()))

        pg = doc[idx]
        W, H = pg.rect.width, pg.rect.height
        spans = []
        for blk in pg.get_text("dict")["blocks"]:
            if blk["type"] != 0:
                continue
            for ln in blk["lines"]:
                for sp in ln["spans"]:
                    if sp["text"].strip():
                        spans.append(tuple(sp["bbox"]))

        # per-box best overlap
        best = []  # (kind, coef, text)
        for (r, kind, t) in allb:
            m = max([overlap_coef(r, s) for s in spans], default=0.0)
            best.append((kind, m, t))

        n = len(best)
        recall = sum(1 for _, m, _ in best if m > 0.5) / n if n else None
        no_span = [(t, k) for k, m, t in best if m < 0.05]
        hrec = [m for k, m, _ in best if k == "header"]
        header_recall = (
            sum(1 for m in hrec if m > 0.5) / len(hrec) if hrec else None
        )
        thirds = []
        for q in range(3):
            ms = [
                m
                for (r, k, _), (kk, m, _) in zip(allb, best)
                if k == "body"
                and q * H / 3 <= (r[1] + r[3]) / 2 < (q + 1) * H / 3
            ]
            thirds.append(
                round(sum(1 for m in ms if m > 0.5) / len(ms), 3) if ms else None
            )

        # per-span overhang vs best box.
        # Real overhang = span spills far beyond its box (merged/overflowing
        # spans that break mobile selection). Minor line-height padding
        # (descender dip below baseline, ~30% on tiny boxes) is normal and
        # must NOT count: threshold 50% per direction, or span much larger
        # than its box.
        oh = 0
        oh_examples = []
        for s in spans:
            bi = None
            bm = 0.0
            for i, (r, _, _) in enumerate(allb):
                c = overlap_coef(r, s)
                if c > bm:
                    bm, bi = c, i
            if bi is None:
                oh += 1
                continue
            r = allb[bi][0]
            bw, bh = r[2] - r[0], r[3] - r[1]
            if bw <= 0 or bh <= 0:
                continue
            ext = [
                max(0.0, r[0] - s[0]) / bw,
                max(0.0, s[2] - r[2]) / bw,
                max(0.0, r[1] - s[1]) / bh,
                max(0.0, s[3] - r[3]) / bh,
            ]
            big = area(s) > 2.5 * area(r)
            if max(ext) > 0.5 or big:
                oh += 1
                if len(oh_examples) < 8:
                    oh_examples.append(
                        {
                            "span_overhang_max": round(max(ext), 2),
                            "span_vs_box_area": round(area(s) / area(r), 2)
                            if area(r) > 0
                            else None,
                            "near_box_text": allb[bi][2][:40],
                        }
                    )
        overhang = oh / len(spans) if spans else None

        score = (1 - recall if recall is not None else 0) + (
            overhang if overhang is not None else 0
        )
        pages.append(
            {
                "page": idx + 1,
                "file": fn,
                "category": pj.get("category"),
                "page_number": pj.get("page_number"),
                "n_boxes": sum(1 for _, k, _ in allb if k == "body"),
                "n_header_boxes": sum(1 for _, k, _ in allb if k == "header"),
                "n_spans": len(spans),
                "recall": round(recall, 3) if recall is not None else None,
                "header_recall": round(header_recall, 3)
                if header_recall is not None
                else None,
                "body_recall_thirds": thirds,
                "overhang": round(overhang, 3)
                if overhang is not None
                else None,
                "boxes_no_span": len(no_span),
                "missing_examples": [
                    {"kind": k, "text": t[:60]} for t, k in no_span[:10]
                ],
                "overhang_examples": oh_examples,
                "score": round(score, 3),
            }
        )

    ranked = sorted(pages, key=lambda p: -p["score"])
    json.dump(
        {
            "pages": pages,
            "ranked_worst_first": [p["page"] for p in ranked],
            "metric_notes": {
                "recall": "fraction of OCR boxes with a placed span overlapping (overlap coef > 0.5)",
                "overhang": "fraction of spans spilling >50% beyond best box in any direction, or span area >2.5x box (merged/overflow spans)",
                "score": "(1-recall) + overhang; higher = worse",
                "body_recall_thirds": "[top, middle, bottom] body-box recall",
            },
        },
        open(os.path.join(BASE, "redpen", "prescreen.json"), "w"),
        indent=1,
    )
    print(f"wrote prescreen.json for {len(pages)} pages")
    print("--- worst 8 ---")
    for p in ranked[:8]:
        print(
            f"p{p['page']} {p['file']} score={p['score']} recall={p['recall']} "
            f"overhang={p['overhang']} no_span={p['boxes_no_span']} "
            f"thirds={p['body_recall_thirds']} hrec={p['header_recall']}"
        )


if __name__ == "__main__":
    main()
