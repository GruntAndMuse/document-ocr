# Why This Exists

GruntAndMuse is a human and an AI building things together in public.
doc-ocr is our second release.

## The problem

Dennis is rewiring a 2000 Chevy S10 — ground-up build, V6 swap, needs to
be California-smog legal. The factory service manuals are ~5,700 scanned
pages. Paper scans. Not searchable. Finding one wire in 5,700 unsearchable
pages is a special kind of hell.

So we built a pipeline: turn the scans into searchable PDFs where you can
Ctrl+F for a wire color, click a page number, select text exactly where it
sits on the page. The pilot hit 100/100 pages, zero errors.

Then we realized: everyone with a stack of scanned documents has this
problem. Service manuals, textbooks, archival records, old magazines.
The pipeline doesn't care what the pages are — it just needs to know what
*type* each page is. So we made it generic, with the service manual tuning
as the first profile.

## The mechanic library vision

Dennis tows for a living. His tow yard sees a rotating cast of vehicles —
S10s, beaters, parts cars. Each one is a potential reference: scan the
relevant manual sections, OCR them, build a searchable library. The truck
in the yard today is the answer to the question in the shop tomorrow.

That's the bigger picture: a community-built, searchable library of
technical documentation. Not pirated — manuals you own, processed for
your own use, with the pipeline shared so anyone can do the same.

## How we work

- **Pilot before scale.** Every change is proven on a small sample first.
- **One variable per test.** Change one knob, measure, then move on.
- **Document failures.** Dead ends are recorded, not deleted.
- **Verify, don't assume.** If we say it works, we tested it.
- **Slow is smooth, smooth is fast.** Rushing produces redo work.
- **Privacy is a core human right.** Local only. No telemetry. No cloud.
  Your documents are yours.

## Who's behind this

Dennis is a medically retired Army infantryman (grenadier, breacher) who
builds things — a 2000 Chevy S10 from the ground up, 3D printer upgrades,
FOSS pipelines. He did physical security in the Army; the software
inherits the mindset.

Muninn is an AI — a raven, sharp-eyed and a little mischievous. Named by
Dennis after Odin's raven of memory. Does the code, the docs, the testing.

We're figuring out how a visual human and a text AI collaborate. The
process is part of what we're sharing.

## What's next

See [ROADMAP.md](ROADMAP.md). Short version: generic profiles for more
document types, better table handling, more languages, and the searchable
library vision.

Fork it. Break it. Make it better. That's the point.
