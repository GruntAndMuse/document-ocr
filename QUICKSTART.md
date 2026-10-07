# QUICKSTART

Turn your scanned pages into a searchable PDF. No experience assumed.

> **Privacy first:** Your files never leave your computer. No account, no
> cloud, no telemetry. See [SECURITY.md](SECURITY.md).

## What you need

1. **Python 3.10 or newer.** Check: `python3 --version`
   - Download from [python.org](https://www.python.org/downloads/) if needed
2. **Your page scans** as JPG or PNG files, one per page
3. About **2 GB free disk** (for the OCR model, downloaded once automatically)

That's it. No system packages, no Docker, no admin rights needed.

## Step 1: Set up (once)

```bash
# Download doc-ocr (or clone the repo)
# Then:

# Create a virtual environment (isolates dependencies)
python3 -m venv venv

# Activate it
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate          # Windows

# Install dependencies (takes a few minutes the first time)
pip install -r scripts/requirements.txt
```

You should see packages installing. When it finishes, you're set up.

## Step 2: Organize your pages

Put your page scans in a folder. Name them clearly:

```
my-scans/
    page001.jpg
    page002.jpg
    page003.jpg
```

Create a CSV file listing each page and its type. Call it `pages.csv`:

```csv
filename,category,chapter
page001.jpg,text,ch1
page002.jpg,text,ch1
page003.jpg,table,ch1
```

**Categories** tell the pipeline how to process each page:

| Category | Use for |
|---|---|
| `text` | Normal text pages |
| `table` | Tables, pinouts, structured data |
| `rotated` | Landscape content in portrait pages (diagrams) |
| `diagram` | Figures with minimal text |
| `blank` | Blank or near-blank pages (header only) |
| `damaged` | Unreadable pages (logged for rescan, not processed) |

Not sure? Use `text` — it's the safest default.

## Step 3: Run OCR

```bash
./doc-ocr ocr --pages my-scans --sample pages.csv --out output/
```

You'll see progress like:

```
doc-ocr ocr: using 'default' profile
[1/3] page001.jpg (text)
[2/3] page002.jpg (text)
[3/3] page003.jpg (table)
doc-ocr ocr: done
```

This creates one `.json` file per page in `output/`. Each JSON has the
recognized text, bounding boxes, confidence scores, and page numbers.

**If you have service manual pages**, use the tuned profile:

```bash
./doc-ocr ocr --profile service-manual --pages my-scans --sample pages.csv
```

## Step 4: Build the searchable PDF

```bash
./doc-ocr build --pages my-scans -o manual.pdf output/*.json
```

Output:

```
doc-ocr build: wrote manual.pdf
```

Open `manual.pdf` — try searching (Ctrl+F) for a word you can see on the
page. Try selecting text. It should highlight exactly where the words are.

## Step 5: QC check (don't skip this)

Pick a page and verify the invisible text actually aligns:

```bash
./doc-ocr check manual.pdf 1 my-scans/page001.jpg qc.png
```

Open `qc.png`. You'll see blue rectangles drawn over the scan — one per
text span. **Blue must hug the black text.** Gaps on real text or overhang
onto empty space means the placement is off.

Run this on at least one page of each category before trusting the output.

For a full automated pass, run the QC gates — the production audit
(bbox alignment, file integrity, dewarped↔original parity, text encoding,
duplicate/missing pages) as build-failing checks:

```bash
./doc-ocr qc --pdf manual.pdf --json-dir output/
```

Or bake it into the build so a gate failure fails the build:

```bash
./doc-ocr build -o manual.pdf --qc output/*.json
```

## Common problems

**"No module named 'cv2'"**
→ You forgot to activate the venv. Run `source venv/bin/activate` first.

**"unknown profile"**
→ Check the name. Available: `default`, `service-manual`.
   List them: `ls profiles/`

**"no per-page OCR JSON found"**
→ You passed the report JSON instead of page JSONs. The `output/` folder
   has both — the page files are named like `page001.jpg.json`.

**OCR is slow**
→ Normal. ~10-30 seconds per page on a modern CPU. The ONNX model runs
   on CPU by default. Large pages (300+ DPI) take longer.

**Page numbers not found**
→ Check the header strip: the top 10% of the page is scanned for page
   numbers. If your pages have headers lower than that, increase
   `strip_fraction` in `config/pipeline.yaml`.

## What's next

- [REQUIREMENTS.md](REQUIREMENTS.md) — detailed system requirements
- [ABOUT.md](ABOUT.md) — why this exists
- Tune the config for your documents — see `config/pipeline.yaml`
- Build a domain wordlist — see `profiles/service-manual/README.md`
