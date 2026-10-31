"""The environment card and the rows have to name the same engines.

The b11256 bug is the reason this file exists: the protocol's card said one
llama.cpp, 375 rows of committed data said another, and every gate was green.
A number is not checked by being written next to a version; it is checked when
something compares the two.
"""
import glob
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def protocol_row():
    text = (ROOT / "PROTOCOL.md").read_text(encoding="utf-8")
    m = re.search(r"^\| Engines \| (.+) \|$", text, re.M)
    assert m, "the protocol has no '| Engines |' row"
    return m.group(1)


def campaign_versions():
    """(engine, version) for the controlled campaign of 3 October."""
    seen = set()
    for path in glob.glob(str(ROOT / "data" / "2026-10-03-*.jsonl")):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("engine") and row.get("version"):
                seen.add((row["engine"], str(row["version"])))
    return seen


def check_row(row, versions):
    """Every engine version in the rows has to appear in the card."""
    for engine, version in versions:
        if engine == "llamacpp":
            m = re.fullmatch(r"(b\d+)-([0-9a-f]+)", version)
            assert m, f"unexpected llama.cpp version string: {version}"
            assert m.group(1) in row, f"{m.group(1)} is in the data, not in the card"
            assert m.group(2) in row, f"{m.group(2)} is in the data, not in the card"
        elif engine == "tabbyapi":
            m = re.search(r"tabbyAPI ([0-9a-f]+), exllamav3 ([0-9.]+)", version)
            assert m, f"unexpected TabbyAPI version string: {version}"
            assert m.group(1) in row, f"{m.group(1)} is in the data, not in the card"
            assert f"exllamav3 {m.group(2)}" in row, (
                f"exllamav3 {m.group(2)} is in the data, not in the card")
        else:
            assert version in row, f"{version} is in the data, not in the card"


def test_the_card_names_the_versions_in_the_rows():
    versions = campaign_versions()
    assert {engine for engine, _ in versions} == {
        "ollama", "llamacpp", "lmstudio", "tabbyapi"}
    check_row(protocol_row(), versions)


def test_the_check_can_actually_fail():
    row = protocol_row().replace("b427", "b11256")
    with pytest.raises(AssertionError):
        check_row(row, campaign_versions())
