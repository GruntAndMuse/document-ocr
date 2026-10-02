#!/usr/bin/env python3
"""Rebuild demo PDFs after pipeline/placement changes.
Usage: venv/bin/python rebuild_demos.py
Builds: redpen/searchable-demo.pdf (3pp, full-res) and
        redpen/redpen-searchable.pdf (48pp, half-res phone-friendly)
"""
import json, os, sys, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "mdp", os.path.join(os.path.dirname(os.path.abspath(__file__)), "make_demo_pdf.py"))
mdp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mdp)
import fitz, cv2

BASE = os.path.dirname(os.path.abspath(__file__))

# 3-page demo, full resolution
demo3 = ["output/GMT00ST_1_BRAKE_00007.jpg.json",
         "output/GMT00ST_1_BRAKE_00012.jpg.json",
         "output/GMT00ST_1_BRAKE_00005.jpg.json"]
doc = fitz.open()
for rel in demo3:
    pj = json.load(open(os.path.join(BASE, rel)))
    mdp.add_page(doc, pj)
doc.save(os.path.join(BASE, "redpen/searchable-demo.pdf"))
print("searchable-demo.pdf:", round(os.path.getsize(
    os.path.join(BASE, "redpen/searchable-demo.pdf")) / 1e6, 1), "MB")

# 48-page red-pen, half-res
files = json.load(open(os.path.join(BASE, "redpen/redpen48.json")))
S = 0.5
doc = fitz.open()
for f in files:
    pj = copy.deepcopy(json.load(open(os.path.join(BASE, "output", f + ".json"))))
    for key in ("boxes", "header_boxes"):
        for b in pj.get(key, []):
            b["box"] = [[x * S, y * S] for x, y in b["box"]]
    img = cv2.imread(os.path.join(BASE, "samples/pages", f))
    img = cv2.resize(img, None, fx=S, fy=S, interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 72])
    page = doc.new_page(width=w, height=h)
    page.insert_image(page.rect, stream=buf.tobytes())
    for key in ("boxes", "header_boxes"):
        for b in pj.get(key, []):
            mdp.place_box_text(page, b)
doc.save(os.path.join(BASE, "redpen/redpen-searchable.pdf"))
print("redpen-searchable.pdf:", round(os.path.getsize(
    os.path.join(BASE, "redpen/redpen-searchable.pdf")) / 1e6, 1), "MB,",
    len(doc), "pages")
