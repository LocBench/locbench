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
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
import analyze_log as A


def load(paths):
    """(engine, model) -> the rows.

    Keyed by engine *and* model, not by engine alone. Grouping on the engine
    pools every file that mentions it, and a directory holding a base model, its
    uncensored twin and a control experiment on the same engine then produces one
    "tabbyapi" line averaged across all three. The number looks like a
    measurement and is a mixture.
    """
    runs = {}
    for pattern in paths:
        for path in sorted(glob.glob(pattern)):
            rows = []
            for line in Path(path).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
            if not rows:
                continue
            first = rows[0]
            key = (first.get("engine"), first.get("model"))
            entry = runs.setdefault(key, {"version": first.get("version"), "rows": [], "files": []})
            entry["rows"].extend(rows)
            entry["files"].append(Path(path).name)
    return runs


def _same_cell(value, wanted):
    """A cell is the same cell, or the same cell at a given length.

    A plain prefix match is wrong and wrong quietly:
    "stream+inject".startswith("stream") is true, so a fit labelled `stream`
    absorbs the `stream+inject` rows and reports a line belonging to neither.
    """
    value = str(value or "")
    return value == wanted or value.startswith(wanted + "@")


def line_for(rows, cell, clock="engine_ttft_s"):
    """Fit one cell across the lengths, on one named clock.

    The clock is a parameter and not a preference, because the engines do not
    all report the same interval. Over identical streaming requests, llama.cpp's
    reported window leaves 58 ms of each request uncounted and TabbyAPI's leaves
    128: the first stops when the prompt has been evaluated, the second when the
    first token has been sampled, and neither covers getting the bytes out.
    Fitting both and printing the gap is the only way to see whether a gap
    between two engines is a gap between two engines or between two stopwatches.

    The earlier version picked whichever clock a row happened to have and fell
    back silently -- so an engine with both would have been fitted on the engine
    clock and an engine with only one on the client clock, and the two numbers
    would have been printed in one column as if they were the same quantity.
    """
    points = {}
    for row in rows:
        # prefix match: the sweep labels its cells plain@300, plain@1200...
        if row.get("discarded") or not _same_cell(row.get("cell"), cell):
            continue
        n = row.get("uncached") or row.get("prompt_tokens")
        window = row.get(clock)
        if not n or window is None:
            continue
        points.setdefault(n, []).append(window)
    if len(points) < 3:
        return None
    xs = [float(n) for n in sorted(points)]
    ys = [statistics.median(points[n]) for n in sorted(points)]
    fit = A.ols([[1.0] * len(xs), xs], ys)
    if not fit:
        return None
    (intercept, slope), r2, count = fit
    # The standard error on the intercept, because an intercept quoted without
    # one is an intercept nobody can argue with and nobody should believe. It
    # depends on how far the shortest prompt is from zero: a fit whose nearest
    # point is at 400 tokens is extrapolating, and this says by how much that
    # costs.
    m = len(xs)
    mean_x = sum(xs) / m
    sxx = sum((v - mean_x) ** 2 for v in xs)
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    if m > 2 and sxx > 0:
        var = sum(r * r for r in residuals) / (m - 2)
        stderr = math.sqrt(var * (1.0 / m + mean_x * mean_x / sxx))
    else:
        stderr = float("nan")
    return {"a": intercept, "se": stderr, "shortest": min(xs),
            "r": 1 / slope if slope > 0 else float("inf"),
            "r2": r2, "n": count, "clock": clock}


def _cell(f):
    """One fitted intercept, as a column. Absent is said, not left blank."""
    if not f:
        return "-- not on this clock"
    return "%6.3f +/- %.3f s" % (f["a"], f["se"])


def _tail(rows, cell):
    """How long text kept arriving after the first chunk, in seconds.

    The guard on the client's clock: that clock is a time to first token only if
    the engine streams. The first metric tried here was the fraction of the
    reply that had arrived at the first chunk, and it was wrong in a way worth
    recording. On a 4,000-token prompt the prefill is most of the wall time, so
    even a perfectly streaming engine shows a high fraction -- LM Studio sits at
    0.81 there with a prefill rate identical to the one measured on its own
    clock, which is to say it is behaving correctly and the metric was measuring
    the prompt.

    What separates streaming from buffering is not the fraction but the tail.
    An engine that sends its whole answer in one chunk has nothing left to
    arrive, so `total - ttft` collapses to zero; an engine that streams has one.
    """
    tails = []
    for row in rows:
        if row.get("discarded") or not _same_cell(row.get("cell"), cell):
            continue
        t, total = row.get("client_ttft_s"), row.get("client_total_s")
        if t is None or not total:
            continue
        tails.append(total - t)
    if not tails:
        return None
    return statistics.median(tails)


def _gap(engine_fit, client_fit):
    """What the engine's clock does not time, in seconds."""
    if not engine_fit or not client_fit:
        return "--"
    return "%+.3f s" % (client_fit["a"] - engine_fit["a"])


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
    print("D3 — the same cell, engine against engine")
    print("  comparing the '%s' cell" % args.cell)
    print()
    print("  %-26s %-18s %19s %19s %9s %8s" % (
        "engine / model", "version", "engine's clock", "client's clock", "gap", "arrives after"))
    print("  " + "-" * 112)

    fitted = {}
    for engine, model in sorted(runs, key=lambda k: (k[0] or "", k[1] or "")):
        run = runs[(engine, model)]
        fe = line_for(run["rows"], args.cell, "engine_ttft_s")
        fc = line_for(run["rows"], args.cell, "client_ttft_s")
        label = "%s / %s" % (engine, (model or "?").split("/")[-1])
        if not fe and not fc:
            print("  %-26s %-18s   (not enough lengths to fit)" % (
                label[:26], (run["version"] or "unknown")[:18]))
            continue
        tail = _tail(run["rows"], args.cell)
        fitted[label] = {"engine": fe, "client": fc, "tail": tail}
        print("  %-26s %-18s %19s %19s %9s %8s" % (
            label[:26], (run["version"] or "unknown")[:18],
            _cell(fe), _cell(fc), _gap(fe, fc),
            "%.2f s" % tail if tail is not None else "-"))

    if len(fitted) < 2:
        return 0

    print()
    print("  VERDICT")

    gaps = {e: f["client"]["a"] - f["engine"]["a"]
            for e, f in fitted.items() if f["engine"] and f["client"]}
    if len(gaps) >= 2:
        spread = max(gaps.values()) - min(gaps.values())
        print("    what each engine's clock leaves untimed: %s"
              % ", ".join("%s %.3f s" % (e.split(" / ")[0], g)
                          for e, g in sorted(gaps.items())))
        if spread > 0.030:
            print("    -> %.0f ms apart. These are not the same instrument, so the" % (spread * 1000))
            print("       engine's-clock column is comparing stopwatches as much as")
            print("       engines. The client's clock is one clock measuring one")
            print("       interval for every engine: that is the column to read.")
        else:
            print("    -> within %.0f ms of each other. The engine clocks time the" % (spread * 1000))
            print("       same interval here, and either column will do.")

    buffered = {e: f["tail"] for e, f in fitted.items()
                if f.get("tail") is not None and f["tail"] < 0.100}
    if buffered:
        print("    -> these engines do not stream: %s" % ", ".join(
            "%s (%.0f ms arrived after the first chunk)" % (e.split(" / ")[0], 1000 * r)
            for e, r in sorted(buffered.items())))
        print("       For those rows the client's clock is the whole reply, not a")
        print("       time to first token, and they must not be ranked on it.")

    for clock, name in (("client", "the client's clock"), ("engine", "the engine's clock")):
        values = {e: f[clock]["a"] for e, f in fitted.items() if f[clock]}
        if len(values) < 2:
            continue
        lo, hi = min(values.values()), max(values.values())
        print("    on %s: %s" % (name, ", ".join(
            "%s %.3f s" % (e.split(" / ")[0], a) for e, a in sorted(values.items()))))
        print("       spread %.3f s (%.1fx between the smallest and the largest)"
              % (hi - lo, (hi / lo) if lo > 0 else float("inf")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
