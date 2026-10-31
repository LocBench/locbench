"""The fifth engine: two sessions, five engines, one table.

The D4 result is a boundary result, so the checks are about the two things that
could make it look more certain than it is: a single fast session, and a table
that quietly drops the caveat. The two sessions have to agree; the five-engine
spread has to be larger than the four-engine one; the README has to show the
five-engine chart, not the old one.
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
import plot_fixed_cost_five as P5

FILES = [
    ROOT / "data" / "2026-10-31-stream-hyperqwen.jsonl",
    ROOT / "data" / "2026-10-31-stream-hyperqwen-2.jsonl",
]


def test_the_two_sessions_agree_within_the_error():
    rows = P5.compute()
    hyper = next(row for row in rows if row["name"] == "HyperQwen")
    assert len(hyper["sessions"]) == 2
    a, b = [s["a"] for s in hyper["sessions"]]
    assert abs(a - b) < 0.01
    assert 0.045 <= hyper["a"] <= 0.060
    assert hyper["se"] < 0.005


def test_the_five_engine_spread_is_larger_than_the_four():
    rows = P5.compute()
    P5.check(rows)  # SystemExit if a number moved
    by = {row["name"]: row["a"] for row in rows}
    assert by["HyperQwen"] == min(by.values())
    assert by["LM Studio"] == max(by.values())
    assert by["LM Studio"] / by["HyperQwen"] > 7.5
    assert by["LM Studio"] / by["Ollama"] < 4.1


def test_the_raw_rows_are_the_engine_and_the_model_with_no_discards():
    for path in FILES:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        assert len(rows) == 21
        assert not any(row.get("discarded") for row in rows)
        assert {row["version"] for row in rows} == {"HyperQwen / vLLM 0.31.0"}
        assert {row["model"] for row in rows} == {"qwen3.8-27b"}
        assert all(row["stream"] for row in rows)


def test_the_check_can_actually_fail():
    rows = P5.compute()
    for row in rows:
        if row["name"] == "HyperQwen":
            row["a"] = row["a"] + 0.01
    with pytest.raises(SystemExit):
        P5.check(rows)


def test_the_svg_is_well_formed_and_names_the_five():
    path = ROOT / "pieces" / "fixed-cost-five.svg"
    ET.parse(path)
    text = path.read_text(encoding="utf-8")
    for name in ("HyperQwen", "Ollama", "llama.cpp", "TabbyAPI", "LM Studio"):
        assert name in text


def test_the_readme_uses_the_five_engine_chart():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "pieces/fixed-cost-five.svg" in readme
    assert "pieces/03-the-4x-was-not-the-ceiling.md" in readme
