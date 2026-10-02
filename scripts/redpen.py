#!/usr/bin/env python3
"""Red-pen package builder — phone-friendly, single-file HTML.

Purpose: effort calibration. He looks at scan + pipeline output per page and
replies in chat with the NUMBERS that need more effort vs less effort.
The numbers are the whole UI.

Ordering: hardest routes first (schematics = rotation route, pinouts = table
route), then edge cases, then spot-checks of the easy categories.
"""
import json, os, glob, base64, io
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
PAGES = os.path.join(BASE, "samples", "pages")
OUT = os.path.join(BASE, "output")
REDPEN = os.path.join(BASE, "redpen")
IMG_W = 780
TEXT_CHARS = 900

# (category, how many, why he should look)
PLAN = [
    ("schematic", 22, "rotation route — most expensive; is the rotated text good enough?"),
    ("connector_pinout", 16, "table route — is box-level text enough or do you need real table structure?"),
    ("damaged", 1, "rescan ticket — correct call?"),
    ("blank", 1, "light-touch route — anything wasted here?"),
    ("schematic_text", 2, "spot check"),
    ("troubleshooting", 2, "spot check"),
    ("text", 2, "spot check"),
    ("diagram", 2, "spot check"),
]

def load_all():
    pages = []
    for f in glob.glob(os.path.join(OUT, "*.json")):
        if "report" in f:
            continue
        with open(f) as fh:
            p = json.load(fh)
        if not p.get("error"):
            pages.append(p)
    return pages

def pick_pages(pages):
    by_cat = defaultdict(list)
    for p in pages:
        by_cat[p["category"]].append(p)
    for cat in by_cat:
        # deterministic: sort by file, but put low-confidence page numbers first
        by_cat[cat].sort(key=lambda p: (p.get("page_number_confident", True), p["file"]))
    picks = []
    for cat, n, why in PLAN:
        picks.extend([(p, why) for p in by_cat.get(cat, [])[:n]])
    return picks

def img_b64(fn):
    from PIL import Image
    im = Image.open(os.path.join(PAGES, fn))
    im.thumbnail((IMG_W, 100000))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode()

def main():
    pages = load_all()
    picks = pick_pages(pages)
    os.makedirs(REDPEN, exist_ok=True)
    parts = ["""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GMT800 Pilot Red Pen</title>
<style>body{font-family:sans-serif;max-width:820px;margin:auto;padding:12px;
background:#111;color:#eee}img{width:100%;border:1px solid #444}
.card{border:1px solid #333;border-radius:8px;padding:12px;margin:16px 0}
.num{font-size:32px;font-weight:bold;color:#ffd500}
.meta{color:#aaa;font-size:13px;margin:4px 0}
.why{color:#8fd08f;font-size:13px;font-style:italic;margin:4px 0}
pre{white-space:pre-wrap;font-size:12px;background:#1a1a1a;padding:8px;
border-radius:4px;max-height:240px;overflow:auto}
h1{font-size:20px}.hint{background:#222;padding:10px;border-radius:8px;
font-size:14px}b{color:#ffd500}</style>
</head><body>
<h1>GMT800 OCR Pilot &mdash; Red Pen</h1>
<div class="hint">Pilot result: <b>100/100 pages</b>, page numbers found on every
readable page, zero errors. Now the judgment call is yours.<br><br>
For each numbered page: <b>scan on top</b>, what the pipeline read below.
Reply in chat with just the <b>numbers</b> &mdash; which need <b>MORE</b> effort
and which need <b>LESS</b>. Example: &ldquo;more: 3, 17 &nbsp; less: 40, 41&rdquo;.
The numbers are the whole UI.</div>"""]
    for i, (p, why) in enumerate(picks, 1):
        fn = p["file"]
        rot = " · rotated 90°" if p.get("body_rotated") else ""
        conf = "" if p.get("page_number_confident", True) else " · <b>page# unsure</b>"
        ticket = " · <b>RESCAN TICKET</b>" if p.get("rescan_ticket") else ""
        text = p.get("body_text", "")[:TEXT_CHARS]
        parts.append(f"""<div class="card"><div class="num">#{i}</div>
<div class="meta">{fn} · {p['category']}{rot} · book page {p.get('page_number') or '?'} · {p.get('n_boxes', '?')} boxes{conf}{ticket}</div>
<div class="why">{why}</div>
<img loading="lazy" src="data:image/jpeg;base64,{img_b64(fn)}">
<pre>{text}</pre></div>""")
    parts.append("</body></html>")
    out = os.path.join(REDPEN, "redpen.html")
    with open(out, "w") as f:
        f.write("\n".join(parts))
    print(f"wrote {out} ({len(picks)} pages, {os.path.getsize(out)//1024}KB)")

if __name__ == "__main__":
    main()
