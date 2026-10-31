#!/usr/bin/env python3
"""plot_fixed_cost_five.py — the fifth engine, on the same clock.

The four-engine piece ended at 4.0x. This reads the four October files plus the
two HyperQwen sessions and draws the five-engine sample, refusing to draw if a
number has moved away from the one the piece states.

    python3 bench/plot_fixed_cost_five.py
    python3 bench/plot_fixed_cost_five.py --check
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
import compare_engines as C

FILES = {
    "HyperQwen": [
        "data/2026-10-31-stream-hyperqwen.jsonl",
        "data/2026-10-31-stream-hyperqwen-2.jsonl",
    ],
    "Ollama": ["data/2026-10-03-stream-ollama.jsonl"],
    "llama.cpp": ["data/2026-10-03-stream-llamacpp.jsonl"],
    "TabbyAPI": ["data/2026-10-03-stream-tabbyapi.jsonl"],
    "LM Studio": ["data/2026-10-03-stream-lmstudio.jsonl"],
}

# (intercept s, standard error s) as the pieces state them.
EXPECTED = {
    "HyperQwen": (0.0525, 0.0022),
    "Ollama": (0.1047, 0.0071),
    "llama.cpp": (0.1608, 0.0097),
    "TabbyAPI": (0.2731, 0.0442),
    "LM Studio": (0.4165, 0.0607),
}

TOLERANCE = 0.0015


def _fit(paths):
    rows = []
    for rel in paths:
        rows += [json.loads(line) for line in
                 (ROOT / rel).read_text(encoding="utf-8").splitlines() if line.strip()]
    fit = C.line_for(rows, "stream", "client_ttft_s")
    if not fit:
        raise SystemExit("no fit for %s" % ", ".join(paths))
    return fit, rows


def compute():
    rows = []
    for name, paths in FILES.items():
        fit, raw = _fit(paths)
        entry = {
            "name": name,
            "a": fit["a"],
            "se": fit["se"],
            "r": fit["r"],
            "r2": fit["r2"],
            "n": fit["n"],
            "files": paths,
            "rows": len(raw),
            "version": raw[0].get("version"),
            "model": raw[0].get("model"),
        }
        if len(paths) > 1:
            entry["sessions"] = []
            for rel in paths:
                sfit, _ = _fit([rel])
                entry["sessions"].append({"file": rel, "a": sfit["a"], "se": sfit["se"]})
        rows.append(entry)
    return rows


def check(rows):
    by = {row["name"]: row for row in rows}
    bad = []
    for name, (want, want_se) in EXPECTED.items():
        row = by.get(name)
        if row is None:
            bad.append(f"{name}: missing")
            continue
        if abs(row["a"] - want) > TOLERANCE:
            bad.append(f"{name}: intercept {row['a']:.4f}, published {want:.4f}")
        if abs(row["se"] - want_se) > TOLERANCE:
            bad.append(f"{name}: error {row['se']:.4f}, published {want_se:.4f}")
    if "HyperQwen" in by and "sessions" in by["HyperQwen"]:
        sessions = by["HyperQwen"]["sessions"]
        if len(sessions) == 2 and abs(sessions[0]["a"] - sessions[1]["a"]) > 0.01:
            bad.append("HyperQwen: the two sessions disagree by more than 10 ms")
    values = [row["a"] for row in rows]
    if values and max(values) / min(values) < 7.5:
        bad.append("the five-engine spread is no longer above 7.5x")
    if bad:
        raise SystemExit("the picture would not match the piece:\n  " + "\n  ".join(bad))
    print("  values match the five-engine table")


def draw(rows, out):
    rows = sorted(rows, key=lambda r: r["a"])
    names = [r["name"] for r in rows]
    values = [r["a"] for r in rows]
    errors = [r["se"] for r in rows]
    spread = max(values) / min(values)

    fig, ax = plt.subplots(figsize=(10.6, 5.0))
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")

    y = list(range(len(rows)))
    colors = []
    for name in names:
        if name == "HyperQwen":
            colors.append("#0d9488")
        elif name == "LM Studio":
            colors.append("#f59e0b")
        else:
            colors.append("#3b82f6")

    bars = ax.barh(y, values, height=0.52, color=colors, alpha=0.95,
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
        ax.text(bar.get_width() + row["se"] + 0.012,
                bar.get_y() + bar.get_height() / 2,
                label, va="center", ha="left", fontsize=10.5,
                color="#1a1a1a", clip_on=False)

    fig.text(0.055, 0.94, "The 4x was not the ceiling", fontsize=18,
             fontweight="bold", color="#111111", ha="left")
    fig.text(0.055, 0.885,
             "Five engines · one 27B class · one RTX 3090 · 3 and 31 October 2026",
             fontsize=10.5, color="#555555", ha="left")
    fig.text(0.055, 0.035,
             "Bars: the intercept of time-to-first-token against uncached tokens. "
             "Whiskers: one standard error.\n"
             f"{spread:.1f}x between the ends. HyperQwen: vLLM 0.31.0, base W4A16, 31 October. "
             "The other four: uncensored Q4_K_M/EXL3, 3 October.\n"
             "Same class, not the same file.",
             fontsize=8.8, color="#666666", ha="left", linespacing=1.45)

    fig.subplots_adjust(left=0.15, right=0.73, top=0.80, bottom=0.22)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, format="svg", facecolor=fig.get_facecolor(),
                metadata={"Date": None, "Creator": None})
    plt.close(fig)
    print(f"  wrote {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "pieces" / "fixed-cost-five.svg"))
    ap.add_argument("--check", action="store_true",
                    help="verify the numbers and write nothing")
    args = ap.parse_args()

    rows = compute()
    for row in rows:
        print(f"  {row['name']:10s} {row['a']:.4f} ± {row['se']:.4f} s  "
              f"{row['r']:.0f} tok/s  R²={row['r2']:.4f}  n={row['n']}")
    check(rows)
    if not args.check:
        draw(rows, Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
