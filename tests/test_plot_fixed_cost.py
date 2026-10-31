"""The picture and the piece have to say the same thing.

A chart is a number with a nice outfit: it is exactly as capable of drifting as
a sentence. These tests compute the four fits from the committed rows, refuse a
picture whose numbers have moved away from the published table, and make sure
the README actually shows it.
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
import plot_fixed_cost as P


def test_the_four_fits_are_the_published_ones():
    rows = P.compute()
    assert [r["name"] for r in rows] == ["Ollama", "llama.cpp", "TabbyAPI", "LM Studio"]
    P.check(rows)  # SystemExit if an intercept or an error bar has moved
    assert rows[-1]["a"] / rows[0]["a"] > 3.9


def test_the_check_can_actually_fail():
    rows = P.compute()
    rows[0] = dict(rows[0], a=rows[0]["a"] + 0.01)
    with pytest.raises(SystemExit):
        P.check(rows)


def test_the_svg_is_well_formed_and_names_the_four():
    path = ROOT / "pieces" / "fixed-cost.svg"
    ET.parse(path)
    text = path.read_text(encoding="utf-8")
    for name in P.EXPECTED:
        assert name in text


def test_the_readme_shows_the_picture():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "pieces/fixed-cost.svg" in readme
