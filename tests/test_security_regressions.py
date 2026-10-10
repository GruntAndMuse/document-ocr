#!/usr/bin/env python3
"""Security regression tests: every finding from the 2026-10-10 gauntlet
(self-review + DeepSeek + Gemini, 23 findings) gets a test that FAILS if
the vulnerability comes back.

Uses the adversarial fixtures from SECURITY_CHECKLIST.md.

Run:  python tests/test_security_regressions.py
Exit 0 = all pass. Exit 1 = any failure. No pytest needed — plain asserts
with PASS/FAIL lines, same style as tests/test_qc_gates.py.
"""
import importlib.util
import json
import os
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))          # tests/
ROOT = os.path.dirname(BASE)                              # document-ocr/
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, ROOT)

import gruntandmuse_shared as G  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PIPELINE = _load("pipeline")
MDP = _load("make_demo_pdf")
BDS = _load("build_dewarped_searchable")
QC = _load("qc_gates")

PASS = []
FAIL = []


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print(f"  PASS {name}")
    except AssertionError as e:
        FAIL.append(name)
        print(f"  FAIL {name}: {e}")
    except Exception as e:
        FAIL.append(name)
        print(f"  FAIL {name}: unexpected {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# 1. Path traversal filenames rejected
# ---------------------------------------------------------------------------

def t_traversal_dotdot():
    assert G.safe_filename("../evil.png") is None
    assert G.safe_filename("a/../../evil.png") is None


def t_traversal_backslash():
    assert G.safe_filename("..\\evil.png") is None
    assert G.safe_filename("a\\..\\evil.png") is None


def t_traversal_absolute():
    assert G.safe_filename("/etc/passwd") is None
    assert G.safe_filename("C:\\Windows\\evil.png") is None


def t_traversal_nul():
    assert G.safe_filename("a\x00.png") is None
    assert G.safe_filename("\x00") is None


def t_traversal_valid_passes():
    assert G.safe_filename("page001.png") == "page001.png"
    assert G.safe_filename("scan-2024_01.png") == "scan-2024_01.png"


def t_traversal_empty_rejected():
    assert G.safe_filename("") is None
    assert G.safe_filename(None) is None
    assert G.safe_filename(123) is None


# ---------------------------------------------------------------------------
# 2. Symlink escaping the pages dir rejected
# ---------------------------------------------------------------------------

def t_symlink_escape():
    with tempfile.TemporaryDirectory() as tmp:
        pages = os.path.join(tmp, "pages")
        outside = os.path.join(tmp, "outside")
        os.makedirs(pages)
        os.makedirs(outside)
        secret = os.path.join(outside, "secret.png")
        with open(secret, "wb") as f:
            f.write(b"fake")
        link = os.path.join(pages, "link.png")
        os.symlink(secret, link)
        # safe_join must resolve the symlink and refuse
        assert G.safe_join(pages, "link.png") is None, \
            "symlink escape not blocked"


def t_symlink_valid_passes():
    with tempfile.TemporaryDirectory() as tmp:
        pages = os.path.join(tmp, "pages")
        os.makedirs(pages)
        real = os.path.join(pages, "real.png")
        with open(real, "wb") as f:
            f.write(b"fake")
        assert G.safe_join(pages, "real.png") == os.path.realpath(real)


# ---------------------------------------------------------------------------
# 3. Atomic writes (tmp + os.replace in all writers)
# ---------------------------------------------------------------------------

def _has_atomic_pattern(path):
    src = open(path).read()
    return "os.replace(" in src and ".tmp" in src


def t_atomic_pipeline():
    assert _has_atomic_pattern(os.path.join(SCRIPTS, "pipeline.py")), \
        "pipeline.py missing tmp+os.replace"


def t_atomic_build_dewarped():
    assert _has_atomic_pattern(
        os.path.join(SCRIPTS, "build_dewarped_searchable.py"))


def t_atomic_make_demo():
    assert _has_atomic_pattern(os.path.join(SCRIPTS, "make_demo_pdf.py")), \
        "make_demo_pdf.py missing atomic save (Gemini G1)"


def t_atomic_write_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "out.json")
        G.atomic_write_text(p, '{"a": 1}')
        assert json.load(open(p)) == {"a": 1}
        # no stray tmp files left behind
        assert os.listdir(tmp) == ["out.json"], os.listdir(tmp)


# ---------------------------------------------------------------------------
# 4. Corrupt JSON fails loudly (no silent skip)
# ---------------------------------------------------------------------------

def t_corrupt_json_loud():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "bad.json")
        with open(p, "w") as f:
            f.write('{"file": "a.png", "boxes": [')  # truncated
        try:
            G.load_json_loud(p)
            raise AssertionError("corrupt JSON did not raise")
        except ValueError as e:
            assert "corrupt JSON" in str(e)


def t_zero_byte_json_loud():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "empty.json")
        open(p, "w").close()
        try:
            G.load_json_loud(p)
            raise AssertionError("zero-byte JSON did not raise")
        except ValueError:
            pass


def t_valid_json_loads():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "ok.json")
        with open(p, "w") as f:
            json.dump({"file": "a.png"}, f)
        assert G.load_json_loud(p) == {"file": "a.png"}


# ---------------------------------------------------------------------------
# 5. Null/malformed boxes don't crash builders
# ---------------------------------------------------------------------------

def t_null_boxes_map():
    # build_dewarped_searchable.map_boxes with None
    assert BDS.map_boxes(None, [0] * 10) == []
    assert BDS.map_boxes("notalist", [0] * 10) == []


def t_malformed_box_entries():
    # entries that aren't dicts are skipped, not crashed on
    boxes = ["x", 5, {"box": 5}, {"box": [[1, 2, 3]]}, None]
    result = BDS.map_boxes(boxes, [0] * 10)
    assert result == [], f"expected [], got {result}"


def t_place_box_text_malformed():
    # make_demo_pdf.place_box_text must not raise on garbage
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    for bad in [{"box": "x"}, {"box": [[1]]}, {"box": [[1, 2]] * 3},
                {"box": [[1, 2]] * 4, "text": 123},  # missing box
                "notadict"]:
        if isinstance(bad, dict):
            MDP.place_box_text(page, bad)  # must not raise
    doc.close()


def t_json_boxes_malformed():
    # qc_gates.json_boxes with wrong types
    assert QC.json_boxes({"boxes": 5}) == []
    assert QC.json_boxes({"boxes": ["x", None, 5]}) == []
    assert QC.json_boxes({"boxes": None}) == []
    good = {"boxes": [{"box": [[0, 0], [1, 0], [1, 1], [0, 1]],
                       "text": "hi"}]}
    assert len(QC.json_boxes(good)) == 1


# ---------------------------------------------------------------------------
# 6. Image dimension caps enforced
# ---------------------------------------------------------------------------

def t_guard_dims_rejects_huge():
    import numpy as np
    huge = np.zeros((20000, 20000, 3), dtype=np.uint8)  # 400MP
    try:
        G.guard_image_dims(huge, max_pixels=12000 * 12000)
        raise AssertionError("huge image not rejected")
    except ValueError as e:
        assert "over the cap" in str(e)


def t_guard_dims_accepts_normal():
    import numpy as np
    normal = np.zeros((1000, 800, 3), dtype=np.uint8)
    h, w = G.guard_image_dims(normal)
    assert (h, w) == (1000, 800)


def t_guard_file_rejects_big():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "big.bin")
        with open(p, "wb") as f:
            f.write(b"\x00" * 1024)
        try:
            G.guard_image_file(p, max_bytes=512)
            raise AssertionError("oversize file not rejected")
        except ValueError as e:
            assert "over the" in str(e)


# ---------------------------------------------------------------------------
# 7. --sample 0 and negative rejected
# ---------------------------------------------------------------------------

def t_sample_zero_rejected():
    try:
        QC.sample_indices(100, 0)
        raise AssertionError("--sample 0 did not raise")
    except ValueError:
        pass
    try:
        G.validate_sample_arg(0)
        raise AssertionError("validate_sample_arg(0) did not raise")
    except ValueError:
        pass


def t_sample_negative_rejected():
    try:
        QC.sample_indices(100, -1)
        raise AssertionError("--sample -1 did not raise")
    except ValueError:
        pass


def t_sample_valid():
    assert QC.sample_indices(10, 3) == [0, 3, 6]
    assert G.validate_sample_arg(5) == 5


# ---------------------------------------------------------------------------
# 8. Empty PDF fails QC gate cleanly (no crash)
# ---------------------------------------------------------------------------

def t_empty_pdf_gate():
    # fitz refuses to save a 0-page PDF, so mock the doc object —
    # the gate must handle len(doc) == 0 without IndexError.
    import fitz
    real_open = fitz.open

    class EmptyDoc:
        def __len__(self):
            return 0

        def close(self):
            pass

    fitz.open = lambda *a, **k: EmptyDoc()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "empty.pdf")
            open(p, "wb").write(b"%PDF-1.4 fake")
            r = QC.gate_file_integrity(p, expected_pages=None)
    finally:
        fitz.open = real_open
    assert r["passed"] is False, "empty PDF should fail the gate"
    assert "no pages" in r["detail"].lower(), r["detail"]


# ---------------------------------------------------------------------------
# 9. Wordlist replacement doesn't interpret regex backreferences
# ---------------------------------------------------------------------------

def t_wordlist_no_backref():
    # A wordlist entry like x>\1 must not raise re.error
    fixes = {"x": "\\1", "y": "\\g<bad>"}
    text = PIPELINE.apply_wordlist("x y z", fixes)
    assert text == "\\1 \\g<bad> z", f"got {text!r}"


def t_wordlist_normal():
    fixes = {"teh": "the"}
    assert PIPELINE.apply_wordlist("teh cat", fixes) == "the cat"


def t_wordlist_word_boundary():
    # camp -> cAMP corruption class must stay fixed
    fixes = {"amp": "AMP"}
    assert PIPELINE.apply_wordlist("camp", fixes) == "camp"


# ---------------------------------------------------------------------------
# 10. Config fraction validation at load time
# ---------------------------------------------------------------------------

def t_fraction_valid():
    assert G.validate_fraction(0.15, "strip_fraction") == 0.15
    assert G.validate_fraction(0, "x") == 0


def t_fraction_rejected():
    for bad in (1.0, 1.5, -0.1, "x", None):
        try:
            G.validate_fraction(bad, "strip_fraction")
            raise AssertionError(f"{bad!r} not rejected")
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# 11. Page number 0 not dropped from gap detection
# ---------------------------------------------------------------------------

def t_page_zero_kept():
    # _page_number_gaps must not silently drop page 0 (DeepSeek W7).
    # Returns (gaps, unparseable); pages 0 and 2 must report "missing 1".
    gaps, unparseable = QC._page_number_gaps(
        [{"page_number": 0}, {"page_number": 2}])
    assert any("1" in g for g in gaps), f"gap at 1 not detected: {gaps}"


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

TESTS = [
    t_traversal_dotdot, t_traversal_backslash, t_traversal_absolute,
    t_traversal_nul, t_traversal_valid_passes, t_traversal_empty_rejected,
    t_symlink_escape, t_symlink_valid_passes,
    t_atomic_pipeline, t_atomic_build_dewarped, t_atomic_make_demo,
    t_atomic_write_roundtrip,
    t_corrupt_json_loud, t_zero_byte_json_loud, t_valid_json_loads,
    t_null_boxes_map, t_malformed_box_entries, t_place_box_text_malformed,
    t_json_boxes_malformed,
    t_guard_dims_rejects_huge, t_guard_dims_accepts_normal,
    t_guard_file_rejects_big,
    t_sample_zero_rejected, t_sample_negative_rejected, t_sample_valid,
    t_empty_pdf_gate,
    t_wordlist_no_backref, t_wordlist_normal, t_wordlist_word_boundary,
    t_fraction_valid, t_fraction_rejected,
    t_page_zero_kept,
]


def main():
    print(f"Security regression tests ({len(TESTS)} cases)")
    print("-" * 60)
    for t in TESTS:
        check(t.__name__, t)
    print("-" * 60)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
