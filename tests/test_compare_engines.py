"""compare_engines, on rows written by hand.

The defect this file exists to catch was silent. The first version took
whichever clock a row happened to carry and fell back from the engine's to the
client's without saying so -- so two engines timed by two different stopwatches
were fitted and printed in one column, and the column read as "what the engine
charges before it works" while actually being "what four different clocks
happened to include". Nothing in the output looked wrong, which is why it needs
a test rather than a careful reading.

The numbers are toy numbers. What is being checked is which rows go into which
fit, and whether a clock that is not there stays not there.
"""
import importlib
import json
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"
sys.path.insert(0, str(BENCH))
C = importlib.import_module("compare_engines")


def rows_for(clock, points, cell="plain"):
    """One row per (uncached tokens, window) pair, carrying one clock."""
    rows = []
    for n, window in points:
        row = {"cell": cell, "discarded": False, "uncached": n, "prompt_tokens": n}
        if clock:
            row[clock] = window
        rows.append(row)
    return rows


def test_a_clock_that_is_absent_stays_absent():
    """This is the bug. A row with only the engine's clock must produce no
    client-clock fit -- not a client-clock fit quietly built from the engine's
    numbers, which is what the fallback did and what makes two engines
    incomparable while looking comparable."""
    rows = rows_for("engine_ttft_s", [(10, 0.2), (20, 0.3), (30, 0.4)])

    engine = C.line_for(rows, "plain", "engine_ttft_s")
    assert engine["a"] == pytest.approx(0.1, abs=1e-9)
    assert C.line_for(rows, "plain", "client_ttft_s") is None


def test_one_set_of_requests_can_be_fitted_on_both_clocks():
    """A streamed row carries both clocks, and that is the entire point of the
    streaming sweep: the same requests, two stopwatches, so the difference
    between the two fits is the difference between the instruments and nothing
    else."""
    rows = []
    for n in (10, 20, 30):
        rows.append({"cell": "stream", "discarded": False, "uncached": n,
                     "prompt_tokens": n,
                     "engine_ttft_s": 0.1 + n * 0.01,
                     "client_ttft_s": 0.2 + n * 0.01})

    engine = C.line_for(rows, "stream", "engine_ttft_s")
    client = C.line_for(rows, "stream", "client_ttft_s")
    assert engine["a"] == pytest.approx(0.1, abs=1e-9)
    assert client["a"] == pytest.approx(0.2, abs=1e-9)
    assert C._gap(engine, client) == "+0.100 s"


def test_the_gap_says_nothing_rather_than_zero_when_a_clock_is_missing():
    """A missing clock is not a gap of zero. Printing 0.000 s would read as
    "this engine's clock covers everything", which is a claim the data is not
    making."""
    assert C._gap(None, {"a": 0.2}) == "--"
    assert C._gap({"a": 0.1}, None) == "--"
    assert C._cell(None) == "-- not on this clock"


def test_a_discarded_request_never_reaches_a_fit():
    """The protocol's rule: a request that failed is recorded, not measured."""
    rows = rows_for("engine_ttft_s", [(10, 0.2), (20, 0.3), (30, 0.4)])
    rows.append({"cell": "plain", "discarded": True, "uncached": 40,
                 "prompt_tokens": 40, "engine_ttft_s": 99.0, "reason": "http 503"})
    fit = C.line_for(rows, "plain", "engine_ttft_s")
    assert fit["a"] == pytest.approx(0.1, abs=1e-9)
    assert fit["shortest"] == 10


def test_a_cell_matches_its_lengths_and_not_its_neighbours():
    """"stream+inject" starts with "stream", so a prefix match that is not
    anchored on the separator lets a fit labelled `stream` absorb the
    `stream+inject` rows and report a line belonging to neither."""
    rows = (rows_for("engine_ttft_s", [(10, 0.2), (20, 0.3), (30, 0.4)], "stream@10")
            + rows_for("engine_ttft_s", [(10, 9.0), (20, 9.0), (30, 9.0)], "stream+inject"))
    fit = C.line_for(rows, "stream", "engine_ttft_s")
    assert fit["a"] == pytest.approx(0.1, abs=1e-9), "the other cell leaked in"


def a_run(tmp_path, name, engine, gap, tail=1.0):
    """A file of readable rows for one engine, with a chosen clock gap.

    `tail` is how many seconds of reply kept arriving after the first chunk. At
    1.0 the engine is streaming; at 0.0 the first chunk was also the last.
    """
    path = tmp_path / name
    lines = []
    for n in (100, 500, 2000):
        ttft = 0.10 + gap + n * 0.001
        lines.append(json.dumps({
            "engine": engine, "model": "m", "version": "test",
            "cell": "stream@%d" % n, "discarded": False,
            "uncached": n, "prompt_tokens": n,
            "engine_ttft_s": 0.10 + n * 0.001,
            "client_ttft_s": ttft,
            "client_total_s": ttft + tail,
        }))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def run_verdict(monkeypatch, paths):
    printed = []
    monkeypatch.setattr(sys, "argv", ["compare_engines.py"] + paths + ["--cell", "stream"])
    monkeypatch.setattr(C, "print",
                        lambda *a, **k: printed.append(" ".join(str(x) for x in a)),
                        raising=False)
    assert C.main() == 0
    return "\n".join(printed)


def test_two_engines_timed_by_different_stopwatches_are_flagged(tmp_path, monkeypatch):
    """The verdict has to refuse the comparison, because the numbers would look
    perfectly reasonable. Two engines with identical engine-clock intercepts and
    gaps of 60 ms and 180 ms are not the same engine measured twice -- they are
    two engines measured by two stopwatches, and the engine-clock column would
    say they are identical.
    """
    paths = [a_run(tmp_path, "a.jsonl", "alpha", 0.06),
             a_run(tmp_path, "b.jsonl", "beta", 0.18)]
    text = run_verdict(monkeypatch, paths)
    assert "not the same instrument" in text
    assert "client's clock is one clock" in text


def test_engines_whose_clocks_agree_are_not_flagged(tmp_path, monkeypatch):
    """The opposite failure: a tool that always cries confound is a tool nobody
    reads. Gaps of 60 and 65 ms are the same instrument within noise, and the
    verdict has to say so rather than hedge."""
    paths = [a_run(tmp_path, "a.jsonl", "alpha", 0.060),
             a_run(tmp_path, "b.jsonl", "beta", 0.065)]
    text = run_verdict(monkeypatch, paths)
    assert "not the same instrument" not in text
    assert "either column will do" in text


def test_an_engine_that_buffers_its_reply_is_caught(tmp_path, monkeypatch):
    """The client's clock is a time to first token only if the engine streams.

    An engine that sends the whole answer in one chunk makes the client's "first
    token" the entire response. That number would sit in the ranking column
    looking exactly like a prefill window -- and it would be the one engine in
    the table measured end to end, standing next to three that are not. What
    catches it is the tail: a buffered reply has nothing left to arrive.
    """
    paths = [a_run(tmp_path, "a.jsonl", "alpha", 0.06, tail=1.0),
             a_run(tmp_path, "b.jsonl", "beta", 0.06, tail=0.0)]
    text = run_verdict(monkeypatch, paths)
    assert "do not stream" in text
    assert "beta" in text
    assert "must not be ranked on it" in text


def test_a_long_prefill_is_not_mistaken_for_buffering(tmp_path, monkeypatch):
    """The first metric here was the fraction of the reply that had arrived at
    the first chunk, and it measured the prompt instead of the engine.

    On a 4,000-token prompt the prefill is most of the wall time, so a perfectly
    streaming engine shows a high fraction -- LM Studio reached 0.81 on a 681
    tok/s prefill that matches its own reported rate exactly. Calling that
    buffered would discard a good measurement. The tail tells them apart, which
    is why the tail is what the guard reads.
    """
    paths = [a_run(tmp_path, "a.jsonl", "alpha", 0.06, tail=1.4),
             a_run(tmp_path, "b.jsonl", "beta", 0.06, tail=2.1)]
    # Give these rows the shape that broke the old metric: a first chunk very
    # late in a long reply.
    for name in ("a.jsonl", "b.jsonl"):
        path = tmp_path / name
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row["client_ttft_s"] = 6.0
            row["client_total_s"] = 7.4
            rows.append(json.dumps(row))
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    text = run_verdict(monkeypatch, paths)
    assert "do not stream" not in text


def test_two_files_for_one_engine_are_flagged_rather_than_fused(tmp_path, monkeypatch):
    """Rows are grouped by (engine, model), so two runs of the same engine and
    the same model become one row -- a fit over both of them together, printed
    in the shape of a single measurement.

    This bit while writing the piece. The 64k sweep and the 32k sweep of LM
    Studio carry the same engine and the same model, were handed over together,
    and came back as one line that was then quoted as the 32k result. The
    docstring had warned about it since the first version; a warning that lives
    in a docstring is not read at the moment it matters, so it is a line of
    output.
    """
    paths = [a_run(tmp_path, "a.jsonl", "alpha", 0.06),
             a_run(tmp_path, "b.jsonl", "alpha", 0.06)]
    text = run_verdict(monkeypatch, paths)
    assert "POOLED" in text
    assert "a.jsonl" in text and "b.jsonl" in text


def test_one_file_per_engine_is_not_flagged(tmp_path, monkeypatch):
    """The ordinary case has to stay quiet, or the flag stops meaning
    anything."""
    paths = [a_run(tmp_path, "a.jsonl", "alpha", 0.06),
             a_run(tmp_path, "b.jsonl", "beta", 0.06)]
    text = run_verdict(monkeypatch, paths)
    assert "POOLED" not in text


def test_two_lengths_are_not_enough_to_pin_an_intercept():
    """Two points always fit a line exactly, so the fit would report a perfect
    R2 and a standard error of zero for an intercept it cannot support. This is
    the mistake the project criticises in its own earlier work, and the guard
    belongs in the code rather than in the habit of whoever runs it."""
    rows = rows_for("engine_ttft_s", [(10, 0.2), (20, 0.3)])
    assert C.line_for(rows, "plain", "engine_ttft_s") is None
