#!/usr/bin/env python3
"""Stratified pilot sampler: pick a small deterministic sample across
categories from a manifest, deliberately spread to catch variety.

Usage:
    python sampler.py --manifest manifest.csv --out sample.csv [--n 100] [--seed 20260929]

Manifest CSV columns: filename,category[,chapter]
  - filename: page image filename
  - category: page type (must match a route in your pipeline.yaml)
  - chapter:  optional grouping (spread sampling across chapters)

The sample is deterministic (seeded) so it's reproducible.
The real hard-case curation happens after the first visual pass —
this just gets you a representative starting set.

WHY stratified: random sampling over-represents common page types and
misses rare ones. A wiring diagram that's 2% of pages is 100% of your
debugging if the pipeline chokes on it.
"""
import argparse
import csv
import os
import random
import sys
from collections import defaultdict, Counter


def die(msg, hint=None):
    print(f"error: {msg}", file=sys.stderr)
    if hint:
        print(f"hint: {hint}", file=sys.stderr)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Stratified pilot sampler")
    ap.add_argument("--manifest", required=True,
                    help="manifest CSV (columns: filename,category[,chapter])")
    ap.add_argument("--out", required=True, help="output sample CSV path")
    ap.add_argument("--n", type=int, default=100, help="target sample size")
    ap.add_argument("--seed", type=int, default=20260929,
                    help="random seed (change for a different sample)")
    ap.add_argument("--targets",
                    help="category targets as cat:n,cat:n (default: proportional)")
    args = ap.parse_args()

    if not os.path.exists(args.manifest):
        die(f"manifest not found: {args.manifest}")

    random.seed(args.seed)

    # WHY: DictReader handles the optional chapter column gracefully —
    # .get("chapter", "?") returns "?" if the column is missing.
    with open(args.manifest) as f:
        rows = list(csv.DictReader(f))
    if not rows or "filename" not in rows[0] or "category" not in rows[0]:
        die(f"manifest needs at least 'filename' and 'category' columns",
            f"found columns: {list(rows[0].keys()) if rows else '(empty)'}")

    # Group by category, then chapter
    by_cat_ch = defaultdict(lambda: defaultdict(list))
    for r in rows:
        cat = r["category"].strip()
        ch = r.get("chapter", "?").strip() or "?"
        by_cat_ch[cat][ch].append(r["filename"].strip())

    # Targets: explicit or proportional
    if args.targets:
        targets = {}
        for pair in args.targets.split(","):
            cat, n = pair.split(":")
            targets[cat.strip()] = int(n)
    else:
        # WHY: Proportional with a floor of 1 per category. Rare categories
        # get at least one page — that's the whole point of stratification.
        # Without the floor, a 1% category vanishes from a 100-page sample.
        total = len(rows)
        targets = {}
        for cat, chs in by_cat_ch.items():
            count = sum(len(v) for v in chs.values())
            targets[cat] = max(1, round(args.n * count / total))

    sample = []
    for cat, target in targets.items():
        pool = by_cat_ch.get(cat, {})
        if not pool:
            print(f"  warn: category '{cat}' not in manifest, skipping",
                  file=sys.stderr)
            continue
        # Flatten chapters, round-robin across them to spread the sample
        chs = sorted(pool.keys())
        all_pages = []
        for ch in chs:
            all_pages.extend(sorted(pool[ch]))
        # WHY: Stride instead of random.sample — deterministic spread through
        # the page sequence catches variety (early/middle/late pages differ).
        step = max(1, len(all_pages) // target)
        picked = []
        idx = 0
        while len(picked) < target and idx < len(all_pages) * 2:
            cand = all_pages[(idx * step) % len(all_pages)]
            if cand not in picked:
                picked.append(cand)
            idx += 1
            if len(picked) >= len(all_pages):
                break
        # Map back to chapters for the output CSV
        fn_to_ch = {}
        for ch in chs:
            for fn in pool[ch]:
                fn_to_ch[fn] = ch
        sample.extend((fn, cat, fn_to_ch.get(fn, "?")) for fn in picked[:target])

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["filename", "category", "chapter"])
        for fn, cat, ch in sorted(sample):
            w.writerow([fn, cat, ch])
    print(f"sampled {len(sample)} pages -> {args.out}")
    print(Counter(c for _, c, _ in sample))


if __name__ == "__main__":
    main()
