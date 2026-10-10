"""
GruntAndMuse shared pipeline utilities.
Import in any pipeline: from gruntandmuse_shared import friendly_errors, progress, ...

Principles baked in:
- Friendly errors: no raw tracebacks for user errors, no disappearing windows
- Privacy by architecture: no telemetry, no phoning home, local-only
- Plain-English output for non-technical users
"""

import sys
import traceback
import functools


def friendly_errors(func):
    """Decorator: catch errors gracefully, explain what happened and what to do next.
    Never show a raw traceback for user errors. Log technical details to stderr
    for bug reports, but lead with the human explanation."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError as e:
            print(f"\n❌ Couldn't find a file: {e.filename}", file=sys.stderr)
            print("   Check the path and try again.", file=sys.stderr)
            sys.exit(1)
        except PermissionError as e:
            print(f"\n❌ Permission denied: {e.filename or ''}", file=sys.stderr)
            print("   Try running with the right permissions or pick a different location.", file=sys.stderr)
            sys.exit(1)
        except KeyboardInterrupt:
            print("\n\nCancelled. Nothing was changed.", file=sys.stderr)
            sys.exit(130)
        except ValueError as e:
            print(f"\n❌ Bad input: {e}", file=sys.stderr)
            print("   Check your arguments and try again. Use --help for usage.", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Something went wrong: {e}", file=sys.stderr)
            print("   If this keeps happening, report it at:", file=sys.stderr)
            print("   https://github.com/GruntAndMuse", file=sys.stderr)
            print("\n   Technical details (for the bug report):", file=sys.stderr)
            traceback.print_exc()
            sys.exit(1)
    return wrapper


class Progress:
    """Simple progress reporter. No dependencies, works everywhere."""

    def __init__(self, total, label="Working"):
        self.total = total
        self.done = 0
        self.label = label

    def tick(self, msg=""):
        self.done += 1
        pct = int(100 * self.done / self.total) if self.total else 0
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        line = f"\r{self.label}: [{bar}] {pct}% ({self.done}/{self.total})"
        if msg:
            line += f" — {msg}"
        print(line, end="", flush=True)

    def finish(self, msg="Done!"):
        print(f"\n✅ {msg}")


def confirm(prompt, default=False):
    """Plain-English yes/no. Returns bool."""
    suffix = " [Y/n]: " if default else " [y/N]: "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def header(title):
    """Print a clear section header."""
    print(f"\n{'=' * 50}\n  {title}\n{'=' * 50}")


def check_no_network():
    """Assert this pipeline makes no network calls. Call in tests, not production.
    Patches socket to raise on any connection attempt."""
    import socket
    _orig = socket.socket.connect

    def _blocked(self, *args, **kwargs):
        raise RuntimeError(
            "Network access blocked: this pipeline must work fully offline. "
            "If you need network, that's an architecture decision, not an accident."
        )
    socket.socket.connect = _blocked
    return lambda: setattr(socket.socket, "connect", _orig)  # call to restore


# ---------------------------------------------------------------------------
# Security guards — every pipeline gets these free.
# Born from the document-ocr gauntlet (2026-10-10): 23 findings across
# self-review + DeepSeek + Gemini. Import, don't reimplement.
# ---------------------------------------------------------------------------

import json
import os


def safe_filename(fn):
    """Reject path traversal and NUL bytes in input-supplied filenames.

    Returns the filename if safe, None if it must be rejected.
    Blocks: /, \\, .., embedded NUL. Does NOT resolve symlinks —
    use safe_join() when the file will actually be opened.
    """
    if not isinstance(fn, str) or not fn:
        return None
    if "/" in fn or "\\" in fn or ".." in fn or "\x00" in fn:
        return None
    return fn


def safe_join(base_dir, fn):
    """Join a filename to a base dir, resolving symlinks and verifying
    the result stays inside base_dir. Returns the real path, or None
    if the file escapes (symlink attack, traversal that slipped through).
    """
    fn = safe_filename(fn)
    if not fn:
        return None
    real = os.path.realpath(os.path.join(base_dir, fn))
    base = os.path.join(os.path.realpath(base_dir), "")
    if not real.startswith(base):
        return None
    return real


def atomic_write_bytes(path, data):
    """Write bytes atomically: tmp file + os.replace. A crash mid-write
    never leaves a partial file at the destination."""
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def atomic_write_text(path, text, encoding="utf-8"):
    """Write text atomically: tmp file + os.replace."""
    atomic_write_bytes(path, text.encode(encoding))


def load_json_loud(path):
    """Load a JSON file, failing LOUDLY on corruption.

    A corrupt JSON must never be silently skipped — a skipped page
    JSON means a silently missing page in the output. Raises
    ValueError with the file path on parse failure.
    """
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"corrupt JSON {path}: {e}")
    except OSError as e:
        raise ValueError(f"cannot read {path}: {e}")


def guard_image_file(path, max_bytes=100 * 1024 * 1024):
    """Pre-read guard against decompression bombs. Check file size
    BEFORE handing the file to an image decoder that will allocate
    memory for the full pixel dimensions."""
    size = os.path.getsize(path)
    if size > max_bytes:
        raise ValueError(
            f"image {path} is {size // 1024 // 1024}MB, "
            f"over the {max_bytes // 1024 // 1024}MB cap")
    return size


def guard_image_dims(img, max_pixels=12000 * 12000, name="image"):
    """Post-decode guard: reject absurd pixel dimensions even when the
    compressed file was small (decompression bomb). Call after imread."""
    h, w = img.shape[:2]
    if h * w > max_pixels:
        raise ValueError(
            f"{name} is {w}x{h} pixels, over the cap "
            f"({int(max_pixels ** 0.5)}x{int(max_pixels ** 0.5)})")
    return h, w


def validate_sample_arg(n, name="--sample"):
    """Sample counts must be >= 1. Zero divides by zero; negative
    silently disables every sampled gate while still printing PASS."""
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"{name} must be 1 or more, got {n!r}")
    return n


def validate_fraction(value, name, lo=0.0, hi=1.0):
    """Config fractions must be in range at LOAD time, not when
    OpenCV segfaults on a 0-height array three steps later."""
    if not isinstance(value, (int, float)) or not (lo <= value < hi):
        raise ValueError(
            f"config {name} must be in [{lo}, {hi}), got {value!r}")
    return value
