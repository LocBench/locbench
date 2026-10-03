#!/usr/bin/env python3
"""measure.py — the client that runs the controlled measurements.

The analysis in `analyze_log.py` works on data that was collected by accident.
This tool collects data on purpose, one variable at a time, and records the
engine version with every row -- because an engine update moves the numbers, and
without the version there is no way to tell a regression from a difference in
configuration.

Three experiments, as defined in PROTOCOL.md:

  d1  the same prompt length in four cells: streaming or not, crossed with the
      telemetry flag present or not. This is the one that decides whether the
      fixed cost belongs to streaming, to the flag, or to the client.
  d2  a prefix of length L, sent repeatedly with a varying fraction already in
      the cache. The cached fraction is not imposed, it is asked for and read
      back: what the engine reports is the measurement, what we requested is
      only the request.
  d3  the same sweep across engines.

    python3 bench/measure.py --engine ollama --model qwen3.8-27b-64k d1
    python3 bench/measure.py --engine tabbyapi --model qwen3.8-27b-4.0bpw d2

Two disciplines are built into the tool rather than left to the operator:

  * warm-up is discarded. Nothing is recorded until five consecutive requests
    land within 5% of each other, because the first requests of a session pay
    for a cold model and cold kernels.
  * a row that looks wrong is not deleted, it is annotated. Every row carries
    `discarded` and `reason`; a measurement that vanishes without explanation is
    how a bench lies.

Standard library only.
"""
import argparse
import json
import os
import random
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Where each engine listens by default, and where it will say what version it
# is. The path differs per engine; the request shape is the engine's business,
# not ours.
ENGINES = {
    "tabbyapi": {"url": "http://127.0.0.1:8091", "version": "/v1/model"},
    "llamacpp": {"url": "http://127.0.0.1:8090", "version": "/props"},
    "lmstudio": {"url": "http://127.0.0.1:1234", "version": "/v1/models"},
    "ollama":   {"url": "http://127.0.0.1:11434", "version": "/api/version"},
}

# A small vocabulary for building prompts of a controlled size. Words are short
# and common so that the token count stays close to the word count.
VOCAB = (
    "the of and to a in that is was he for it with as his on be at by had this "
    "have from or one but not what all were when we there can an your which do "
    "how their if will up other about out many then them these so some her would "
    "make like him into time has look two more write go see number no way could "
    "people my than first water been call who oil its now find long down day did "
    "get come made may part over new sound take only little work know place year "
    "live me back give most very after thing our just name good sentence man think"
).split()


# --------------------------------------------------------------- transport

def post_json(url, payload, timeout=600):
    """A request that returns (status, parsed_body, raw_text)."""
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": "locbench-measure/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, _maybe_json(raw), raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        return exc.code, _maybe_json(raw), raw


def get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "locbench-measure/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, _maybe_json(resp.read().decode("utf-8", "replace"))
    except Exception:
        return 0, None


def _maybe_json(raw):
    try:
        return json.loads(raw)
    except Exception:
        return None


def stream_json(url, payload, timeout=600):
    """A streaming request, timed by the client.

    Returns (first_token_at, last_token_at, pieces, usage, started_at).

    Two things learned from a real engine rather than from a mock. Pieces of
    text arrive in `delta.content` **or** `delta.reasoning` -- a reasoning model
    streams its thinking in a separate field, and counting only `content` would
    report a model that produced nothing. And a chunk is not a token: the count
    here is of pieces received, which is why the engine's own token count is
    recorded next to it rather than replaced by it.

    `first_token_at` is the client's view of time to first token. It is the only
    view available for engines that publish no timing of their own, and a
    cross-check for the ones that do.
    """
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": "locbench-measure/1.0"})
    started = time.perf_counter()
    first = last = None
    pieces = 0
    usage = None
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            obj = _maybe_json(data)
            if not isinstance(obj, dict):
                continue
            if obj.get("usage"):
                usage = obj["usage"]
            for choice in (obj.get("choices") or []):
                delta = choice.get("delta") or {}
                text = (delta.get("content") or "") + (delta.get("reasoning") or "")
                if not text:
                    continue
                now = time.perf_counter()
                first = first if first is not None else now
                last = now
                pieces += 1
    return first, last, pieces, usage, started


# ------------------------------------------------------------- the engines

def engine_version(engine, url):
    """What version the engine says it is.

    Returns a string, or 'unknown' -- and 'unknown' is a real answer that gets
    recorded. Guessing a version would be worse than not having one.
    """
    path = ENGINES.get(engine, {}).get("version")
    if not path:
        return "unknown"
    status, body = get_json(url.rstrip("/") + path)
    if status != 200 or not isinstance(body, dict):
        return "unknown"
    for key in ("version", "build_info", "build", "model_version"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    # llama.cpp reports the build inside `build_info`; some builds nest it
    for value in body.values():
        if isinstance(value, dict):
            for key in ("version", "build_info", "build"):
                inner = value.get(key)
                if isinstance(inner, str) and inner:
                    return inner
    return "unknown"


def vram_probe(stop_event, samples):
    """Sample nvidia-smi every 100 ms until stopped. Silent if unavailable."""
    while not stop_event.is_set():
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=4)
            value = out.stdout.strip().splitlines()
            if value:
                samples.append(int(value[0]))
        except Exception:
            return
        stop_event.wait(0.1)


# ------------------------------------------------------------------ prompts

def words_text(seed, count):
    """`count` words from the vocabulary, deterministic for a given seed."""
    rng = random.Random(seed)
    return " ".join(rng.choice(VOCAB) for _ in range(count))


def build_prompt(shared_seed, shared_words, tail_seed, tail_words):
    """A prompt in two halves.

    The halves are separate so that a caller can keep one of them identical
    across requests and vary the other. Identical text is what the engine's
    prefix cache can reuse; a different tail is what makes the request new work.
    """
    # Both markers are always present, even when a section is empty. Otherwise
    # the 0% cell would have a different shape from the others -- three words
    # shorter, and systematically so -- and D2 would be comparing a prompt with
    # a slightly different prompt.
    shared = words_text(shared_seed, shared_words) if shared_words > 0 else ""
    tail = words_text(tail_seed, tail_words) if tail_words > 0 else ""
    return "\n\n".join(["Section A. " + shared,
                        "Section B. " + tail,
                        "Reply with one short sentence."])


# ------------------------------------------------------------------ running

class Session:
    """One measurement session against one engine."""

    def __init__(self, engine, url, model, out, repetitions, wait, verbose=True):
        self.engine = engine
        self.url = url.rstrip("/")
        self.model = model
        self.out = out
        self.repetitions = repetitions
        self.wait = wait
        self.verbose = verbose
        self.version = engine_version(engine, self.url)
        self.rows = []
        self.started = time.strftime("%Y-%m-%dT%H:%M:%S")

    # ---- one request

    def request(self, prompt, stream, inject_usage, max_tokens=64, temperature=0.0):
        """Send one request and return a row, or a row marked as discarded."""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": bool(stream),
        }
        if inject_usage:
            # The flag the collection proxy used to add. Whether asking for
            # telemetry changes the telemetry is exactly what D1 tests.
            payload["stream_options"] = {"include_usage": True}

        stop = threading.Event()
        samples = []
        sampler = threading.Thread(target=vram_probe, args=(stop, samples), daemon=True)
        sampler.start()

        started = time.perf_counter()
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "engine": self.engine, "version": self.version, "model": self.model}
        error = None
        usage = None
        client_ttft = None
        client_total = None
        completion = None

        try:
            if stream:
                first, last, chunks, usage, t0 = stream_json(self.url + "/v1/chat/completions", payload)
                client_total = (last - t0) if last else None
                client_ttft = (first - t0) if first else None
                completion = chunks or None
            else:
                status, body, raw = post_json(self.url + "/v1/chat/completions", payload)
                if status != 200:
                    error = "http %s: %s" % (status, raw[:120])
                elif isinstance(body, dict):
                    usage = body.get("usage")
                    choices = body.get("choices") or []
                    completion = len(choices[0].get("message", {}).get("content", "").split()) if choices else None
        except Exception as exc:
            error = "%s: %s" % (type(exc).__name__, exc)

        client_total = client_total or (time.perf_counter() - started)
        stop.set()
        sampler.join(timeout=1)

        row.update(_from_usage(usage))
        row["client_total_s"] = round(client_total, 4)
        row["client_ttft_s"] = round(client_ttft, 4) if client_ttft is not None else None
        # The client's own view of the generation rate, available even when the
        # engine publishes nothing. It uses the engine's token count over the
        # window the client observed -- the count is the engine's, the window is
        # ours, and neither alone would be a measurement.
        window = (client_total - client_ttft) if (client_ttft is not None and client_total) else None
        tokens_out = row.get("completion_tokens")
        row["client_generation_tps"] = (round(tokens_out / window, 1)
                                        if (window and window > 0.05 and tokens_out) else None)
        row["client_pieces"] = completion
        row["peak_vram_mib"] = max(samples) if samples else None
        row["stream"] = bool(stream)
        row["injected"] = bool(inject_usage)
        row["discarded"] = bool(error)
        row["reason"] = error
        return row

    # ---- warm-up

    def warm_up(self, rounds=8, tolerance=0.05):
        """Nothing is recorded until five consecutive requests agree.

        The first requests of a session pay for a cold model, cold kernels and a
        GPU that has not reached its clocks. They are not measurements, they are
        the cost of starting.
        """
        if self.verbose:
            print("  warming up (nothing is recorded yet)", flush=True)
        recent = []
        for i in range(rounds):
            row = self.request(build_prompt(1, 200, 1000 + i, 200), stream=True,
                               inject_usage=True, max_tokens=32)
            if row["discarded"]:
                if self.verbose:
                    print("    %d: %s" % (i + 1, row["reason"]), flush=True)
                continue
            speed = _generation_speed(row)
            if speed:
                recent.append(speed)
            if self.verbose:
                print("    %d: %s" % (i + 1, ("%.0f tok/s" % speed) if speed else "no speed"), flush=True)
            if len(recent) >= 5:
                last5 = recent[-5:]
                if max(last5) - min(last5) <= tolerance * statistics.median(last5):
                    return True
        return len(recent) >= 5

    # ---- record

    def keep(self, row, experiment, cell, repetition):
        row["experiment"] = experiment
        row["cell"] = cell
        row["repetition"] = repetition
        self.rows.append(row)
        if self.out:
            with open(self.out, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def sleep(self):
        if self.wait:
            time.sleep(self.wait)


def _from_usage(usage):
    """The engine's own numbers, and the window they imply.

    `prompt_ts` divides uncached tokens by a window that the source code calls
    time to first token. Inverting it recovers that window, which is the only
    way to see the fixed cost at all.
    """
    if not isinstance(usage, dict):
        return {"prompt_tokens": None, "cached_tokens": None, "uncached": None,
                "reported_tps": None, "engine_ttft_s": None,
                "completion_tokens": None, "generation_tps": None}
    prompt_tokens = usage.get("prompt_tokens")
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    reported = usage.get("prompt_tokens_per_sec")
    uncached = None
    engine_ttft = None
    if prompt_tokens is not None and cached is not None:
        uncached = prompt_tokens - cached
    if uncached and reported:
        engine_ttft = uncached / reported
    return {
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached,
        "uncached": uncached,
        "reported_tps": reported,
        "engine_ttft_s": round(engine_ttft, 4) if engine_ttft else None,
        "completion_tokens": usage.get("completion_tokens"),
        "generation_tps": usage.get("completion_tokens_per_sec"),
    }


def _generation_speed(row):
    """The engine's rate if it publishes one, otherwise ours.

    The warm-up has to settle on every engine. Building it on the engine's own
    number meant it could never settle against Ollama, which publishes no
    timing at all -- eight requests, eight 'no speed', and the session started
    without a warm-up it had actually waited for.
    """
    return row.get("generation_tps") or row.get("client_generation_tps")


# ------------------------------------------------------------- experiments

def experiment_d1(session, words):
    """Four cells, same length, same client, same session.

    The text is fresh in every request, so the engine's prefix cache cannot
    quietly turn one cell into a repeat of another. That is verified afterwards
    by looking at `cached_tokens`, not assumed.
    """
    cells = [("stream+inject", True, True), ("stream", True, False),
             ("inject", False, True), ("plain", False, False)]
    for repetition in range(1, session.repetitions + 1):
        for name, stream, inject in cells:
            seed = 100_000 + repetition * 97 + hash(name) % 1000
            prompt = build_prompt(seed, words, seed + 500_000, 60)
            row = session.request(prompt, stream=stream, inject_usage=inject)
            row = session.keep(row, "d1", name, repetition)
            if session.verbose:
                print("    %-14s rep %d  %s" % (name, repetition, _summary(row)), flush=True)
            session.sleep()


def experiment_d2(session, words, fractions):
    """A fixed prefix of length L, with a varying fraction already cached.

    The shared part is identical across requests, which is the only thing the
    engine can reuse. What we ask for is a request; what the engine reports in
    `cached_tokens` is the measurement.
    """
    shared_seed = 42_000
    for repetition in range(1, session.repetitions + 1):
        for fraction in fractions:
            shared = int(words * fraction)
            tail = words - shared
            # A fresh tail seed every time, so the new part is genuinely new.
            prompt = build_prompt(shared_seed, shared, 700_000 + repetition * 31 + int(fraction * 100), tail)
            row = session.request(prompt, stream=True, inject_usage=True)
            row["asked_fraction"] = fraction
            row = session.keep(row, "d2", "cache=%d%%" % round(fraction * 100), repetition)
            if session.verbose:
                got = row.get("cached_tokens")
                total = row.get("prompt_tokens")
                actual = (got / total) if (got is not None and total) else None
                print("    asked %3d%%  got %s  %s" % (
                    round(fraction * 100),
                    ("%3.0f%%" % (actual * 100)) if actual is not None else "  ?",
                    _summary(row)), flush=True)
            session.sleep()


def experiment_d3(session, words):
    """The same four cells as D1, on whatever engine this session is pointed at.

    D3 is D1 repeated per engine. Running the same code against every engine in
    one session is what makes the comparison a comparison: different sessions
    have different intercepts, as the 2 October data shows.
    """
    experiment_d1(session, words)


def _summary(row):
    if row["discarded"]:
        return "DISCARDED  %s" % row["reason"]
    return "prompt=%s cached=%s ttft=%s s  engine=%s tok/s" % (
        row["prompt_tokens"], row["cached_tokens"], row["engine_ttft_s"], row["reported_tps"])


# ---------------------------------------------------------------- reporting

def first_token(row):
    """The engine's window if it publishes one, otherwise the client's.

    Two engines taught this. TabbyAPI reports a rate from which the window can
    be recovered by inverting it. Ollama reports no timing at all, so there the
    only window is the one the client timed. Reporting "(no usable rows)" for a
    session that measured eight requests perfectly well would be the tool lying
    about its own work.
    """
    if row.get("engine_ttft_s") is not None:
        return row["engine_ttft_s"], "engine"
    if row.get("client_ttft_s") is not None:
        return row["client_ttft_s"], "client"
    return None, None


def report(rows, by="cell"):
    """Median and interval, never the mean: latency distributions have tails."""
    groups = {}
    for row in rows:
        if row["discarded"]:
            continue
        groups.setdefault(row.get(by) or "?", []).append(row)
    print()
    print("  %-16s %4s %11s %6s %9s %10s" % (by, "n", "first tok", "from", "uncached", "gen tok/s"))
    for name in sorted(groups):
        group = groups[name]
        measured = [first_token(r) for r in group]
        ttfts = [v for v, _ in measured if v is not None]
        # Which side measured it, when they agree about which side that is.
        sources = {s for v, s in measured if v is not None}
        source = sources.pop() if len(sources) == 1 else ("mixed" if sources else "-")
        unc = [r["uncached"] for r in group if r["uncached"]]
        gen = [r.get("generation_tps") or r.get("client_generation_tps") for r in group]
        gen = [g for g in gen if g]
        if not ttfts:
            print("  %-16s %4d  (no first-token measurement -- only possible for"
                  " a non-streaming request on an engine that reports nothing)" % (name, len(group)))
            continue
        lo, hi = min(ttfts), max(ttfts)
        print("  %-16s %4d %9.3f s %6s %9s %10s   [%.3f .. %.3f]" % (
            name, len(group), statistics.median(ttfts), source,
            ("%.0f" % statistics.median(unc)) if unc else "-",
            ("%.0f" % statistics.median(gen)) if gen else "-", lo, hi))
    dropped = [r for r in rows if r["discarded"]]
    if dropped:
        print()
        print("  discarded, with reasons (they are kept, not deleted):")
        for reason, count in sorted(_count(dropped, "reason").items(), key=lambda kv: -kv[1]):
            print("    %-58s %d" % (str(reason)[:58], count))


def _count(rows, key):
    out = {}
    for row in rows:
        out[row.get(key)] = out.get(row.get(key), 0) + 1
    return out


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiment", choices=["d1", "d2", "d3", "warmup"])
    ap.add_argument("--engine", default="tabbyapi", choices=sorted(ENGINES))
    ap.add_argument("--url", help="override the engine's default address")
    ap.add_argument("--model", required=False, help="the model name the engine knows")
    ap.add_argument("--words", type=int, default=4000,
                    help="words in the prompt, before the tail (a word is roughly a token)")
    ap.add_argument("--repetitions", type=int, default=5)
    ap.add_argument("--wait", type=float, default=0.0, help="seconds between requests")
    ap.add_argument("--out", help="JSONL to append to")
    ap.add_argument("--fractions", default="0,0.25,0.5,0.75,0.9,0.99",
                    help="for d2: the cached fractions to ask for")
    args = ap.parse_args()

    url = args.url or ENGINES[args.engine]["url"]
    model = args.model or _guess_model(url)
    if not model:
        print("  no model given and the engine did not name one: pass --model", file=sys.stderr)
        return 2

    out = args.out
    if out is None:
        out = str(ROOT / "data" / ("%s-%s.jsonl" % (time.strftime("%Y-%m-%d"), args.experiment)))
        print("  no --out given, writing to %s" % out)

    print()
    print("  LocBench — measuring")
    print("    engine    : %s at %s" % (args.engine, url))
    print("    version   : %s" % engine_version(args.engine, url))
    print("    model     : %s" % model)
    print("    experiment: %s" % args.experiment)
    print()

    session = Session(args.engine, url, model, out, args.repetitions, args.wait)
    if session.version == "unknown":
        print("  the engine did not report a version. It will be recorded as")
        print("  'unknown', which is honest and worse than a number -- an engine")
        print("  update moves these numbers, and the version is what tells you.")
        print()

    if not session.warm_up():
        print("  warm-up did not settle. Recording anyway, and saying so:")
        print("  every row will carry the reason.")

    if args.experiment == "warmup":
        print("\n  warm-up only, nothing recorded.")
        return 0

    if args.experiment == "d1":
        experiment_d1(session, args.words)
    elif args.experiment == "d3":
        experiment_d3(session, args.words)
    else:
        fractions = [float(f) for f in args.fractions.split(",") if f.strip()]
        experiment_d2(session, args.words, fractions)

    report(session.rows)
    print()
    print("  %d rows written to %s" % (len(session.rows), out))
    print("  next: python3 bench/analyze_log.py --log %s" % out)
    return 0


def _guess_model(url):
    status, body = get_json(url.rstrip("/") + "/v1/models")
    if status == 200 and isinstance(body, dict):
        data = body.get("data") or []
        if data and isinstance(data[0], dict):
            return data[0].get("id")
    return None


if __name__ == "__main__":
    sys.exit(main())
