#!/usr/bin/env python3
"""analyze_d1.py — what the four cells say, and what they do not.

D1 asks one question: the fixed cost that shows up in the prompt window — is it
the streaming, the telemetry flag, or the engine?

One length cannot answer it. At a single prompt size a cell with a fixed cost
and a cell without one differ by that fixed cost, which is visible, but a cell
whose *slope* differs looks the same as one whose intercept does. So the
measurement is taken at several lengths and each cell is fitted separately:

    window = fixed_cost + uncached_tokens / throughput

The intercepts are then compared. If one cell carries a cost the others do not,
its intercept stands out and the slopes stay the same.

    python3 bench/analyze_d1.py data/2026-10-03-d1-tabbyapi.jsonl
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
import analyze_log as A   # the least squares, already tested there


def load(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def cells(rows):
    """Median window per (cell, length), and what was discarded."""
    table = {}
    dropped = []
    for row in rows:
        if row.get("discarded"):
            dropped.append(row)
            continue
        cell = row.get("cell")
        n = row.get("uncached")
        # The engine's window where it exists, otherwise the client's. Which one
        # it is matters and is carried along: comparing an engine measurement
        # with a client one is comparing two different quantities.
        if row.get("engine_ttft_s") is not None:
            window, source = row["engine_ttft_s"], "engine"
        elif row.get("client_ttft_s") is not None:
            window, source = row["client_ttft_s"], "client"
        else:
            continue
        if not n or not window:
            continue
        table.setdefault(cell, {}).setdefault(n, {"w": [], "src": set()})
        table[cell][n]["w"].append(window)
        table[cell][n]["src"].add(source)
    return table, dropped


def fit_cell(points):
    """The line for one cell, or None when there are too few points."""
    if len(points) < 3:
        return None
    x = [float(n) for n, _ in points]
    y = [w for _, w in points]
    result = A.ols([[1.0] * len(x), x], y)
    if not result:
        return None
    (intercept, slope), r2, count = result
    return {"a": intercept, "r": (1 / slope if slope > 0 else float("inf")),
            "r2": r2, "n": count}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log")
    args = ap.parse_args()

    rows = load(args.log)
    table, dropped = cells(rows)

    print()
    print("D1 — does the streaming, the flag, or the engine carry the fixed cost?")
    print("  %d rows, %d discarded" % (len(rows), len(dropped)))
    print()

    fits = {}
    for cell in sorted(table):
        points = [(n, statistics.median(v["w"])) for n, v in sorted(table[cell].items())]
        sources = set().union(*(v["src"] for v in table[cell].values()))
        line = fit_cell(points)
        print("  %s  (measured by: %s)" % (cell, ", ".join(sorted(sources))))
        for n, w in points:
            print("    %6d tokens -> %7.3f s   %6.0f tok/s if the window were pure compute"
                  % (n, w, n / w))
        if line:
            fits[cell] = line
            print("    fit:  %.3f s + n / %.0f tok/s     R2 = %.4f  (%d points)"
                  % (line["a"], line["r"], line["r2"], line["n"]))
        else:
            print("    (too few lengths to fit a line)")
        print()

    engines = {c: f for c, f in fits.items() if c in table
               and set().union(*(v["src"] for v in table[c].values())) == {"engine"}}
    if len(engines) >= 2:
        intercepts = {c: f["a"] for c, f in engines.items()}
        lo, hi = min(intercepts.values()), max(intercepts.values())
        spread = hi - lo
        print("  VERDICT")
        print("    intercepts, cells measured the same way: %s"
              % ", ".join("%s %.3f s" % (c, a) for c, a in sorted(intercepts.items())))
        print("    spread: %.3f s" % spread)
        if spread < 0.05:
            print("    -> the cells agree. The fixed cost is the engine's: it is")
            print("       there whichever way the request is made, and neither the")
            print("       streaming nor the telemetry flag adds one.")
        else:
            print("    -> the cells disagree. The cell that stands out is carrying")
            print("       a cost the others do not, and that is the answer.")
    else:
        print("  VERDICT: only one cell has a fittable line, so the comparison")
        print("  cannot be made. D1 needs at least two lengths on cells measured")
        print("  the same way -- the engine's number on at least two of them.")

    if dropped:
        print()
        print("  discarded rows, with reasons (kept, never deleted):")
        reasons = {}
        for row in dropped:
            reasons[row.get("reason")] = reasons.get(row.get("reason"), 0) + 1
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print("    %-58s %d" % (str(reason)[:58], count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
