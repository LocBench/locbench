#!/usr/bin/env python3
"""compare_engines.py — D3, engine against engine.

D1 asks whether the streaming, the flag or the engine carries the fixed cost.
D3 asks the same question of the other engines, and the answer is a comparison,
which means the same shapes have to be lined up before anything is subtracted
from anything else.

Two things make that harder than it looks, and both are said out loud here
rather than smoothed over:

  * **the window is measured by different instruments.** Where an engine
    publishes its own times, that is what is recorded; where it publishes
    nothing, the client's clock is. An engine's window and a client's window
    are not the same quantity -- the client's includes the network and the
    arrival of the first chunk -- and mixing them would produce a difference
    that belongs to the measuring instrument, not to the engine.
  * **the engines do not all run the same weights.** The rule from the protocol
    is to compare at equal nominal parameters and quantization, not equal files,
    and to say when that is what is happening.

    python3 bench/compare_engines.py data/2026-10-03-d1-*.jsonl
"""
import argparse
import glob
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
import analyze_log as A


def load(paths):
    """(engine, version) -> the rows, plus which engine said what."""
    runs = {}
    for pattern in paths:
        for path in sorted(glob.glob(pattern)):
            engine = version = None
            rows = []
            for line in Path(path).read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                rows.append(row)
                engine = engine or row.get("engine")
                version = version or row.get("version")
            if engine:
                runs.setdefault(engine, {"version": version, "rows": [], "files": []})
                runs[engine]["rows"].extend(rows)
                runs[engine]["files"].append(Path(path).name)
    return runs


def line_for(rows, cell):
    """Fit one cell across the lengths, on whichever window is available."""
    points = {}
    for row in rows:
        if row.get("discarded") or row.get("cell") != cell:
            continue
        n = row.get("uncached") or row.get("prompt_tokens")
        if row.get("engine_ttft_s") is not None:
            window, source = row["engine_ttft_s"], "engine"
        elif row.get("client_ttft_s") is not None:
            window, source = row["client_ttft_s"], "client"
        else:
            continue
        if not n or not window:
            continue
        points.setdefault(n, {"w": [], "src": set()})
        points[n]["w"].append(window)
        points[n]["src"].add(source)
    if len(points) < 3:
        return None
    xs = [float(n) for n in sorted(points)]
    ys = [statistics.median(points[n]["w"]) for n in sorted(points)]
    sources = set().union(*(points[n]["src"] for n in points))
    fit = A.ols([[1.0] * len(xs), xs], ys)
    if not fit:
        return None
    (intercept, slope), r2, count = fit
    return {"a": intercept, "r": 1 / slope if slope > 0 else float("inf"),
            "r2": r2, "n": count, "source": "+".join(sorted(sources))}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--cell", default="plain",
                    help="which cell to compare (default: plain, the simplest)")
    args = ap.parse_args()

    runs = load(args.paths)
    if not runs:
        print("  nothing to compare: no rows found", file=sys.stderr)
        return 2

    print()
    print("D3 — the same four cells, engine against engine")
    print("  comparing the '%s' cell, which needs no flag and no streaming" % args.cell)
    print()
    print("  %-12s %-42s %9s %9s %8s %7s %s" % (
        "engine", "version", "fixed", "tok/s", "R2", "points", "window from"))
    print("  " + "-" * 100)

    fitted = {}
    for engine in sorted(runs):
        run = runs[engine]
        line = line_for(run["rows"], args.cell)
        if not line:
            print("  %-12s %-42s   (not enough lengths to fit)" % (
                engine, (run["version"] or "unknown")[:42]))
            continue
        fitted[engine] = line
        print("  %-12s %-42s %7.3f s %9.0f %8.4f %7d %s" % (
            engine, (run["version"] or "unknown")[:42],
            line["a"], line["r"], line["r2"], line["n"], line["source"]))

    if len(fitted) >= 2:
        same_instrument = len({f["source"] for f in fitted.values()}) == 1
        print()
        print("  VERDICT")
        if not same_instrument:
            print("    The windows are not all measured by the same instrument.")
            print("    An engine that reports its own timing and one that does not")
            print("    cannot have their intercepts subtracted: part of the")
            print("    difference belongs to the clock, not to the engine. Rows")
            print("    say which is which.")
        values = {e: f["a"] for e, f in fitted.items()}
        lo, hi = min(values.values()), max(values.values())
        print("    fixed cost by engine: %s"
              % ", ".join("%s %.3f s" % (e, a) for e, a in sorted(values.items())))
        print("    spread: %.3f s (%.1fx between the smallest and the largest)"
              % (hi - lo, (hi / lo) if lo > 0 else float("inf")))
        if hi - lo < 0.05:
            print("    -> the engines agree within 50 ms. Whatever the cost is, it")
            print("       is not one engine's quirk.")
        else:
            print("    -> they do not agree, and the engine that stands out is")
            print("       paying something the others do not. Check the instrument")
            print("       column before believing the size of it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
