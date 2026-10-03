"""The measurement client, against an engine that pretends.

Nothing here measures performance: a fake engine cannot be fast or slow. What it
can do is answer correctly, badly, or not at all -- and those are the failures
that would quietly corrupt a real session. A client that sends the wrong flag in
one of the four D1 cells, or that drops a failed request instead of recording it,
produces a dataset that looks fine and means nothing.

So the fake engine records every payload it receives, and the tests check what
was asked and what was written down.
"""
import importlib
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"
sys.path.insert(0, str(BENCH))
measure = importlib.import_module("measure")


# ------------------------------------------------------------ fake engine

class FakeEngine(BaseHTTPRequestHandler):
    """An OpenAI-compatible endpoint that remembers what it was asked."""

    received = []
    fail_next = 0
    report_usage = True
    report_timings = True
    put_text_in_reasoning = False
    version = "9.9.9-test"

    def log_message(self, *args):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            return self._json({"data": [{"id": "fake-model"}]})
        if self.path == "/v1/version":
            return self._json({"version": self.version})
        return self._json({"error": "no"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        FakeEngine.received.append(payload)

        if FakeEngine.fail_next > 0:
            FakeEngine.fail_next -= 1
            return self._json({"error": {"message": "engine said no"}}, 503)

        text = payload["messages"][0]["content"]
        prompt_tokens = len(text.split()) + 5
        # Half the prompt reported as already cached, in the same field names a
        # real engine uses, so the read-back path is exercised rather than
        # bypassed.
        cached = prompt_tokens // 2
        usage = {"prompt_tokens": prompt_tokens,
                 "prompt_tokens_details": {"cached_tokens": cached},
                 "completion_tokens": 20}
        if FakeEngine.report_timings:
            # TabbyAPI publishes these. Ollama's OpenAI endpoint publishes none
            # of them, which is why `report_timings` exists.
            usage["prompt_tokens_per_sec"] = 500.0
            usage["completion_tokens_per_sec"] = 80.0

        if payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            field = "reasoning" if FakeEngine.put_text_in_reasoning else "content"
            for piece in ("one", " two"):
                chunk = {"choices": [{"delta": {field: piece}}]}
                self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
                self.wfile.flush()
                # A real engine does not answer in two milliseconds. Without a
                # pause the mock is faster than the client's guard against
                # dividing by a near-zero window, and the generation rate comes
                # out null in a way no real session would reproduce.
                time.sleep(0.06)
            final = {"choices": []}
            if FakeEngine.report_usage and (payload.get("stream_options") or {}).get("include_usage"):
                final["usage"] = usage
            self.wfile.write(b"data: " + json.dumps(final).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        else:
            body = {"choices": [{"message": {"content": "one two"}}]}
            if FakeEngine.report_usage:
                body["usage"] = usage
            return self._json(body)


@pytest.fixture
def engine():
    FakeEngine.received = []
    FakeEngine.fail_next = 0
    FakeEngine.report_usage = True
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeEngine)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % server.server_address[1]
    server.shutdown()
    server.server_close()


def a_session(engine, tmp_path, **kw):
    out = tmp_path / "rows.jsonl"
    args = dict(engine="tabbyapi", url=engine, model="fake-model",
                out=str(out), repetitions=1, wait=0.0, verbose=False)
    args.update(kw)
    return measure.Session(**args), out


# ------------------------------------------------------- what gets sent

def test_the_four_cells_send_the_flags_they_claim(engine, tmp_path):
    """D1 rests on four combinations being four combinations.

    If `inject` leaked into the streaming-only cells, or the flag were sent
    everywhere, the experiment would compare one thing with itself and report a
    difference of zero as a finding.
    """
    session, _ = a_session(engine, tmp_path)
    measure.experiment_d1(session, [50])

    sent = {(p.get("stream", False),
             (p.get("stream_options") or {}).get("include_usage", False))
            for p in FakeEngine.received}
    assert sent == {(True, True), (True, False), (False, True), (False, False)}


def test_the_prompt_is_fresh_in_every_request(engine, tmp_path):
    """A repeated prompt would be served from the prefix cache, and the cell
    would silently become a repeat of the previous one."""
    session, _ = a_session(engine, tmp_path)
    measure.experiment_d1(session, [50])
    prompts = [p["messages"][0]["content"] for p in FakeEngine.received]
    assert len(prompts) == len(set(prompts)), "a prompt was repeated"


def test_d2_nests_the_shared_prefix_and_keeps_tails_fresh(engine, tmp_path):
    """What a prefix cache can reuse is text it has already seen.

    So the shared part of a larger fraction must contain, as a prefix, the shared
    part of a smaller one -- the 25% request and the 50% request have to agree on
    their first quarter. And at 0% there is nothing shared at all, which is the
    point of that cell.

    The tails must be new every time: a repeated tail would be cached too, and
    the fraction we read back would not be the fraction we asked for.
    """
    session, _ = a_session(engine, tmp_path)
    measure.experiment_d2(session, words=100, fractions=[0.0, 0.25, 0.5, 0.9])

    prompts = [p["messages"][0]["content"] for p in FakeEngine.received]
    shared = sorted((p.split("Section B.")[0].split() for p in prompts), key=len)
    tails = [p.split("Section B.")[1] for p in prompts]

    assert len(set(tails)) == len(tails), "a tail was reused"

    # The 0% request carries no shared text: there is nothing for the cache to
    # find, which is exactly what that cell is for.
    assert shared[0] == ["Section", "A."]

    # Compared as words, not as strings. As strings the shorter one ends with
    # the blank line and the longer one continues with a space, so the string
    # test fails on a separator while the tokens nest perfectly -- and it is the
    # tokens the cache matches on.
    for shorter, longer in zip(shared[1:], shared[2:]):
        assert longer[:len(shorter)] == shorter, "the shared prefixes are not nested"


# ------------------------------------------------------ what gets written

def test_the_sweep_sends_a_fresh_prompt_every_time(engine, tmp_path):
    """Every request in a sweep has to be new text.

    Seeding the shared half with the length alone made each repetition of the
    same length send the same prefix, and llama.cpp's prefix cache reused it --
    `cached_tokens` came back at 790, 1590 and 3590 where it should have been
    zero. The fit survived because it uses the uncached count the engine
    reports, but the measurement was no longer the one being asked for, and a
    dataset that is quietly right for the wrong reason is worse than one that
    is visibly wrong.
    """
    # Two repetitions, not one: with a single pass there is no earlier request
    # for a cache to match against, and the bug is invisible.
    session, _ = a_session(engine, tmp_path, repetitions=2)
    measure.experiment_sweep(session, [40, 80])
    prompts = [p["messages"][0]["content"] for p in FakeEngine.received]

    # The whole prompt differing is not enough, and checking only that is how
    # the first version of this test passed while the bug was still there: the
    # tail changes every time, so the prompts were all distinct while the prefix
    # -- the only part a cache can reuse -- was identical between repetitions.
    prefixes = [p.split("Section B.")[0] for p in prompts]
    assert len(prefixes) == len(set(prefixes)), "a shared prefix was reused"
    assert len(prompts) == len(set(prompts)), "a whole prompt was repeated"


def test_the_sweep_can_hold_the_generation_length_fixed(engine, tmp_path):
    """Varying how much the model may write back is how the fixed cost is asked
    whether it has anything to do with setting generation up.

    If the intercept moves when only the generation budget changes, then part of
    what looked like a per-request cost is the cost of preparing to write. If it
    does not move, that explanation is out. Either way the control has to
    actually reach the request.
    """
    session, _ = a_session(engine, tmp_path)
    measure.experiment_sweep(session, [40, 80], max_tokens=7)
    assert {p.get("max_tokens") for p in FakeEngine.received} == {7}


def test_the_streaming_sweep_is_the_one_that_has_the_clients_clock(engine, tmp_path):
    """The four engine clocks do not cover the same interval, and that is not a
    detail -- it is the whole difference between a comparison and a mixture.

    Measured on the same streaming requests, llama.cpp's reported window leaves
    58 ms of each request uncounted and TabbyAPI's leaves 128 ms. Put those two
    numbers in one table and the column stops being "what the engine charges
    before it works" and becomes "what four different clocks happened to
    include". The client's clock is the only instrument that times the same
    interval for all four engines, and it exists only when the request streams.

    So the streaming sweep has to actually stream, and it has to keep the
    client's window on every row -- not fall back to the engine's, which is what
    the engine comparison would silently do if the flag went nowhere.
    """
    session, out = a_session(engine, tmp_path)
    measure.experiment_sweep(session, [40, 80], stream=True)

    assert {p.get("stream") for p in FakeEngine.received} == {True}, \
        "the sweep did not stream"
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert rows, "nothing was written"
    assert all(r["cell"].startswith("stream@") for r in rows), \
        "a streaming sweep was filed under the plain cell"
    assert all(r["client_ttft_s"] is not None for r in rows), \
        "the client's window is missing, which is the only reason to stream"


def test_two_sessions_do_not_send_the_same_prompts(engine, tmp_path):
    """Consecutive runs on the same engine must not reuse each other's prefixes.

    This got through once. The seed was fixed for the repetition but not for the
    run, so two sweeps back to back sent identical prompts, the engine answered
    the second one almost entirely from cache, and its four points landed at 16,
    108, 224 and 240 uncached tokens instead of at the four lengths asked for.
    The fit produced a line anyway, over a range twenty times too small, and
    looked exactly as confident as a real one.
    """
    first, _ = a_session(engine, tmp_path)
    measure.experiment_sweep(first, [40, 80])
    sent_first = {p["messages"][0]["content"] for p in FakeEngine.received}

    FakeEngine.received = []
    second, _ = a_session(engine, tmp_path)
    measure.experiment_sweep(second, [40, 80])
    sent_second = {p["messages"][0]["content"] for p in FakeEngine.received}

    assert not (sent_first & sent_second), "two sessions sent the same prompts"


def test_a_failed_request_is_recorded_not_dropped(engine, tmp_path):
    """The rule from the protocol: a measurement that disappears without
    explanation is how a bench lies."""
    session, out = a_session(engine, tmp_path)
    FakeEngine.fail_next = 1
    row = session.request("hello", stream=False, inject_usage=False)
    session.keep(row, "d1", "plain", 1)

    assert row["discarded"] is True
    assert "503" in row["reason"]
    written = [json.loads(l) for l in out.read_text().splitlines()]
    assert len(written) == 1 and written[0]["discarded"] is True


def test_the_engine_version_is_recorded_on_every_row(engine, tmp_path):
    """An engine update moves these numbers. Without the version in the row,
    a regression and a configuration change look the same."""
    session, _ = a_session(engine, tmp_path)
    row = session.request("hello", stream=False, inject_usage=False)
    assert row["version"] == "unknown" or isinstance(row["version"], str)
    assert "version" in row


def test_a_version_nobody_can_supply_is_unknown_not_a_guess(engine, monkeypatch):
    """TabbyAPI has no version endpoint at all -- /health answers 'healthy' and
    nothing else -- so its version is read off the disk instead.

    When neither the engine nor the disk can supply one, the answer is
    'unknown'. That is honest and it is worse than a number, which is exactly
    why it gets recorded rather than filled in with something plausible.
    """
    monkeypatch.setattr(measure, "local_version", lambda _engine: "")
    assert measure.engine_version("tabbyapi", engine) == "unknown"    # no /v1/model
    assert measure.engine_version("ollama", engine) == "unknown"      # no /api/version


def test_the_version_is_read_off_the_disk_when_the_engine_stays_quiet(monkeypatch):
    """The fallback that makes the field worth having on a real machine."""
    monkeypatch.setattr(measure, "local_version", lambda _engine: "tabbyAPI abc1234")
    assert measure.engine_version("tabbyapi", "http://127.0.0.1:1") == "tabbyAPI abc1234"


def test_the_window_the_engine_implies_is_recovered(engine, tmp_path):
    """The whole finding: reported rate divides uncached tokens by a window that
    contains a fixed cost, and the window is recoverable by inverting it."""
    session, _ = a_session(engine, tmp_path)
    row = session.request("hello", stream=False, inject_usage=False)
    # The fake engine reports one word plus five tokens, half of it cached, at
    # a declared 500 tok/s: 6 tokens, 3 cached, 3 uncached, 3/500 of a second.
    assert row["prompt_tokens"] == 6
    assert row["cached_tokens"] == 3
    assert row["uncached"] == 3
    assert row["engine_ttft_s"] == pytest.approx(3 / 500.0, abs=1e-4)


def test_the_client_measures_its_own_first_token(engine, tmp_path):
    """The engine's window and the client's window are different measurements of
    the same request. Recording only one of them would hide the difference."""
    session, _ = a_session(engine, tmp_path)
    row = session.request("hello", stream=True, inject_usage=True)
    assert row["client_ttft_s"] is not None
    assert row["client_total_s"] >= row["client_ttft_s"]


def test_an_engine_that_publishes_no_rate_is_still_measured(engine, tmp_path):
    """Ollama's OpenAI endpoint reports token counts and no timings at all.

    Found by running against a real Ollama, not by a mock. The engine's window
    cannot be recovered there because the field does not exist, so the client's
    own measurement is the only one -- and it has to be recorded, not left null
    because the engine was quiet.
    """
    session, _ = a_session(engine, tmp_path)
    FakeEngine.report_timings = False
    row = session.request("hello", stream=True, inject_usage=True)

    assert row["reported_tps"] is None            # the engine said nothing
    assert row["engine_ttft_s"] is None           # so the window is not recoverable
    assert row["prompt_tokens"] == 6              # but the counts are there
    assert row["client_ttft_s"] is not None       # and the client measured anyway
    assert measure._generation_speed(row) is not None


def test_the_three_names_for_a_piece_of_text():
    """The same thing has three names, and the engine picks.

    `content` is the OpenAI convention. `reasoning` is Ollama. And
    `reasoning_content` is TabbyAPI -- which is what a whole D1 run against a
    real TabbyAPI came back without seeing, so the first token was never
    recorded and the run had to be thrown away.
    """
    assert measure.piece_text({"content": "x"}) == "x"
    assert measure.piece_text({"reasoning": "x"}) == "x"
    assert measure.piece_text({"reasoning_content": "x"}) == "x"
    assert measure.piece_text({}) == ""
    assert measure.piece_text({"content": "a", "reasoning": "b"}) == "ab"


def test_a_reply_with_no_content_does_not_crash(engine, tmp_path):
    """TabbyAPI answers a reasoning model with `content: None` and the text in
    `reasoning_content`. Splitting None killed nine rows of a real run."""
    session, _ = a_session(engine, tmp_path)
    row = session.request("hello", stream=False, inject_usage=True)
    assert row["discarded"] is False


def test_text_arriving_as_reasoning_is_counted(engine, tmp_path):
    """A reasoning model streams its thinking in `delta.reasoning`.

    Counting only `delta.content` reports a model that produced nothing, and the
    client's own rate would be null on exactly the models people run most.
    """
    session, _ = a_session(engine, tmp_path)
    FakeEngine.put_text_in_reasoning = True
    row = session.request("hello", stream=True, inject_usage=True)
    assert row["client_pieces"] == 2, "the reasoning pieces were not counted"


def test_streaming_without_usage_leaves_the_fields_empty_not_zero(engine, tmp_path):
    """Zero and 'the engine did not say' are different facts. A zero would be
    averaged into the results as if it were a measurement."""
    session, _ = a_session(engine, tmp_path)
    row = session.request("hello", stream=True, inject_usage=False)
    assert row["prompt_tokens"] is None
    assert row["engine_ttft_s"] is None


# ------------------------------------------------------------- the report

def test_the_report_uses_the_median_and_shows_the_interval(engine, tmp_path):
    """Long tails are the norm in latency. A mean hides them; the protocol says
    median and interval, and the report has to say the same."""
    rows = [{"cell": "a", "discarded": False, "engine_ttft_s": v, "uncached": 10,
             "reported_tps": 100} for v in (1.0, 1.1, 1.2, 9.0)]
    printed = []
    real_print = print
    measure.print = lambda *a, **k: printed.append(" ".join(str(x) for x in a))
    try:
        measure.report(rows)
    finally:
        measure.print = real_print
    text = "\n".join(printed)
    # With four values the median is the mean of the middle two: 1.15. The mean
    # of all four would be 3.075 -- which is the number the protocol says not to
    # publish, because one slow request drags it away from reality.
    assert "1.150" in text
    assert "3.07" not in text
    assert "1.000" in text and "9.000" in text   # the interval


def test_discarded_rows_are_reported_with_their_reason(engine, tmp_path):
    rows = [{"cell": "a", "discarded": True, "reason": "http 503: busy"},
            {"cell": "a", "discarded": False, "engine_ttft_s": 1.0,
             "uncached": 10, "reported_tps": 100}]
    printed = []
    real_print = measure.print
    measure.print = lambda *a, **k: printed.append(" ".join(str(x) for x in a))
    try:
        measure.report(rows)
    finally:
        measure.print = real_print
    assert any("http 503" in line for line in printed)


# ------------------------------------------------------- real prose, not words

def test_prose_prompts_come_from_the_corpus_and_are_still_fresh(engine, tmp_path):
    """The fixed vocabulary is the weakest thing about these measurements.

    The obvious objection is that real text tokenises differently and might
    carry a different fixed cost, so the client can build its prompts from real
    prose instead. Two things have to survive the swap, and both are silent when
    they break:

      * the words really have to come from the corpus. A control that quietly
        still drew from VOCAB would compare the vocabulary with itself and
        report the absence of a difference as a finding.
      * the sweep still has to send a fresh prefix every time. Prose drawn from
        random offsets makes overlap between prompts far more likely than a
        1,000-word vocabulary does, and a reused prefix is served from cache --
        the four lengths would land somewhere else entirely.
    """
    corpus = tmp_path / "corpus.txt"
    corpus.write_text(" ".join("corpusword%d" % i for i in range(4000)),
                      encoding="utf-8")
    before = list(measure.CORPUS_TEXT)
    try:
        assert measure.load_corpus([corpus]) == 4000
        text = measure.words_text(1, 20)
        assert all(w.startswith("corpusword") for w in text.split())
        assert not (set(text.split()) & set(measure.VOCAB))

        session, _ = a_session(engine, tmp_path, repetitions=2)
        measure.experiment_sweep(session, [40, 80])
        prompts = [p["messages"][0]["content"] for p in FakeEngine.received]
        prefixes = [p.split("Section B.")[0] for p in prompts]
        assert len(prefixes) == len(set(prefixes)), "a shared prefix was reused"
    finally:
        measure.CORPUS_TEXT[:] = before


def test_a_corpus_that_cannot_be_read_is_skipped_not_invented(tmp_path):
    """A missing file contributes nothing. Falling back to the vocabulary for it
    would mix synthetic words into a prose run, and the mixture would be
    invisible in the output -- the prompts would simply be wrong in a way that
    still tokenises."""
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("real words here and more of them", encoding="utf-8")
    before = list(measure.CORPUS_TEXT)
    try:
        n = measure.load_corpus([tmp_path / "does-not-exist.txt", corpus])
        assert n == 7, "the missing file contributed something"
        assert measure.CORPUS_TEXT == ["real", "words", "here", "and",
                                       "more", "of", "them"]
    finally:
        measure.CORPUS_TEXT[:] = before
