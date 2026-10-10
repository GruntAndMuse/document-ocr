# Pipeline Security Checklist

Run this before any pipeline ships. Born from the document-ocr gauntlet
(2026-10-10): 23 findings across self-review + DeepSeek + Gemini.

Most checks are one import away: `from gruntandmuse_shared import ...`

## Filenames (every input-supplied name)
- [ ] `safe_filename()` — rejects `/`, `\`, `..`, NUL bytes
- [ ] `safe_join()` — resolves symlinks, verifies containment in base dir
- [ ] No `os.path.join()` on untrusted names without the above

## Writes (every output file)
- [ ] Atomic: tmp file + `os.replace()` — never write directly to the destination
- [ ] Tmp names include PID (`f"{path}.tmp-{os.getpid()}"`) — no shared global tmp races
- [ ] `atomic_write_bytes()` / `atomic_write_text()` from shared module

## JSON (every file read)
- [ ] `load_json_loud()` — corrupt JSON fails LOUDLY, never silently skipped
- [ ] Type-check loaded structures: `isinstance(d, dict)`, `isinstance(boxes, list)`
- [ ] Guard against `null` fields: `pj.get("boxes")` returns None when key exists with null value
- [ ] Validate inner shapes before unpacking (box = 4 points, each point = 2 numbers)

## Images (every file decoded)
- [ ] `guard_image_file()` — size cap BEFORE the decoder allocates memory
- [ ] `guard_image_dims()` — pixel cap AFTER decode (decompression bombs)
- [ ] None-check on every decode result before touching `.shape`

## Subprocesses
- [ ] Argument lists, never `shell=True`, never string concatenation
- [ ] No ARG_MAX risk: pass `--json-dir`, not thousands of expanded paths

## Config
- [ ] `yaml.safe_load()` — never `yaml.load()`
- [ ] `validate_fraction()` / range-check every numeric config at LOAD time
- [ ] Bad config raises a clean error, not a segfault three steps later

## QC gates
- [ ] Gates fail CLOSED — a gate that can't run is a failure, not a skip
- [ ] `validate_sample_arg()` — sample counts >= 1 (0 = crash, negative = silent bypass)
- [ ] Empty inputs fail the gate, don't crash it
- [ ] The gate was TESTED against a known-bad input, not just written

## Adversarial test fixtures (throw these at every pipeline)
- [ ] Traversal names: `../evil`, `..\\evil`, `/abs/path`, `a\x00.png`
- [ ] Symlink in input dir pointing outside
- [ ] Corrupt JSON: truncated, zero-byte, `[1,2,3]`, `{"boxes": null}`
- [ ] Malformed boxes: 3 points, 5 points, strings, nested wrong
- [ ] Huge-dimension image (small file, absurd pixels)
- [ ] Empty input set / empty PDF
- [ ] Config with out-of-range values

## Process (Dennis's standing policy)
- [ ] Self-review FIRST — apply every pattern on this list before external review
- [ ] Multi-reviewer adversarial gauntlet (not just one model)
- [ ] Every finding fixed, then INDEPENDENTLY VERIFIED (not just re-read)
- [ ] Every security fix gets a regression test
- [ ] Never fix-and-ship
