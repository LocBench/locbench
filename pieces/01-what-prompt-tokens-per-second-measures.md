# What `prompt_tokens_per_sec` actually measures

Two local inference engines — llama.cpp and TabbyAPI — publish a number called
**prompt tokens per second**. I read the source of both. In both, it is this:

```
uncached_prompt_tokens / time_to_first_token
```

That is not the throughput of prompt processing. Time to first token contains
everything that happens between the start of the prefill and the emission of the
first token — including the parts that do not scale with how many tokens you
sent.

It matters because almost everyone compares this number across engines, across
quantizations and across versions, and almost nobody says at what prompt length.
A quantity that depends on prompt length more than on the machine is not a good
thing to compare.

Both engines are careful and honest. The code does what the code says, and the
numerator in both is the right one. The problem is the name:
`prompt_tokens_per_sec` is a throughput name for a latency measurement.

---

## 1. TabbyAPI, over exllamav3

`backends/exllamav3/model.py`, lines 1440–1447:

```python
prompt_tokens = result.get("prompt_tokens")
cached_tokens = round(result.get("cached_tokens"), 2)
prompt_time   = round(result.get("time_prefill"), 2)
prompt_ts = (
    "Indeterminate"
    if prompt_time == 0
    else round((prompt_tokens - cached_tokens) / prompt_time, 2)
)
```

So the numerator is the **uncached** tokens — good, that part is careful. The
denominator is `time_prefill`, which comes from exllamav3.

In exllamav3, that field is documented in `generator/generator.py`, line 498:

```
"time_prefill": float  - time to first token, in seconds
```

and computed in `generator/job.py`, line 760:

```python
self.time_prefill += self.time_first_token - self.time_first_prefill
```

**Time to first token.** Not "time spent prefilling".

Note that exllamav3 keeps three separate windows, which is exactly right:

```python
self.time_enqueued += self.time_first_prefill - self.time_enqueue
self.time_prefill += self.time_first_token - self.time_first_prefill
self.time_generate += self.time_last_token - self.time_first_token
```

In order: the queue wait, the time to the first token, and the rest. Queueing is
not inside `time_prefill`, and `time_generate` starts *after* the first token. So
the three do not overlap — but the metric is built on the middle one, which is a
latency window, and its name says throughput.

## 2. llama.cpp

In `tools/server/server-common.h` the slot statistics track cached and processed
prompt tokens separately:

```cpp
uint64_t n_prompt_cached    = 0;
uint64_t n_prompt_processed = 0;
```

The window and the metric:

```cpp
double t_prompt_ms() const {
    if (t_prompt_last == 0) {
        return 0.0; // the prompt is not processed yet
    }
    return (t_prompt_last - t_start) / 1000.0;
}

double n_prompt_tps() const {
    const double t_ms = t_prompt_ms();
    return t_ms > 0.0 ? 1e3 / t_ms * n_prompt_processed : 0.0;
}
```

Now, when does the window open and close? The comments answer it.

`tools/server/server-context.cpp`, line 3122 — the window **opens** when the slot
picks up the prompt:

```cpp
slot.stats.update_prompt_start();
slot.state = SLOT_STATE_PROCESSING_PROMPT;
```

And at `tools/server/server-context.cpp:3844-3850` the window **closes** — and
the comment right there is explicit about why the measurement is taken at that
point:

```cpp
common_sampler_accept(slot.smpl.get(), id, true);

// here we have synchronized the llama_context (due to the sampling above), so we can do time measurement
const int64_t t_now = ggml_time_us();

slot.stats.n_gen += 1;

if (slot.stats.n_gen == 1) {
    slot.stats.update_prompt_last();
```

The window closes **after the first token has been sampled and the context
synchronized**. That is time to first token, with the sampling and the
synchronisation included.

Same definition as TabbyAPI. Two independent implementations, in two languages,
for two different engines, arrived at the same formula:

```
uncached_tokens / time_to_first_token
```

---

## 3. Why this makes the number incomparable to itself

Model time to first token as a fixed part plus a part that scales with the
tokens actually computed:

```
T(n) = a + n / r
```

where `n` is the uncached prompt tokens, `r` is the real prefill throughput, and
`a` is whatever else lives in the window. Then what the engine reports is

```
reported(n) = n / T(n)
```

which is not `r`. It approaches `r` as `n` grows, and collapses toward zero as
`n` shrinks. On the data below — `a = 0.447 s`, `r = 943 tok/s`:

| uncached prompt tokens | engine reports | actual time |
|---|---|---|
| 200 | 303 tok/s | 0.66 s |
| 1,000 | 664 tok/s | 1.51 s |
| 10,000 | 905 tok/s | 11.0 s |
| 30,000 | 930 tok/s | 32.3 s |

The machine never changed. Everything else did.

This is why a benchmark at 200-token prompts and a benchmark at 30,000-token
prompts can disagree by a factor of three while both being honest. It is also why
a number you published last week may not reproduce today: your client changed how
much of the prompt was already in cache, and nothing tells you.

### What to publish instead

A rate on its own hides both the length and the fixed cost, so it cannot be
compared to anything. Two things can:

- **the pair** — `uncached_tokens` next to the time. Two machines measured at the
  same length can be put side by side, and the difference is real
- **the slope** — measure at two lengths and take the difference. The fixed cost
  cancels, and what is left is a throughput that does not depend on the window

If you publish a rate anyway, put the uncached token count next to it, and say
whether the prompt was cached. That single number decides which of the two
quantities you are actually quoting, and without it the reader has no way to tell.

---

## 4. What I measured

From 98 real requests through a logging proxy in front of TabbyAPI (EXL3,
`qwen3.8-27b-4.0bpw` and `-uncensored-4.0bpw`, one RTX 3090). 87 of them carried
a usable `usage` block; the other 11 are 2 failed requests (HTTP 503) and 9
responses with no usage at all.

Inverting the formula above to recover the engine's own window, and fitting the
87 points:

```
time_to_first_token = 0.447 s + uncached_tokens / 943 tok/s      R² = 0.953
```

The fixed cost is not the cache. A cached token costs **0.009 ms** — effectively
nothing — and adding the cached-token count to the model moves R² by 0.0013. The
cost is per request, not per token re-read.

### The part I cannot establish

These requests were not collected to answer this question. They are real usage,
and real usage has structure that a controlled experiment would have removed.
Splitting them reveals the problem:

| group | n | median uncached | median cached fraction | fit |
|---|---|---|---|---|
| streaming | 56 | 802 | 0.93 | **0.752 s + n/980** · R²=0.947 |
| non-streaming | 31 | 19 | 0.00 | 0.114 s · R²=0.449 |

The non-streaming group never exceeds 872 uncached tokens, so its intercept is
extrapolated from an empty region — that number is not measured, it is invented
by the fit. And the streaming group is entirely one client, which is also the only
one that did not send `stream_options.include_usage`.

So: **streaming, the proxy's injection of that flag, and the client are the same
partition of the data.** Three explanations, and this dataset cannot separate
them. Within the streaming traffic the fixed cost is real and large — 0.75 s,
R²=0.947, over uncached lengths from 13 to 9,746. *What causes it* is an open
question, and it is the next thing to measure.

The magnitude is provisional. The definition is not — that part comes from the
source, and holds regardless of what the fixed cost turns out to be.

---

## 5. What I did not check

- **Ollama** — its documentation describes `prompt_eval_duration` as "time to
  evaluate the uncached prompt tokens", which sounds closer to a pure prefill
  window, and lists a separate `prompt_eval_cached_count`. But the docs are
  ambiguous about whether `prompt_eval_count` includes cached tokens, and I did
  not read the source. **I am not claiming anything about Ollama here.**
- **LM Studio** — closed source.
- **vLLM, SGLang** — not examined.

Two engines verified from source is what this piece rests on. If a third turns out
to use a different window, that is an interesting result and I would like to know.

---

## 6. Reproduce this

Raw data, the script that produced every number above, and its tests are in the
repository. The analysis prints its own limits:

```bash
python3 bench/analyze_log.py --log data/2026-09-usage.jsonl
```

The fit was verified against an independent implementation (the closed form for
simple linear regression) and agrees to 3.9·10⁻¹⁶.

## 7. A correction

The first version of these numbers, published in the protocol a few hours before
this piece, said:

```
0.81 s + uncached / 987 tok/s, R² = 0.953, 49 points
```

The R² was right. The intercept, the slope and the count were not, and the model
attribution was wrong — 90 of the 98 requests are the `uncensored` variant, not
the base model. I had transcribed the fit by hand without re-running it, which is
the way measurement benches lie: not a wrong calculation, a wrong memory of one.

The numbers above come from the command in section 6.
