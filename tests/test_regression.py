#!/usr/bin/env python3
"""doc-ocr regression gate: re-run the pipeline on the 10-page corpus and
diff the OCR text artifact against golden files.

What it does:
  1. Runs scripts/pipeline_parallel.py (the real pipeline, same code path
     as `doc-ocr ocr`) on tests/regression_sample.csv with the
     service-manual profile, into a fresh temp directory.
  2. Normalizes each per-page JSON (drops volatile timing fields) and
     compares against tests/golden/page-NN.json with a byte-exact diff.
  3. Prints a unified diff for every page that differs and exits non-zero.

Exit code 0 = all 10 pages match their goldens exactly.
Exit code 1 = at least one page differs, or the pipeline run itself failed.

Environment overrides (for other machines / CI):
  REGRESS_PAGES   directory holding the 10 source page scans
                  (default: ~/workspace/gmt800-ocr-test/production/pages)
  REGRESS_WORKERS number of parallel OCR workers (default: 2)
  REGRESS_KEEP    set to 1 to keep the temp output dir for inspection

The pipeline's intermediate output goes to a temp dir (tempfile.mkdtemp,
which honors TMPDIR). If /tmp is a small tmpfs, set TMPDIR to a roomier
path before running, e.g. TMPDIR=$HOME/workspace/.tmp python3 ...
"""
import csv
import difflib
import os
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))          # tests/
PIPELINE_ROOT = os.path.dirname(BASE)                       # document-ocr/
GOLDEN_DIR = os.path.join(BASE, "golden")
SAMPLE = os.path.join(BASE, "regression_sample.csv")
PARALLEL = os.path.join(PIPELINE_ROOT, "scripts", "pipeline_parallel.py")
VENV_PY = os.path.join(PIPELINE_ROOT, "venv", "bin", "python")
PROFILE_DIR = os.path.join(PIPELINE_ROOT, "profiles", "service-manual")
PAGES_DEFAULT = os.path.expanduser(
    "~/workspace/gmt800-ocr-test/production/pages")

sys.path.insert(0, BASE)
from normalize import load_golden, load_produced  # noqa: E402


def die(msg):
    print(f"REGRESSION TEST ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def read_sample():
    with open(SAMPLE, newline="", encoding="utf-8") as f:
        return [r["filename"] for r in csv.DictReader(f)]


def main():
    for path, what in [(VENV_PY, "pipeline venv python"),
                       (PARALLEL, "pipeline_parallel.py"),
                       (PROFILE_DIR, "service-manual profile"),
                       (GOLDEN_DIR, "golden directory"),
                       (SAMPLE, "regression_sample.csv")]:
        if not os.path.exists(path):
            die(f"{what} not found: {path}")

    pages_dir = os.environ.get("REGRESS_PAGES", PAGES_DEFAULT)
    if not os.path.isdir(pages_dir):
        die(f"pages directory not found: {pages_dir} "
            f"(override with REGRESS_PAGES)")
    workers = os.environ.get("REGRESS_WORKERS", "2")

    filenames = read_sample()
    golden_files = sorted(f for f in os.listdir(GOLDEN_DIR)
                          if f.startswith("page-") and f.endswith(".json"))
    if len(golden_files) != len(filenames):
        die(f"golden count ({len(golden_files)}) != sample count "
            f"({len(filenames)}) — regenerate goldens")

    out_dir = tempfile.mkdtemp(prefix="dococr_regress_")
    keep = os.environ.get("REGRESS_KEEP") == "1"
    try:
        cmd = [VENV_PY, PARALLEL,
               "--sample", SAMPLE,
               "--pages", pages_dir,
               "--out", out_dir,
               "--report", "regress_report.json",
               "--workers", workers,
               "--config-dir", PROFILE_DIR]
        print(f"re-running pipeline on {len(filenames)} pages "
              f"({workers} workers)...", flush=True)
        proc = subprocess.run(cmd, cwd=PIPELINE_ROOT,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
        if proc.returncode != 0:
            print(proc.stdout[-4000:], file=sys.stderr)
            die(f"pipeline run failed (exit {proc.returncode}) — "
                f"see output above")

        failures = 0
        for i, fn in enumerate(filenames, start=1):
            golden_path = os.path.join(GOLDEN_DIR, f"page-{i:02d}.json")
            if not os.path.exists(golden_path):
                die(f"golden missing for sample row {i} ({fn}): {golden_path}")
            produced_path = os.path.join(out_dir, fn + ".json")
            if not os.path.exists(produced_path):
                print(f"FAIL page-{i:02d} ({fn}): pipeline produced no JSON",
                      file=sys.stderr)
                failures += 1
                continue
            golden_text = load_golden(golden_path)
            produced_text = load_produced(produced_path)
            if golden_text == produced_text:
                print(f"PASS page-{i:02d} ({fn})")
                continue
            failures += 1
            print(f"FAIL page-{i:02d} ({fn}): output differs from golden",
                  file=sys.stderr)
            diff = difflib.unified_diff(
                golden_text.splitlines(keepends=True),
                produced_text.splitlines(keepends=True),
                fromfile=f"golden/page-{i:02d}.json",
                tofile=f"produced/{fn}.json")
            sys.stderr.writelines(diff)

        print(f"\n{len(filenames) - failures}/{len(filenames)} pages match")
        sys.exit(1 if failures else 0)
    finally:
        if not keep:
            shutil.rmtree(out_dir, ignore_errors=True)
        elif 'out_dir' in dir():
            print(f"kept temp output: {out_dir}")


if __name__ == "__main__":
    main()
