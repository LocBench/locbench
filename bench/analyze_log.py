#!/usr/bin/env python3
"""What a request actually costs: analyse the proxy log.

Redoes, with one command, the 2 October 2026 analysis of the data logged by
the collection proxy, and prints its limits alongside — which matter as much as
the numbers, because this data was NOT collected to answer this question and
carries a confound.

    python3 bench/analyze_log.py
    python3 bench/analyze_log.py --log data/2026-10-02-usage.jsonl
    python3 bench/analyze_log.py --csv data/local-inference.csv

The nub of it, in one line: TabbyAPI computes

    prompt_tokens_per_sec = (prompt_tokens - cached_tokens) / prompt_time

that is, **uncached tokens** over the prompt window. That window contains a
fixed cost per request, so the field everyone reads as "the machine's prefill
speed" is in fact that speed **diluted by how little work the request had**.
Here the real time is recovered by inverting the formula, and the fixed cost
shows up as the intercept.

No external dependencies: standard library only.
"""
import argparse
import csv
import json
import math
import os
import sys
from statistics import median

DEFAULT_LOG = os.path.expanduser("~/.local/share/tabby-usage/usage.jsonl")


# ----------------------------------------------------------------- reading

def read(path):
    """The JSON lines of the log. Unreadable lines are counted, not silently skipped."""
    rows, rotte = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                rotte += 1
    return rows, rotte


def _reason(r):
    """None if the row is usable, otherwise why it is not.

    A single function decides: so the list of points and the list of discards
    cannot tell two different stories. Rule 5 of the protocol.
    """
    if r.get("status") not in (None, 200):
        return "request failed (status %s)" % r.get("status")
    p, c, v = r.get("prompt_tokens"), r.get("cached_tokens"), r.get("prompt_tps")
    if not p or not v:
        return "the engine returned no usage block"
    if c is None:
        return "cached_tokens is missing"
    if p - c <= 0:
        return "no uncached tokens (it was all in cache)"
    return None


def _normalise(r):
    p, c, v = r["prompt_tokens"], r["cached_tokens"], r["prompt_tps"]
    uncached = p - c
    return {
        "ts": r.get("ts"),
        "client": (r.get("client") or "?")[:40],
        "model": r.get("model"),
        "stream": bool(r.get("stream")),
        "injected": bool(r.get("injected")),
        "prompt_tokens": p,
        "cached_tokens": c,
        "uncached": float(uncached),
        "ttft_s": uncached / v,   # <-- the metric, inverted
        "reported_tps": float(v),
        "completion_tokens": r.get("completion_tokens"),
        "wall_s": r.get("wall_s"),
        # independent cross-check: the time observed by the proxy minus
        # generation. It does not go through the engine's own accounting.
        "observed_s": _observed(r),
    }


def usable(rows):
    """The requests a prompt window can be recovered from, normalised."""
    return [_normalise(r) for r in rows if _reason(r) is None]


def discards(rows):
    """The unusable rows, grouped by reason."""
    count = {}
    for r in rows:
        m = _reason(r)
        if m:
            count[m] = count.get(m, 0) + 1
    return count


def _observed(r):
    w, ct, ctps = r.get("wall_s"), r.get("completion_tokens"), r.get("completion_tps")
    if w is None:
        return None
    generation = (ct / ctps) if (ct and ctps) else 0.0
    return w - generation


# ---------------------------------------------------------- least squares

def ols(columns, y):
    """Least squares via the normal equations. `columns` is a list of predictors
    (the first must be the constant 1.0). Returns (beta, r2, n)."""
    n = len(y)
    k = len(columns)
    if n <= k:
        return None
    A = [[sum(columns[a][i] * columns[b][i] for i in range(n)) for b in range(k)]
         for a in range(k)]
    v = [sum(columns[a][i] * y[i] for i in range(n)) for a in range(k)]
    M = [A[i][:] + [v[i]] for i in range(k)]
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(M[r][i]))
        M[i], M[p] = M[p], M[i]
        if abs(M[i][i]) < 1e-12:
            return None                      # collinear columns: the model is not estimable
        for r in range(k):
            if r != i:
                f = M[r][i] / M[i][i]
                for c in range(i, k + 1):
                    M[r][c] -= f * M[i][c]
    beta = [M[i][k] / M[i][i] for i in range(k)]
    yh = [sum(columns[j][i] * beta[j] for j in range(k)) for i in range(n)]
    yb = sum(y) / n
    ssr = sum((y[i] - yh[i]) ** 2 for i in range(n))
    sst = sum((yi - yb) ** 2 for yi in y)
    return beta, (1 - ssr / sst if sst else 0.0), n


def fit(points, time_key="ttft_s"):
    """Fit of time ~ fixed_cost + uncached * slope."""
    points = [p for p in points if p.get(time_key) is not None]
    if len(points) <= 2:
        return None
    x = [p["uncached"] for p in points]
    y = [p[time_key] for p in points]
    res = ols([[1.0] * len(x), x], y)
    if not res:
        return None
    (a, b), r2, n = res
    return {"intercept_s": a, "slope_s": b, "tps": (1 / b if b > 0 else float("inf")),
            "r2": r2, "n": n, "points": points}


# -------------------------------------------------------------- printing

def title(t):
    print()
    print(t)
    print("-" * len(t))


def print_fit(label, r):
    if not r:
        print("  %-26s  (too few points)" % label)
        return
    print("  %-26s n=%3d   %7.0f ms + uncached / %5.0f tok/s   R2=%.3f"
          % (label, r["n"], r["intercept_s"] * 1000, r["tps"], r["r2"]))


def census(rows, rotte, points):
    title("1. CENSUS")
    print("  lines in the log:          %d" % len(rows))
    if rotte:
        print("  unreadable lines:          %d" % rotte)
    print("  usable for the fit:        %d" % len(points))
    print("  discarded:                 %d" % (len(rows) - len(points)))
    for reason, n in sorted(discards(rows).items(), key=lambda kv: -kv[1]):
        print("      %-46s %3d" % (reason, n))
    print()
    models = {}
    for r in rows:
        models[r.get("model")] = models.get(r.get("model"), 0) + 1
    print("  models:")
    for m, n in sorted(models.items(), key=lambda kv: -kv[1]):
        print("    %-38s %3d" % (m, n))


def section_fit(points):
    title("2. THE METRIC, INVERTED")
    print("  prompt window recovered from  (prompt_tokens - cached_tokens) / prompt_tps")
    print()
    overall = fit(points)
    stream = fit([p for p in points if p["stream"]])
    nonstream = fit([p for p in points if not p["stream"]])
    print_fit("all usable", overall)
    print_fit("streaming only", stream)
    print_fit("non-streaming only", nonstream)
    print_fit("cross-check: observed time",
                 fit(points, "observed_s"))
    return overall, stream, nonstream


def section_confound(points):
    title("3. THE CONFOUND (read this before believing section 2)")
    for name, g in (("streaming", [p for p in points if p["stream"]]),
                    ("non-streaming", [p for p in points if not p["stream"]])):
        if not g:
            continue
        unc = sorted(p["uncached"] for p in g)
        cache = [p["cached_tokens"] / p["prompt_tokens"] for p in g]
        print("  %-15s n=%3d   uncached: min %6.0f  median %6.0f  max %6.0f"
              % (name, len(g), unc[0], median(unc), unc[-1]))
        print("  %-15s        cached fraction: median %.2f" % ("", median(cache)))
    print()
    print("  If the two groups do not overlap in length, comparing their")
    print("  intercepts is an EXTRAPOLATION, not a measurement:")
    print()
    print("  %-20s %9s %11s %10s %11s" % ("uncached", "n str", "t str", "n non-st", "t non-st"))
    for lo, hi in [(0, 500), (500, 1500), (1500, 4000), (4000, 10000), (10000, float("inf"))]:
        s = [p["ttft_s"] for p in points if p["stream"] and lo <= p["uncached"] < hi]
        m = [p["ttft_s"] for p in points if not p["stream"] and lo <= p["uncached"] < hi]
        label = "%d-%s" % (lo, "+" if hi == float("inf") else int(hi))
        ts = "%8.0f ms" % (median(s) * 1000) if len(s) >= 2 else "         -"
        tm = "%8.0f ms" % (median(m) * 1000) if len(m) >= 2 else "         -"
        print("  %-20s %9d %11s %10d %11s" % (label, len(s), ts, len(m), tm))

    # The finishing blow: the alternative explanations are the same partition.
    print()
    print("  CROSS-TAB stream x injected — the three explanations do not separate:")
    print()
    print("  %-24s %5s %12s %9s  %s" % ("class", "n", "intercept", "R2", "who is in it"))
    for st in (True, False):
        for inj in (True, False):
            g = [p for p in points if p["stream"] == st and p["injected"] == inj]
            if not g:
                continue
            r = fit(g)
            chi = {}
            for p in g:
                chi[p["client"].split("/")[0]] = chi.get(p["client"].split("/")[0], 0) + 1
            if r:
                print("  %-24s %5d %9.0f ms %9.3f  %s"
                      % ("stream=%d injected=%d" % (st, inj), len(g),
                         r["intercept_s"] * 1000, r["r2"],
                         ",".join(sorted(chi, key=lambda k: -chi[k])[:4])))
            else:
                print("  %-24s %5d %12s %9s  %s"
                      % ("stream=%d injected=%d" % (st, inj), len(g), "too few", "-",
                         ",".join(sorted(chi, key=lambda k: -chi[k])[:4])))
    print()
    print("  The full cells are two, and they are complementary: whoever sends")
    print("  streaming does not send `stream_options`, whoever does not send")
    print("  streaming does. With this data **streaming, injection and client are")
    print("  indistinguishable**: the fixed cost can belong to any of the three.")

    print()
    print("  And the two models have different intercepts — but ran in different sessions:")
    for m in sorted({p["model"] for p in points}):
        g = [p for p in points if p["model"] == m]
        r, rs = fit(g), fit([p for p in g if p["stream"]])
        if r:
            print("    %-34s n=%3d  %6.0f ms  R2=%.3f" % (m, r["n"], r["intercept_s"] * 1000, r["r2"]))
        if rs:
            print("    %-34s n=%3d  %6.0f ms  R2=%.3f  (streaming only)"
                  % ("  ^ of which streaming", rs["n"], rs["intercept_s"] * 1000, rs["r2"]))


def section_cache(points):
    title("4. DOES THE CACHE COST ANYTHING? (hypothesis killed)")
    g = [p for p in points if p["stream"]]
    if len(g) <= 3:
        print("  (too few points)")
        return
    x1 = [p["uncached"] for p in g]
    x2 = [p["cached_tokens"] for p in g]
    y = [p["ttft_s"] for p in g]
    without_cache = ols([[1.0] * len(y), x1], y)
    with_cache = ols([[1.0] * len(y), x1, x2], y)
    if not (without_cache and with_cache):
        print("  (collinear columns)")
        return
    (a1, b1), r1, n = without_cache
    (a2, b2, c2), r2, _ = with_cache
    print("  t = a + b*uncached                  R2 = %.4f" % r1)
    print("  t = a + b*uncached + c*in_cache     R2 = %.4f" % r2)
    print()
    print("  R2 gained by adding the cache:       %+.4f" % (r2 - r1))
    print("  cost of a cached token:              %.3f ms  (%.0f tok/s)" % (c2 * 1000, 1 / c2 if c2 > 0 else float("inf")))
    print()
    if r2 - r1 < 0.01:
        print("  -> The cache explains nothing: the fixed cost is per REQUEST, not per token.")
    else:
        print("  -> The cache explains something: the line has to be rewritten.")


def section_table(points, overall):
    title("5. WHAT THE METRIC CLAIMS, AGAINST THE MACHINE")
    if not overall:
        print("  (no fit)")
        return
    a, b, tps = overall["intercept_s"], overall["slope_s"], overall["tps"]
    print("  the fit says: time = %.0f ms + uncached / %.0f tok/s" % (a * 1000, tps))
    print()
    print("  %-18s %14s %16s" % ("uncached tokens", "the metric says", "actual time"))
    for x in (200, 1000, 10000, 30000):
        t = a + x / tps
        print("  %-18d %11.0f tok/s %13.0f ms" % (x, x / t, t * 1000))
    print()
    print("  The middle column is what ends up in the posts. It is the real time")
    print("  divided by work the machine never did.")


def export_csv(points, path):
    columns = ["ts", "client", "model", "stream", "injected", "prompt_tokens",
               "cached_tokens", "uncached", "reported_tps", "ttft_s",
               "observed_s", "completion_tokens", "wall_s"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for p in points:
            w.writerow(p)
    print("\n  CSV written: %s  (%d rows)" % (path, len(points)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default=DEFAULT_LOG, help="the proxy's JSONL log")
    ap.add_argument("--csv", help="export the rows used to CSV")
    args = ap.parse_args()

    if not os.path.exists(args.log):
        sys.exit("log not found: %s" % args.log)

    rows, rotte = read(args.log)
    points = usable(rows)
    print("LocBench — analysis of %s" % args.log)

    census(rows, rotte, points)
    overall, _, _ = section_fit(points)
    section_confound(points)
    section_cache(points)
    section_table(points, overall)

    if args.csv:
        export_csv(points, args.csv)


if __name__ == "__main__":
    main()
