#!/usr/bin/env python3
"""plot_fixed_cost.py — the four engines, one clock, one picture.

The table in piece 02 is the evidence; this is the same evidence at a glance.
It reads the four streamed files, fits the same intercept the piece fits, and
refuses to draw if a number has moved away from the published one.

    python3 bench/plot_fixed_cost.py
    python3 bench/plot_fixed_cost.py --check

`--check` does everything except write the file: it is the test's entry point.
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
import compare_engines as C

# The published values, so the picture cannot quietly drift away from the piece.
# (intercept s, standard error s)
EXPECTED = {
    "Ollama": (0.105, 0.007),
    "llama.cpp": (0.161, 0.010),
    "TabbyAPI": (0.273, 0.044),
    "LM Studio": (0.416, 0.061),
}

FILES = {
    "Ollama": "data/2026-10-03-stream-ollama.jsonl",
    "llama.cpp": "data/2026-10-03-stream-llamacpp.jsonl",
    "TabbyAPI": "data/2026-10-03-stream-tabbyapi.jsonl",
    "LM Studio": "data/2026-10-03-stream-lmstudio.jsonl",
}

TOLERANCE = 0.0015


def compute():
    """Fit the streamed cell of each engine on the client's clock."""
    rows = []
    for name, rel in FILES.items():
        runs = C.load([str(ROOT / rel)])
        if len(runs) != 1:
            raise SystemExit(f"{rel}: expected one (engine, model), found {len(runs)}")
        (engine, model), entry = next(iter(runs.items()))
        fit = C.line_for(entry["rows"], "stream", "client_ttft_s")
        if not fit:
            raise SystemExit(f"{rel}: no fit")
        rows.append({
            "name": name,
            "engine": engine,
            "model": model,
            "version": entry["version"],
            "a": fit["a"],
            "se": fit["se"],
            "r": fit["r"],
            "r2": fit["r2"],
            "n": fit["n"],
        })
    return rows


def check(rows):
    bad = []
    for row in rows:
        want, want_se = EXPECTED[row["name"]]
        if abs(row["a"] - want) > TOLERANCE:
            bad.append(f"{row['name']}: intercept {row['a']:.4f}, published {want:.4f}")
        if abs(row["se"] - want_se) > TOLERANCE:
            bad.append(f"{row['name']}: error {row['se']:.4f}, published {want_se:.4f}")
    if bad:
        raise SystemExit("the picture would not match the piece:\n  " + "\n  ".join(bad))
    print("  values match the published table")


def draw(rows, out):
    rows = sorted(rows, key=lambda r: r["a"])
    fig, ax = plt.subplots(figsize=(10.4, 4.6))
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")

    y = list(range(len(rows)))
    names = [r["name"] for r in rows]
    values = [r["a"] for r in rows]
    errors = [r["se"] for r in rows]

    bars = ax.barh(y, values, height=0.52, color="#2f4b7c", alpha=0.92,
                   xerr=errors, error_kw={"ecolor": "#1a1a1a", "capsize": 4,
                                          "elinewidth": 1.1, "capthick": 1.1})
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=12)
    ax.invert_yaxis()
    ax.set_xlim(0, 0.52)
    ax.set_xlabel("fixed cost per request (s)", fontsize=11)
    ax.grid(axis="x", color="#d9d9d9", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", colors="#444444")

    for bar, row in zip(bars, rows):
        label = f"{row['a']:.3f} ± {row['se']:.3f} s"
        ax.text(bar.get_width() + row["se"] + 0.012, bar.get_y() + bar.get_height() / 2,
                label, va="center", ha="left", fontsize=10.5, color="#1a1a1a",
                clip_on=False)

    fig.text(0.06, 0.94, "What an engine charges before the first token",
             fontsize=17, fontweight="bold", color="#111111", ha="left")
    fig.text(0.06, 0.875,
             "Qwen3.8-27B · one RTX 3090 · one client clock · 3 October 2026",
             fontsize=10.5, color="#555555", ha="left")
    fig.text(0.06, 0.035,
             "Bars: the intercept of time-to-first-token against uncached tokens. "
             "Whiskers: one standard error.\n"
             "4.0x between the ends; the middle of the field is not resolved.",
             fontsize=9.2, color="#666666", ha="left", linespacing=1.45)

    fig.subplots_adjust(left=0.14, right=0.73, top=0.80, bottom=0.20)
    fig.savefig(out, format="svg", facecolor=fig.get_facecolor(),
                metadata={"Date": None, "Creator": None})
    plt.close(fig)
    print(f"  wrote {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "pieces" / "fixed-cost.svg"))
    ap.add_argument("--check", action="store_true",
                    help="verify the numbers and write nothing")
    args = ap.parse_args()

    rows = compute()
    for row in rows:
        print(f"  {row['name']:10s} {row['a']:.4f} ± {row['se']:.4f} s  "
              f"{row['r']:.0f} tok/s  R²={row['r2']:.4f}  n={row['n']}")
    check(rows)
    if not args.check:
        draw(rows, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
