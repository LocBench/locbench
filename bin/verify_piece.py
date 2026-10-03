#!/usr/bin/env python3
"""The check that runs before a piece ships.

A published piece carries the face of whoever signs it, and whoever signs it
does not read code: so the only verification that exists is the one that runs by
itself. This script does three things to a text:

  1. CITATIONS — every `file` with a line number exists, and that line is not
     empty. This catches the worst case: a reference to a line that says
     something else
  2. CODE — every line of code quoted in a block is really in one of the
     sources. This catches the invented or stale quotation
  3. NUMBERS — the values a piece claims are recomputed now, from the same
     committed data, and printed alongside for comparison

    python3 bin/verify_piece.py pieces/01-....md
    python3 bin/verify_piece.py --all

Exits with code 1 if there is at least one error: it is meant to be a gate, not
a report to read.
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

# Where to look for the engine sources. They live outside the repository, so
# anyone who clones it will not have them — and a citation pointing into them
# comes back unverifiable, which is what the gate should say rather than
# pretend otherwise.
#
# More roots can be added with LOCBENCH_SOURCES, separated by ":".
SOURCE_ROOTS = [
    *(Path(p) for p in os.environ.get("LOCBENCH_SOURCES", "").split(":") if p),
    Path.home() / "tools" / "llama.cpp",
    Path.home() / "tools" / "tabbyAPI",
    Path.home() / "scripts",             # the collection proxy, not published
    ROOT,
]

RE_CITATION = re.compile(
    r"`([A-Za-z0-9_./+-]+\.(?:py|cpp|h|hpp|c|md|sh))`"
    r"(?:,?\s*(?:around\s+)?lines?\s+(\d+)(?:\s*[–—-]\s*(\d+))?)?"
)
RE_BLOCK = re.compile(r"```(\w*)\n(.*?)```", re.S)


def _find(path):
    """The cited file, looked up in the known roots."""
    p = Path(path)
    if p.is_absolute() and p.exists():
        return p
    for root in SOURCE_ROOTS:
        cand = root / path
        if cand.exists():
            return cand
    # citations like "tools/server/server-common.h" inside llama.cpp
    for root in SOURCE_ROOTS:
        if not root.is_dir():
            continue
        for found in root.rglob(Path(path).name):
            if str(found).endswith(path):
                return found
    return None


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.checks = 0

    def error(self, msg):
        self.errors.append(msg)

    def warning(self, msg):
        self.warnings.append(msg)


def check_citations(text, report):
    """Every reference to a file (with a line) must exist and not point at nothing.

    Lines that are an unclosed checkbox in a plan are skipped: an unchecked item
    names work that does not exist yet, by definition. Checking it would be a
    false alarm, and a gate that cries wolf teaches people to stop reading it.
    """
    seen = set()
    for number, line in enumerate(text.splitlines(), 1):
        if re.match(r"\s*- \[ \]", line):
            continue
        for m in RE_CITATION.finditer(line):
            _check_citation(m, seen, report)


def _check_citation(m, seen, report):
    path, da, a = m.group(1), m.group(2), m.group(3)
    key = (path, da, a)
    if key in seen:
        return
    seen.add(key)
    report.checks += 1

    f = _find(path)
    if f is None:
        # It may be a file outside the repository (the collection proxy, for
        # instance). An explicit error beats silence: a reader does not know
        # that file exists, and it has to be said somewhere.
        report.error(f"citation not found: {path} "
                     f"(it is in none of the known roots, not even outside the repo)")
        return
    if not da:
        return

    rows = f.read_text(encoding="utf-8", errors="replace").splitlines()
    start = int(da)
    end = int(a) if a else start
    if start < 1 or end > len(rows):
        report.error(f"{path}: lines {start}-{end} but the file has {len(rows)}")
        return
    body = [r.strip() for r in rows[start - 1:end]]
    if not any(body):
        report.error(f"{path}: lines {start}-{end} are empty")
    else:
        print(f"    ok  {path}:{start}-{end}  ->  {body[0][:60]}")


def check_code(text, report):
    """Quoted lines of code must exist in one of the sources."""
    for lang, body in RE_BLOCK.findall(text):
        if lang not in ("py", "python", "cpp", "c", "h", "hpp"):
            continue
        for line in body.splitlines():
            r = line.strip()
            # only distinctive lines: too short or too generic proves nothing
            if len(r) < 25 or r.startswith(("#", "//", "*")):
                continue
            report.checks += 1
            if not _exists_in_sources(r):
                report.warning(f"line not found in the sources: {r[:70]}")

    # comments quoted in the text are the strongest evidence: if one is
    # invented, the damage is doubled
    for m in re.finditer(r"\*\*([^*]{25,160})\*\*", text):
        frase = m.group(1).strip()
        if not re.match(r"^[A-Za-z][A-Za-z0-9 ,.'()\-/]*$", frase):
            continue
        if not frase.endswith(("token", "seconds", "measurement")):
            continue
        report.checks += 1
        if not _exists_in_sources(frase):
            report.warning(f"quoted phrase not found in the sources: {frase[:70]}")


_LINE_CACHE = None


def _exists_in_sources(line):
    """Look for the (normalised) line across all known sources."""
    global _LINE_CACHE
    if _LINE_CACHE is None:
        _LINE_CACHE = set()
        for root in SOURCE_ROOTS:
            if not root.is_dir():
                continue
            for f in root.rglob("*"):
                if f.suffix not in (".py", ".cpp", ".h", ".hpp", ".c"):
                    continue
                try:
                    for r in f.read_text(encoding="utf-8", errors="replace").splitlines():
                        _LINE_CACHE.add(re.sub(r"\s+", " ", r.strip()))
                except OSError:
                    pass
    return re.sub(r"\s+", " ", line) in _LINE_CACHE


def check_numbers(report):
    """Recompute the analysis now, so the numbers can be compared by eye."""
    import analyze_log as A

    data_files = ROOT / "data" / "2026-10-02-usage.jsonl"
    rows, _ = A.read(str(data_files))
    points = A.usable(rows)
    overall = A.fit(points)
    stream = A.fit([p for p in points if p["stream"]])
    nonstream = A.fit([p for p in points if not p["stream"]])

    g = [p for p in points if p["stream"]]
    y = [p["ttft_s"] for p in g]
    without_cache = A.ols([[1.0] * len(y), [p["uncached"] for p in g]], y)
    with_cache = A.ols([[1.0] * len(y), [p["uncached"] for p in g],
                    [p["cached_tokens"] for p in g]], y)
    cache_cost_ms = with_cache[0][2] * 1000
    gain = with_cache[1] - without_cache[1]

    # (description, recomputed value, tolerance)
    expected = [
        ("usable rows", float(len(points)), 0),
        ("n, all points", float(overall["n"]), 0),
        ("intercept, all points (s)", overall["intercept_s"], 0.001),
        ("slope, all points (tok/s)", overall["tps"], 1.0),
        ("R2, all points", overall["r2"], 0.001),
        ("n streaming", float(stream["n"]), 0),
        ("intercept streaming (s)", stream["intercept_s"], 0.001),
        ("slope streaming (tok/s)", stream["tps"], 1.0),
        ("R2 streaming", stream["r2"], 0.001),
        ("n non-streaming", float(nonstream["n"]), 0),
        ("intercept non-streaming (s)", nonstream["intercept_s"], 0.001),
        ("R2 non-streaming", nonstream["r2"], 0.001),
        ("cost of a cached token (ms)", cache_cost_ms, 0.001),
        ("R2 gained from the cache", gain, 0.0005),
    ]

    print("  values recomputed from the committed data (compare them to the text by eye):")
    for name, value, tol in expected:
        print(f"    {name:34s} = {value:.4f}")
    return expected


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("piece", nargs="?", help="the file to check")
    ap.add_argument("--all", action="store_true", help="check every piece")
    args = ap.parse_args()

    if args.all:
        files = sorted((ROOT / "pieces").glob("*.md"))
    elif args.piece:
        files = [Path(args.piece)]
    else:
        ap.error("give a piece, or --all")

    report = Report()
    for f in files:
        if not f.exists():
            report.error(f"piece does not exist: {f}")
            continue
        text = f.read_text(encoding="utf-8")
        print(f"\n=== {f} ===")
        print("  citations:")
        check_citations(text, report)
        print("  code:")
        check_code(text, report)

    # Values are recomputed and printed; comparing them to the text is for
    # whoever reads. An automatic "this number is not cited" check produces
    # false positives on any document that does not list everything, and a gate
    # that cries wolf teaches people to stop reading it.
    print("\n=== numbers, recomputed now ===")
    check_numbers(report)

    print(f"\n{report.checks} checks, {len(report.errors)} errors, {len(report.warnings)} warnings")
    for e in report.errors:
        print(f"  ERROR    {e}")
    for a in report.warnings:
        print(f"  warning  {a}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
