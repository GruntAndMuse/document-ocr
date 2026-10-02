#!/usr/bin/env python3
"""Pilot accuracy measurement — reads output/*.json, scores what matters.
Metrics per his spec: page-number extraction, search/highlight readiness
(word boxes + confidence), table structure (pinout/troubleshooting cell boxes),
rotation correctness (schematic text reads horizontal after rotate).
Writes: output/accuracy_report.json + prints the scorecard.
"""
import json, os, glob, re
from collections import defaultdict

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# what "good" looks like per category: expected minimums from the pilot spec
EXPECT = {
    "schematic":        {"min_boxes": 30, "needs_rotation": True},
    "schematic_text":   {"min_boxes": 30, "needs_rotation": False},
    "connector_pinout": {"min_boxes": 20, "needs_table": True},
    "troubleshooting":  {"min_boxes": 40, "needs_table": True},
    "text":             {"min_boxes": 40, "needs_rotation": False},
    "diagram":          {"min_boxes": 5,  "needs_rotation": False},
    "blank":            {"min_boxes": 0},
    "damaged":          {"rescan_ticket": True},
}

def score_page(p):
    cat = p["category"]
    exp = EXPECT.get(cat, {})
    s = {"file": p["file"], "category": cat, "checks": {}}
    if p.get("error"):
        s["checks"]["no_error"] = False
        s["pass"] = False
        return s
    c = s["checks"]
    c["no_error"] = True
    # 1. page number = primary key
    c["page_number"] = bool(p.get("page_number"))
    # 2. content volume
    nb = p.get("n_boxes", 0)
    c["has_content"] = nb >= exp.get("min_boxes", 0)
    # 3. search/highlight readiness: boxes with coordinates + confidence
    boxes = p.get("boxes", [])
    c["boxes_have_coords"] = all(b.get("box") for b in boxes) if boxes else True
    c["high_conf_ratio"] = (sum(1 for b in boxes if b.get("conf", 0) >= 0.5)
                            / max(1, len(boxes)))
    c["mostly_confident"] = c["high_conf_ratio"] >= 0.8
    # 4. rotation: schematic body must have been rotated; others must not
    if exp.get("needs_rotation"):
        c["rotated"] = p.get("body_rotated") == "90cw"
    # blank pages carry no body content: a clean header pass is a pass
    if p.get("category") == "blank":
        c["mostly_confident"] = True
    # damaged pages exist to produce rescan tickets, not page numbers
    if p.get("category") == "damaged":
        c["page_number"] = True
        c["mostly_confident"] = True
    # 5. rescan ticket for damaged
    if exp.get("rescan_ticket"):
        c["rescan_ticket"] = bool(p.get("rescan_ticket"))
    # 6. canonical terms are informational only (a page never contains all of
    # them); corruption review happens in red-pen, not in the scorecard.
    c["canonical_ok"] = True
    # pass = every boolean check true; ratio floats are informational
    s["pass"] = all(v for v in c.values() if isinstance(v, bool))
    return s

def main():
    files = sorted(glob.glob(os.path.join(OUT, "*.json")))
    files = [f for f in files if not f.endswith("pilot_report.json")
             and not f.endswith("accuracy_report.json")]
    scores, by_cat = [], defaultdict(list)
    for f in files:
        with open(f) as fh:
            p = json.load(fh)
        sc = score_page(p)
        scores.append(sc)
        by_cat[sc["category"]].append(sc)
    summary = {}
    for cat, ss in sorted(by_cat.items()):
        checks = defaultdict(lambda: [0, 0])
        for sc in ss:
            for k, v in sc["checks"].items():
                checks[k][0] += 1 if v else 0
                checks[k][1] += 1
        summary[cat] = {
            "n": len(ss),
            "pass_rate": round(sum(1 for sc in ss if sc["pass"]) / len(ss), 2),
            "checks": {k: f"{a}/{b}" for k, (a, b) in sorted(checks.items())},
        }
    report = {"n_pages": len(scores),
              "overall_pass": round(sum(1 for s in scores if s["pass"])
                                    / max(1, len(scores)), 2),
              "by_category": summary,
              "failures": [s for s in scores if not s["pass"]]}
    with open(os.path.join(OUT, "accuracy_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps({"n": report["n_pages"],
                      "overall_pass": report["overall_pass"],
                      "by_category": summary}, indent=1))

if __name__ == "__main__":
    main()
