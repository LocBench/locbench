"""The bench's arithmetic, verified against known cases.

The protocol promises that every number is redone with one command. A command
that gets the arithmetic wrong is worse than no command: this checks that the
least squares find what they should, that unusable rows are dropped, and that
the fit on the real 2 October 2026 data still returns those numbers.

The last tests are regressions against the committed data: they are how the
bench notices that it has changed.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bench"))
import importlib

A = importlib.import_module("analyze_log")

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "2026-10-02-usage.jsonl"


# ------------------------------------------------------------- i conti

def test_ols_recovers_an_exact_line():
    x = [0.0, 1.0, 2.0, 3.0, 4.0]
    y = [3.0 + 2.0 * v for v in x]
    beta, r2, n = A.ols([[1.0] * len(x), x], y)
    assert n == 5
    assert beta[0] == pytest.approx(3.0)
    assert beta[1] == pytest.approx(2.0)
    assert r2 == pytest.approx(1.0)


def test_ols_rejects_collinear_columns():
    """If two predictors are the same thing, the model is not estimable:
    it must say so, not return an invented number."""
    x = [1.0, 2.0, 3.0, 4.0]
    assert A.ols([[1.0] * 4, x, [2.0 * v for v in x]], [1.0, 2.0, 3.0, 4.0]) is None


def test_fit_recovers_intercept_and_slope():
    points = [{"uncached": float(x), "ttft_s": 0.5 + x / 1000.0}
             for x in (0, 250, 500, 1000, 2000, 4000)]
    r = A.fit(points)
    assert r["n"] == 6
    assert r["intercept_s"] == pytest.approx(0.5)
    assert r["tps"] == pytest.approx(1000.0)
    assert r["r2"] == pytest.approx(1.0)


def test_fit_rejects_too_few_points():
    assert A.fit([{"uncached": 1.0, "ttft_s": 1.0}]) is None


# -------------------------------------------------------- the filter

def test_usable_drops_incomplete_rows():
    rows = [
        {"prompt_tokens": 100, "cached_tokens": 0, "prompt_tps": 100.0},      # a good row
        {"prompt_tokens": 100, "prompt_tps": 100.0},                          # cache missing
        {"prompt_tokens": 100, "cached_tokens": 0},                           # tps missing
        {"prompt_tokens": 100, "cached_tokens": 100, "prompt_tps": 100.0},    # all in cache
        {"prompt_tokens": 0, "cached_tokens": 0, "prompt_tps": 100.0},        # empty
        {"prompt_tokens": 100, "cached_tokens": 0, "prompt_tps": 0},          # tps nullo
    ]
    assert len(A.usable(rows)) == 1


def test_usable_inverts_the_metric():
    """tempo_prefill = (prompt_tokens - cached_tokens) / prompt_tps."""
    p, = A.usable([{"prompt_tokens": 1000, "cached_tokens": 600, "prompt_tps": 200.0}])
    assert p["uncached"] == 400.0
    assert p["ttft_s"] == pytest.approx(2.0)


def test_observed_time_subtracts_generation():
    r = {"wall_s": 10.0, "completion_tokens": 500, "completion_tps": 100.0}
    assert A._observed(r) == pytest.approx(5.0)


def test_observed_time_handles_a_row_without_wall():
    assert A._observed({"wall_s": None}) is None


def test_read_counts_broken_lines(tmp_path):
    f = tmp_path / "log.jsonl"
    f.write_text('{"a": 1}\n\n{broken\n{"a": 2}\n', encoding="utf-8")
    rows, rotte = A.read(str(f))
    assert len(rows) == 2
    assert rotte == 1


def test_discards_report_the_reason():
    """Rule 5: discarded measurements are recorded with the reason."""
    rows = [
        {"prompt_tokens": 100, "cached_tokens": 0, "prompt_tps": 100.0},        # a good row
        {"status": 503},                                                        # failed
        {"status": 200},                                                        # no usage block
        {"status": 200, "prompt_tokens": 100, "prompt_tps": 100.0},             # cache missing
        {"status": 200, "prompt_tokens": 100, "cached_tokens": 100,
         "prompt_tps": 100.0},                                                  # all in cache
    ]
    s = A.discards(rows)
    assert sum(s.values()) == 4
    assert s["request failed (status 503)"] == 1
    assert s["the engine returned no usage block"] == 1
    assert s["cached_tokens is missing"] == 1
    assert s["no uncached tokens (it was all in cache)"] == 1


# ------------------------------------------ the real 2 October 2026 data

def test_usable_and_discards_add_up_to_the_total():
    """The two lists cannot diverge: they come from the same decision."""
    rows, _ = A.read(str(SNAPSHOT))
    assert len(A.usable(rows)) + sum(A.discards(rows).values()) == len(rows)

def test_the_snapshot_census():
    rows, rotte = A.read(str(SNAPSHOT))
    assert rotte == 0
    assert len(rows) == 98
    # 98 logged, 87 with a recoverable window: the rest carry no usage
    assert len(A.usable(rows)) == 87


def test_the_fit_still_holds():
    rows, _ = A.read(str(SNAPSHOT))
    r = A.fit(A.usable(rows))
    assert r["n"] == 87
    assert r["intercept_s"] == pytest.approx(0.447, abs=0.005)
    assert r["tps"] == pytest.approx(943, abs=3)
    assert r["r2"] == pytest.approx(0.953, abs=0.001)


def test_the_cache_does_not_explain_the_fixed_cost():
    """The hypothesis 'the cached prefix is what costs' was killed: adding
    cached_tokens to the model gains a thousandth of R2."""
    rows, _ = A.read(str(SNAPSHOT))
    g = [p for p in A.usable(rows) if p["stream"]]
    y = [p["ttft_s"] for p in g]
    without_cache = A.ols([[1.0] * len(y), [p["uncached"] for p in g]], y)
    with_cache = A.ols([[1.0] * len(y), [p["uncached"] for p in g],
                    [p["cached_tokens"] for p in g]], y)
    assert with_cache[1] - without_cache[1] < 0.01


def test_stream_and_injected_are_the_same_partition():
    """Why this data cannot answer D1.

    There is not a single non-streaming request that is not also injected:
    the comparison group is defined by the injection, not by the streaming.
    """
    rows, _ = A.read(str(SNAPSHOT))
    points = A.usable(rows)
    assert not [p for p in points if not p["stream"] and not p["injected"]]
    crosstab = {(p["stream"], p["injected"]) for p in points}
    assert (True, False) in crosstab
    assert (False, True) in crosstab
