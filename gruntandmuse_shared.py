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
