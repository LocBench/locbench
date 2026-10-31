#!/usr/bin/env python3
"""The 1280x640 card for the repository and for X.

It is not a second chart. It reads the same four fits as `plot_fixed_cost.py`,
so the card cannot say 4.0x while the piece says something else.

    python3 bench/plot_social_preview.py
    python3 bench/plot_social_preview.py --check

Upload the result in Settings -> Social preview. X uses it when the repository
is linked.
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
import plot_fixed_cost as P


def draw(rows, out):
    rows = sorted(rows, key=lambda r: r["a"])
    names = [r["name"] for r in rows]
    vals = [r["a"] for r in rows]
    errs = [r["se"] for r in rows]
    spread = max(vals) / min(vals)

    fig = plt.figure(figsize=(12.8, 6.4), dpi=100, facecolor="#0b1220")
    fig.patch.set_facecolor("#0b1220")

    fig.text(0.055, 0.90, "LOCBENCH", color="#60a5fa", fontsize=17,
             fontweight="bold", family="DejaVu Sans")
    fig.text(0.055, 0.865, "a measurement bench for local inference", color="#94a3b8",
             fontsize=12.5, family="DejaVu Sans")
    fig.text(0.055, 0.78, "What an engine\ncharges before\nthe first token",
             color="#f8fafc", fontsize=45, fontweight="bold", va="top",
             linespacing=1.03, family="DejaVu Sans")
    fig.text(0.055, 0.40, "Four engines · one 27B · one RTX 3090", color="#cbd5e1",
             fontsize=16, family="DejaVu Sans")
    fig.text(0.055, 0.255, f"{spread:.1f}x", color="#60a5fa", fontsize=66,
             fontweight="bold", family="DejaVu Sans")
    fig.text(0.235, 0.285, "between the fastest\nand the slowest", color="#94a3b8",
             fontsize=15, va="center", linespacing=1.25, family="DejaVu Sans")
    fig.text(0.055, 0.095, "raw data · method · limits", color="#64748b",
             fontsize=13.5, family="DejaVu Sans")

    ax = fig.add_axes([0.575, 0.19, 0.365, 0.50], facecolor="#0b1220")
    y = list(range(len(rows)))
    colors = ["#3b82f6"] * (len(rows) - 1) + ["#f59e0b"]
    bars = ax.barh(y, vals, height=0.55, color=colors, alpha=0.95,
                   xerr=errs, error_kw={"ecolor": "#cbd5e1", "capsize": 3,
                                        "elinewidth": 1.0, "capthick": 1.0})
    ax.set_yticks(y)
    ax.set_yticklabels(names, color="#e2e8f0", fontsize=13.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 0.50)
    ax.set_xticks([0, 0.1, 0.2, 0.3, 0.4])
    ax.tick_params(axis="x", colors="#94a3b8", labelsize=10.5)
    ax.tick_params(axis="y", length=0)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#334155")
    ax.grid(axis="x", color="#1e293b", linewidth=0.9)
    ax.set_axisbelow(True)
    ax.set_title("fixed cost per request (s)", color="#94a3b8", fontsize=11.5,
                 loc="left", pad=10)
    for bar, value in zip(bars, vals):
        ax.text(bar.get_width() + 0.018, bar.get_y() + bar.get_height() / 2,
                f"{value:.3f}", va="center", ha="left", color="#f8fafc", fontsize=12.5)
    fig.text(0.575, 0.135, "bars: intercept · whiskers: one standard error",
             color="#64748b", fontsize=9.5)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=fig.get_facecolor(), dpi=100)
    plt.close(fig)
    print(f"  wrote {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "assets" / "social-preview.png"))
    ap.add_argument("--check", action="store_true",
                    help="verify the numbers and write nothing")
    args = ap.parse_args()

    rows = P.compute()
    P.check(rows)
    if not args.check:
        draw(rows, Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
