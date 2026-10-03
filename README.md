# LocBench

**A measurement bench for local LLM inference — the numbers out front, the
method next to them.**

Local inference on the internet is full of opinions and poor in measurements.
People publish token/s without saying at what context length, with what cache
fraction, on which engine, at which version. Those numbers cannot be compared to
anything, not even to themselves a week later.

LocBench does the other thing: **one variable at a time, the environment
declared, the raw data published, and a section on what the measurement does not
control.**

## Where it starts

Read the source of two engines and you find the same thing.

TabbyAPI, over exllamav3 — `backends/exllamav3/model.py:1442-1447`:

```python
prompt_time = round(result.get("time_prefill"), 2)
prompt_ts = (
    "Indeterminate"
    if prompt_time == 0
    else round((prompt_tokens - cached_tokens) / prompt_time, 2)
)
```

and `time_prefill` is documented in exllamav3, `generator/generator.py:498`, as

```
"time_prefill": float  - time to first token, in seconds
```

llama.cpp computes the same quantity in `tools/server/server-common.h` — uncached
tokens over a window that opens when the slot picks up the prompt and closes once
the first token has been sampled and the context synchronised. The comment in the
source says why the measurement is taken there.

So the field everyone reads and compares, `prompt_tokens_per_sec`, is:

```
uncached_prompt_tokens / time_to_first_token
```

A latency window carrying a throughput name. On 98 real requests through a
logging proxy (87 usable, one RTX 3090):

```
time_to_first_token = 0.447 s + uncached_tokens / 943 tok/s        R² = 0.953
```

At 200 uncached tokens it reports **303 tok/s**. And that is not the end of it:
the data carries a confound that makes it a hypothesis rather than a measurement,
and the protocol says so before the numbers.

The whole story is in [`PROTOCOL.md`](PROTOCOL.md), together with the three
questions that turn that hypothesis into a measurement, or demolish it.

Published so far: [`pieces/`](pieces/) — starting with
[what `prompt_tokens_per_sec` actually measures](pieces/01-what-prompt-tokens-per-second-measures.md).

## Layout

```
PROTOCOL.md            what we measure, how, and what we do NOT control
bench/analyze_log.py    redoes the analysis from the raw data, limits included
bin/verify_piece.py    the gate: citations, quoted code and numbers in a piece
bin/verify_post.py     post texts against the platform character limits
data/                    the raw JSONL, one line per request, committed
tests/                   the arithmetic and the two gates, verified
pieces/                   the published pieces, and the posts that go with them
```

Redo everything the protocol claims, from zero:

```bash
python3 bench/analyze_log.py --log data/2026-09-usage.jsonl
python3 -m pytest tests/ -q
```

## The engines

Ollama · llama.cpp · LM Studio · EXL3 (TabbyAPI), on the same machine.

## The rules

1. **One variable at a time.** Change two and you cannot tell which caused the
   difference
2. **Publish the median, not the mean**, with the interval
3. **Discarded measurements are recorded**, with the reason: the ones that
   vanish without explanation are how a measurement bench lies
4. **Everything is redone with one command**, from the raw data
5. **A comparison uses one clock.** An engine's own reported window is a
   cross-check, never the source: the four engines do not time the same
   interval, and two of them publish no timing at all. Ranking engines means
   timing every one of them with the client, in streaming, where that clock
   exists

## Licence

Code is [MIT](LICENSE). The measurements in `data/` are
[CC BY 4.0](LICENSE-DATA) — reuse them, redo them, build on them; just say where
they came from. A measurement nobody may reuse is a measurement nobody can check,
and being checkable is the whole claim.

## Status

The protocol is written, the three controlled experiments (D1, D2, D3) have been
run on four engines, and every number in the two published pieces is recomputed
from the committed data by `bin/verify_piece.py`.

The method changed while doing it, and that is the most useful thing here: **the
engine's own reported window is not one instrument read four times.** Over
identical streamed requests, llama.cpp's leaves 63 ms of each request untimed
and TabbyAPI's 128. So the ranking column is the client's clock, over streamed
requests, where one clock times one interval for every engine — and the engine's
own number is kept beside it as the cross-check it always was.

What is not done is in the pieces, item by item, rather than in a footnote:
one machine, one card, one model, and prompts that are still not anyone's
real workload.

The piece published so far is in [`pieces/`](pieces/).

> Everything here is in English: this file, the protocol, the pieces, the commit
> messages, the file and directory names, the analysis output and the CSV column
> names. Nothing is left in another language for a reader to stumble into.
