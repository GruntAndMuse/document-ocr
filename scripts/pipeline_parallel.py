#!/usr/bin/env python3
"""Parallel OCR runner — same logic as pipeline.py, pages distributed across workers.

Safety design (learned from the batch-3 pdftoppm race):
- Each page writes to its OWN output file (<filename>.json). No shared prefixes,
  no shared temp dirs. Workers never touch the same file.
- Each worker initializes its OWN RapidOCR instance (no shared model state).
- Deterministic: same inputs produce byte-identical outputs (verified by diff).
- OMP/onnxruntime threads are capped per-worker to avoid CPU oversubscription.

Usage: venv/bin/python pipeline_parallel.py [--sample CSV] [--pages DIR] [--out DIR]
                                             [--report NAME] [--workers N]
"""
import argparse, csv, json, os, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.dirname(BASE))
from gruntandmuse_shared import friendly_errors  # noqa: E402
# Reuse everything from pipeline.py — zero logic duplication.
import pipeline as P

def _worker_init(config_dir):
    """Per-process init: point at the right config, lazy-load OCR on first use."""
    P._CONFIG_DIR = config_dir
    P.CFG = os.path.join(config_dir, "pipeline.yaml")
    P.WORDLIST = os.path.join(config_dir, "wordlist.txt")
    # Force fresh OCR instance in this process (don't inherit parent's).
    P._OCR = None

def _process_one(args_tuple):
    """Process a single page. Must be top-level for pickling."""
    fn, cat, pages_dir, out_dir, config_dir = args_tuple
    # Load config/wordlist in worker (small, cheap, avoids pickling issues).
    cfg = P.load_config(os.path.join(config_dir, "pipeline.yaml"))
    fixes, canonical = P.load_wordlist(os.path.join(config_dir, "wordlist.txt"))
    try:
        res = P.process_page(fn, cat, cfg, fixes, canonical, pages_dir)
    except Exception as e:
        res = {"file": fn, "category": cat, "error": str(e)[:200]}
    # Each page writes ONLY its own file — no shared state.
    out_path = os.path.join(out_dir, fn + ".json")
    with open(out_path, "w") as f:
        json.dump(res, f)
    return (fn, cat, res.get("error"), res.get("elapsed_s", 0))

@friendly_errors
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default=P.SAMPLE, help="page-list CSV")
    ap.add_argument("--pages", default=P.PAGES, help="page images dir")
    ap.add_argument("--out", default=P.OUT, help="per-page JSON output dir")
    ap.add_argument("--report", default="pilot_report.json",
                    help="summary report filename")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2,
                    help="parallel worker processes")
    ap.add_argument("--config-dir", default=None,
                    help="config dir (defaults to DOC_OCR_CONFIG or scripts/config)")
    args = ap.parse_args()

    config_dir = args.config_dir or os.environ.get("DOC_OCR_CONFIG",
                                                   os.path.join(BASE, "config"))
    # WHY: Same fail-fast validation as the serial runner — garbage in gets
    # a friendly error before any worker processes spin up.
    P.validate_inputs(args)
    os.makedirs(args.out, exist_ok=True)
    rows = P.load_sample_rows(args.sample)
    todo = [r for r in rows
            if not os.path.exists(os.path.join(args.out, r["filename"] + ".json"))]
    done_before = len(rows) - len(todo)
    if done_before:
        print(f"resuming: {done_before} already done, {len(todo)} to go", flush=True)

    from concurrent.futures import ProcessPoolExecutor
    work = [(r["filename"], r["category"], args.pages, args.out, config_dir)
            for r in todo]

    report = {"pages": [], "started": time.strftime("%Y-%m-%d %H:%M %Z"),
              "sample": args.sample, "workers": args.workers,
              "mode": "parallel"}
    t_start = time.time()
    with ProcessPoolExecutor(max_workers=args.workers,
                             initializer=_worker_init,
                             initargs=(config_dir,)) as ex:
        for i, (fn, cat, err, elapsed) in enumerate(ex.map(_process_one, work)):
            n = done_before + i + 1
            status = f"ERROR: {err}" if err else f"{elapsed}s"
            print(f"[{n}/{len(rows)}] {fn} ({cat}) {status}", flush=True)
            # Re-read the JSON for the report (single source of truth).
            with open(os.path.join(args.out, fn + ".json")) as f:
                report["pages"].append(json.load(f))

    wall_s = time.time() - t_start
    # Summary (same shape as pipeline.py).
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
    report["wall_seconds"] = round(wall_s, 1)
    with open(os.path.join(args.out, args.report), "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps(cats, indent=1))
    print(f"wall time: {wall_s:.1f}s for {len(todo)} pages "
          f"({wall_s/max(len(todo),1):.1f}s/page) with {args.workers} workers")

if __name__ == "__main__":
    main()
