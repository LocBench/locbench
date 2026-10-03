# LocBench — measurement protocol

This document states **what we measure, how, and what we declare we do not
control**. It takes ten minutes to read, and it is the part that makes the rest
credible: a number without a method is not a measurement, it is an opinion with
digits.

---

## 1. The starting point: a number that does not mean what it looks like

### 1.1 The definition — a fact about the code, not about the data

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

The numerator is the **uncached** tokens, and that part is careful.
The denominator, `time_prefill`, is what exllamav3 documents in
`generator/generator.py:498` as

```
"time_prefill": float  - time to first token, in seconds
```

llama.cpp computes the same quantity in `tools/server/server-common.h`: uncached
tokens — it tracks `n_prompt_cached` and `n_prompt_processed` separately and
divides by the latter — over a window that opens when the slot picks up the
prompt (`tools/server/server-context.cpp:3122`) and closes once the first token
has been sampled and the context synchronised (`tools/server/server-context.cpp:3844-3850`).
The comment in the source says why the measurement is taken at that point.

So the field named `prompt_tokens_per_sec`, the one everyone reads and compares,
is:

```
uncached_prompt_tokens / time_to_first_token
```

If that window contains a cost that does not depend on the tokens, the cost is
spread over the few new tokens and the reported speed drops. This holds for
anyone reading that field, regardless of the data that follows: it is a property
of the code.

### 1.2 What the data says — September 2026

98 real requests logged by `tabby-usage-proxy.py` in front of TabbyAPI (EXL3, one
RTX 3090). **87** carry a usable `usage` block; the other 11 are 2 failed
requests (HTTP 503) and 9 responses with no usage at all.

Recovering the engine's own window by inverting the definition above, and fitting
the 87:

```
time_to_first_token = 0.447 s + uncached_tokens / 943 tok/s        R² = 0.953
```

| uncached tokens | the metric reports | actual time |
|---|---|---|
| 200 | 303 tok/s | 0.66 s |
| 1,000 | 664 tok/s | 1.51 s |
| 10,000 | 905 tok/s | 11.0 s |
| 30,000 | 930 tok/s | 32.3 s |

**The number everyone publishes and compares depends on how little work the
request had.** At 200 tokens it reports a third of the truth.

### 1.3 Why the magnitude is provisional

Those 87 requests are not one population: they are **two**, and they do not
overlap in length.

| group | n | uncached (median) | cached fraction | fixed cost |
|---|---|---|---|---|
| streaming | 56 | 802 | 0.93 | **0.752 s + n/980** · R²=0.947 |
| non-streaming | 31 | 19 | 0.00 | 0.114 s · R²=0.449 |

The non-streaming group **never** exceeds 872 uncached tokens: its intercept is
extrapolated from an empty region, not measured. And the streaming group is
entirely one client (OpenCode), which is also the only one that did not send
`stream_options.include_usage` — so **streaming, injection and client are the
same partition of the data.**

**The honest conclusion:** within the streaming traffic the fixed cost is real and
large — 0.75 s, R²=0.947, over uncached lengths from 13 to 9,746. *What causes
it* — the streaming, the injection, or the shape of OpenCode's requests — this
data does not say. That is question D1.

One hypothesis killed along the way, and it is worth saying: **it is not the
cache.** A cached token costs 0.009 ms, and adding `cached_tokens` to the model
moves R² by 0.0013. The cost is per request, not per token re-read.

The field that makes all of this visible is `cached_tokens`: without it you read
"570 tok/s" and you cannot tell why it does not add up.

**And this data was not collected to answer this question.** It is opportunistic:
real use, one machine, no controls. A good fit on uncontrolled data is a
**hypothesis**. The three questions below exist to turn it into a measurement —
or to demolish it.

---

## 2. The three questions

### D1 — Is the fixed cost the streaming, the injection, or the client?

The opportunistic data has a three-way confound, and it does not resolve by
looking: whoever sends streaming does not send `stream_options`, whoever does not
send streaming does send it, and the two sets are different clients.

**How it is settled:** the same prompt, **at the same length**, sent in all four
combinations, always **from the same measuring client** — so the client is
controlled by construction:

| | without `stream_options` | with `stream_options` |
|---|---|---|
| **streaming** | (a) | (b) |
| **non-streaming** | (c) | (d) |

- fixed cost in (a) and (b) but not in (c) and (d) → it is the **streaming**
- fixed cost in (b) and (d) but not in (a) and (c) → it is the **injection**
- fixed cost the same in all four → it is the **shape of the request**, not how
  the telemetry was asked for

**What would falsify it:** the same fixed cost in all four cells. In that case the
cost is simply the engine's, and the analysis of the opportunistic data was
right.

**The proxy already has a partial answer:** the number under analysis is computed
by TabbyAPI, not by the proxy — so the proxy cannot *add* time to the count. It
can change it, though, if the flag it injects changes how the engine measures.
That is exactly (a) against (b), and it is why this experiment matters even to
people who do not run a proxy.

**The constraint:** all four cells must be measured at a fixed length, or we
repeat the error this protocol exists to avoid.

### D2 — Does the cache, deliberately varied, confirm the line?

In the data the cached fraction is *suffered*, not chosen: it depends on what the
client was doing — median 0.93 in streaming, 0.00 outside. It is a variable we
observed, not one we set.

**A clarification for anyone redoing this experiment:** you do not *impose* the
cache, you **ask for it**. Send a request with a long prefix `L`, then a second
with the same prefix plus a new tail, and **read back** `cached_tokens`: if it
says what you expected, the imposition worked and the time can be read; if it
says something else, the engine did its own thing and the measurement is void.
The gap between what we ask for and what we get is itself a datum, even when it
is wrong.

**How it is settled:** the same prompt of fixed length `L`, repeated while varying
the fraction already cached — 0%, 25%, 50%, 75%, 90%, 99% — everything else held
fixed, **streaming fixed** (the only group that, from §1.3, has the fixed cost).

**What we are looking for:** in the opportunistic data a cached token costs
0.009 ms — nothing — and putting it in the model moves R² by 0.0013. If the
experiment confirms that the intercept does not depend on the cached fraction,
the cost really is per **request**. And that difference matters: a tax per call
and a tax per token re-read are paid in opposite ways.

**What would falsify it:** time that is non-linear in the uncached tokens, or an
intercept that grows with the cached fraction.

### D3 — Do the other three engines have the same fixed cost?

This is the question that decides the title of the long piece.

- If **all** of them have a fixed cost, the conclusion is: *prefill metrics from
  local engines are not comparable to each other, nor to themselves*.
- If **only TabbyAPI** has it, the conclusion is stronger and more useful:
  *TabbyAPI pays 0.75 s per request that the others do not pay*, and for an agent
  making many short calls that is a tax you only see by measuring it.

Those are two different pieces, and we do not yet know which one gets written.

**How it is settled:** the same model, the same quantization where possible, the
same card, the same prompts, across **Ollama** (11434), **llama.cpp** (8090),
**LM Studio** (1234), **EXL3/TabbyAPI** (8091).

**The honest constraint:** the same weights are not available for every engine in
the same format. Where they are not, we say so, and the comparison is made at
equal *nominal parameters and quantization*, not equal files.

**A warning that comes from the data in §1.3:** in the September log the two
models present have very different intercepts — 98 ms for `qwen3.8-27b-4.0bpw`
(n=8), 488 ms for the `uncensored` one (n=79). It would look as if the model
matters. But the first ran in one session and the second in another, and with n=8
against n=79 they cannot be told apart. **Engine comparisons must be made inside
one session**, or you are measuring the time, not the engine.

---

## 3. The environment, declared

Every published number carries this card. Without it, it is worth nothing.

| | |
|---|---|
| GPU | NVIDIA RTX 3090, 24,576 MiB, driver 595.99.02 |
| CPU | Intel Core Ultra 7 265KF, 20 threads |
| RAM | 62 GiB |
| OS | Nobara 44 (Fedora), kernel 7.2.6 |
| Engines | Ollama 0.34.4 · llama.cpp b11256 · LM Studio · TabbyAPI/EXL3 |
| Reference model | `qwen3.8-27b-4.0bpw` (where available) |

**The data in §1.2 does not come from the reference model.** It is 98 requests
from real use: 90 on `qwen3.8-27b-uncensored-4.0bpw`, 8 on `qwen3.8-27b-4.0bpw`,
collected in two different sessions. The reference model above is the one used
**from now on**, in the controlled experiments — not the one that produced the
numbers in section 1.

**The driver and engine versions are recorded at every measurement session.** An
update can move the numbers, and without the version there is no way to tell what
the difference should be attributed to.

---

## 4. The metrics, defined one by one

The point of all of it: **every metric has an operational definition**, not a
generic name. If a metric cannot be defined unambiguously, it is not published.

| metric | operational definition |
|---|---|
| **time to first token (TTFT)** | from the start of the prompt window to the first sampled token — what the engines call prefill time |
| **reported prompt rate** | `uncached_tokens / TTFT` — what the engine declares, **where it declares anything** (see below) |
| **true prompt throughput** | the slope of the time-vs-token line, at fixed cache |
| **fixed cost** | the intercept of that same line, in seconds per request |
| **generation** | `completion_tokens / generation_time` |
| **peak VRAM** | `nvidia-smi` sampled at 10 Hz during the request |
| **MTP acceptance** | `mtp_accepted / (mtp_accepted + mtp_rejected)` |

**Generation is always measured separately from the prompt.** A number that mixes
the two says nothing.

**Prompt length is quoted in tokens, never in words.** A word is not a unit of
work. Measured on this bench, the same word count is **1.3x to 1.6x** as many
tokens in real prose as in the fixed vocabulary, and **up to 40% more** between
two passages of prose of the same length. A benchmark that states its prompt
length in words is stating a number that varies by half between two prompts it
is treating as equal — and the fit below is over tokens, because that is the
count the engine reports.

**Not every engine publishes a rate, and that is part of the result.** TabbyAPI
does, and its field can be inverted to recover the window. Ollama's
OpenAI-compatible endpoint publishes token counts and **no timing at all** —
`prompt_tokens_per_sec` is simply not there — so on that engine the window can
only be measured by the client. The measurement client therefore always times
the window itself and treats the engine's number as a cross-check where one
exists, rather than as the source. A comparison across engines has to say which
of the two it is quoting, because for one of them there is no choice.

**And the two are not the same interval — by different amounts in different
engines.** Measured on identical streaming requests, llama.cpp's reported window
leaves **63 ms** of each request untimed and TabbyAPI's leaves **128 ms**: the
first stops when the prompt has been evaluated, the second when the first token
has been sampled, and neither covers getting the bytes out. So "the engine's own
clock" is not one instrument read four times. It is four instruments. Subtracting
one engine's intercept from another's charges the difference between two
stopwatches to the engine.

That is why the rule below is a rule and not a preference. **A ranking of engines
is built on the client's clock**, over streamed requests, where the same code
times the same interval for every engine. The engine's own number is kept and
published as what it is: a cross-check that says how much of each request happens
inside the part of the engine that chose to report.

Note that the first two rows are the correction this protocol owes to itself: the
field the engines call "prompt tokens per second" is the *reported prompt rate*,
and the denominator is a latency. The two are different quantities, and only one
of them is a throughput.

---

## 5. The procedure

1. **Warm-up discarded.** The first requests of every session are not recorded:
   the model loads, the kernels compile, the GPU ramps up. Recording starts only
   after five consecutive requests land within 5% of each other.
2. **Repetitions.** Every configuration is measured **at least five times**.
   Median and interval are published, **not the mean**: latency distributions have
   long tails, and the mean hides them.
3. **No external load.** No other process on the GPU. Whatever runs alongside
   (browser, compositor) is declared, even when it looks irrelevant.
4. **One factor at a time.** If two things change together, there is no telling
   which caused the difference — and that is the error made in the first analysis
   of this data, confounding cache with prompt length.
5. **Discarded measurements are recorded.** If a request falls outside 5% of the
   others, it is not deleted: it is annotated with the reason. Measurements that
   vanish without explanation are how measurement benches lie.

---

## 6. What we do NOT control, stated up front

- **One machine only.** The results hold for a 3090 on this system. They are not
  generalisable to other cards, and we do not pretend otherwise.
- **One GPU only.** No data on multi-GPU, or on what NVLink changes.
- **Temperature and clocks.** We do not pin them. We measure long sessions, where
  the card heats up: early measurements may be faster than late ones, and **this
  is a declared limit, not an error to be hidden**.
- **Run-to-run variance of the model.** We do not measure output quality, only
  speed. Two different answers cost different amounts, and that stays outside the
  bench.
- **The operating system's page cache on the weight files.** Not controlled.
- **The fixed cost may depend on the context length already allocated.** We
  measure at different contexts, but we do not claim to separate it from every
  other factor.

---

## 7. The data

Every recorded request is **one JSON line**, and it is published raw.

```json
{"ts":"2026-09-29T22:10:00","engine":"tabbyapi","version":"…","model":"…",
 "d1":{"imposed_cache":0.5,"prompt_tokens":8000,"cached_tokens":4000},
 "ttft_s":8.12,"reported_rate":493,"uncached_tokens":4000,
 "completion_tokens":200,"generation_time_s":2.6,"generation":77,
 "peak_vram_mib":21400,"repetition":3,"discarded":null}
```

**Published raw** means: the entire JSONL, plus a CSV with the columns the plots
need. Anyone who doubts a point can look at it. Anyone who wants to redo the fit
can redo it.

**Raw includes the parts that are not tidy.** The `client` field holds whatever
the client sent as its name, and some of the values are in Italian — `batteria`,
`prova-effort`, `salute-gpu` — because they came from throwaway test scripts
written in Italian. They are left exactly as they were captured. Renaming them
would make the file tidier and would no longer be the record of what ran; the
argument for publishing raw data at all is that the file is evidence, and
evidence that has been cleaned up is not evidence. Everything *around* the data
— documents, code, column names — is in English, and now so is the tool that
collects it.

**What is not published: the logging proxy that collected it.** It sits between
the client and the engine, adds `stream_options.include_usage` when a client
omits it — TabbyAPI returns a `usage` block only if asked — and writes one line
per request. It is a private tool, so *collection* is not reproducible from this
repository; the data it produced is committed in full, so the analysis is. This
is a declared limit, and it is one of the reasons the protocol insists on
publishing raw data rather than summaries.

**The scripts are in the repository**, and a published measurement is redone with
one command. The log is in `data/2026-09-usage.jsonl` — 98 lines from two
sessions, 19 and 29 September 2026, committed — and **everything in §1 comes out
of it**:

```bash
python3 bench/analyze_log.py --log data/2026-09-usage.jsonl
```

The same command also prints the limits section: whoever redoes the fit sees the
numbers and what the data cannot say, together.

---

## 8. What makes a result publishable

A result leaves LocBench only if it:

1. is **reproducible** — scripts and data in the repository, one command
2. carries **the formula or the mechanism**, not just the number
3. declares **what it does not control**
4. is **falsifiable**: it states what would disprove it

Fail any of the four and it stays an internal note.

Before publication, every piece passes `bin/verify_piece.py`: every citation
must point at a line that exists and is not empty, every quoted line of code must
actually be in the sources, and every number claimed must match the analysis
recomputed from the committed data. That gate is itself verified by mutating it
on purpose, to make sure its own tests notice.

---

## 9. The pieces

**Published:** [`pieces/01-what-prompt-tokens-per-second-measures.md`](pieces/01-what-prompt-tokens-per-second-measures.md)
— what `prompt_tokens_per_sec` actually measures, in both engines, from the
source.

What holds today, without further experiments:

1. the definition, read from the source: the field named `prompt_tokens_per_sec`
   divides uncached tokens by **time to first token**. A fact about the code, not
   a measurement, and true for anyone who reads it;
2. within the streaming traffic of those two sessions, a fixed cost of **0.75 s per
   request**, R²=0.947 over 56 requests from 13 to 9,746 uncached tokens;
3. a cached token costs **0.009 ms**: the cost is per request, not per token
   re-read;
4. **and the part that usually goes unwritten:** what this data does *not* say.
   Whether the cost belongs to streaming, to the injection or to the client
   cannot be established, because the three are the same partition of the log. A
   piece that declares its limit is stronger than one that has none.

The long piece is written **after** D1, D2 and D3. Measurements first, thesis
second. And if D1 says the cost is the **injection** — that *asking for telemetry
changes the telemetry* — the piece changes title and becomes something else,
probably more interesting.
