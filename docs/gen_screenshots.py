#!/usr/bin/env python3
"""Generate annotated screenshots for doc-ocr docs from real output.

Creates terminal-style screenshots with red-circle annotations.
Regenerate when the CLI output changes: python3 docs/gen_screenshots.py
"""
import os
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)

# WHY: DejaVu is available on most Linux; fall back to default bitmap font.
def get_font(size=18):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    ]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

BG = (30, 30, 30)       # terminal dark
FG = (220, 220, 220)    # terminal text
GREEN = (80, 200, 120)  # success
YELLOW = (220, 180, 80) # prompt
RED = (255, 80, 80)     # annotation circles
BLUE = (100, 150, 255)  # annotation text bg

def make_terminal(lines, annotations, filename, width=900):
    """lines: list of (text, color). annotations: list of (y_line, x_start, x_end, label)."""
    font = get_font(18)
    lh = 28  # line height
    pad = 20
    # measure
    ascent, descent = font.getmetrics()
    char_w = font.getlength("M")
    height = pad * 2 + lh * len(lines) + 60  # extra for labels
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    for i, (text, color) in enumerate(lines):
        y = pad + i * lh
        d.text((pad, y), text, font=font, fill=color)
    # annotations: red ellipse around (x_start..x_end) on line y_line, label below
    for (y_line, x_start, x_end, label) in annotations:
        y = pad + y_line * lh
        x0 = pad + x_start * char_w
        x1 = pad + x_end * char_w
        d.ellipse([x0 - 8, y - 6, x1 + 8, y + lh - 4], outline=RED, width=3)
        # label
        lx = x0
        ly = y + lh + 2
        d.text((lx, ly), label, font=get_font(15), fill=RED)
    img.save(os.path.join(OUT, filename))
    print(f"  wrote {filename} ({width}x{height})")

# Screenshot 1: ocr command
make_terminal(
    [
        ("$ ./doc-ocr ocr --profile service-manual --pages my-scans --sample pages.csv", YELLOW),
        ("doc-ocr ocr: using 'service-manual' profile", FG),
        ("[1/6] page001.jpg (text)", FG),
        ("[2/6] page002.jpg (blank)", FG),
        ("[3/6] page003.jpg (troubleshooting)", FG),
        ("[4/6] page004.jpg (diagram)", FG),
        ("[5/6] page005.jpg (schematic)", FG),
        ("[6/6] page006.jpg (connector_pinout)", FG),
        ("doc-ocr ocr: done", GREEN),
    ],
    [(0, 4, 13, "one command runs the whole OCR stage"),
     (8, 0, 18, "clear completion signal")],
    "01-ocr-command.png",
)

# Screenshot 2: build command
make_terminal(
    [
        ("$ ./doc-ocr build --pages my-scans -o manual.pdf output/*.json", YELLOW),
        ("doc-ocr build: skipping 1 non-page JSON (report/progress files)", FG),
        ("wrote manual.pdf (6699KB, 6 pages, skipped 0)", FG),
        ("doc-ocr build: wrote manual.pdf", GREEN),
    ],
    [(1, 0, 50, "smart filtering — report JSONs don't crash the build"),
     (3, 0, 30, "your searchable PDF is ready")],
    "02-build-command.png",
)

# Screenshot 3: check command
make_terminal(
    [
        ("$ ./doc-ocr check manual.pdf 1 my-scans/page001.jpg qc.png", YELLOW),
        ("179 spans drawn -> qc.png", FG),
        ("doc-ocr check: wrote qc.png", GREEN),
        ("open it: blue rectangles must hug the black text.", FG),
        ("gaps on real text or overhang onto empty space = placement bug.", FG),
    ],
    [(3, 0, 55, "tells you exactly what to look for"),
     (4, 0, 60, "not just 'done' — actionable QC guidance")],
    "03-check-command.png",
)

# Screenshot 4: error handling
make_terminal(
    [
        ("$ ./doc-ocr ocr --pages wrong-folder --sample pages.csv", YELLOW),
        ("error: pages directory not found: wrong-folder", RED),
        ("hint: point --pages at the folder holding your page scans", FG),
    ],
    [(1, 0, 45, "no traceback — plain English"),
     (2, 0, 55, "tells you how to fix it")],
    "04-friendly-error.png",
)

print("done")
