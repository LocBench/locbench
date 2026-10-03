# Post texts for piece 01

Ready to paste. Lengths are checked by `bin/verify_post.py`, against the
limits of each platform.

Both texts link the repository, so they go out **after** the repository is
public. The text is written to be pasted, not rewritten.

---

## r/LocalLLaMA

**Title:**

<!-- limit: 300 -- a Reddit post title -->

```
I read the source of llama.cpp and TabbyAPI: "prompt tokens per second" is uncached_tokens / time_to_first_token, not prompt throughput
```

**Body:**

```
Everyone compares "prompt tok/s" across engines, quantizations and versions.
Almost nobody says at what prompt length. I wanted to know what the number
actually is, so I read the source of two engines.

**TabbyAPI**, over exllamav3 — `backends/exllamav3/model.py:1442`:

    prompt_time = round(result.get("time_prefill"), 2)
    prompt_ts = (
        "Indeterminate"
        if prompt_time == 0
        else round((prompt_tokens - cached_tokens) / prompt_time, 2)
    )

Careful numerator: uncached tokens. But `time_prefill` comes from exllamav3,
where it is documented in `generator/generator.py:498` as:

    "time_prefill": float  - time to first token, in seconds

**llama.cpp** — `tools/server/server-common.h:442`:

    double n_prompt_tps() const {
        const double t_ms = t_prompt_ms();
        return t_ms > 0.0 ? 1e3 / t_ms * n_prompt_processed : 0.0;
    }

Also careful: `n_prompt_cached` and `n_prompt_processed` are tracked separately,
and the metric uses the processed ones. The window opens when the slot picks up
the prompt (`server-context.cpp:3122`) and closes after the first token is
sampled and the context synchronised. The comment in the source says exactly
that: "here we have synchronized the llama_context (due to the sampling above),
so we can do time measurement".

So both engines compute `uncached_tokens / time_to_first_token`. The numerator
is right in both. The denominator is a latency window, and the field is named
like a throughput.

**Why it matters.** If T(n) = a + n/r, then what the engine reports is n/T(n),
which is not r. It approaches r as the prompt grows and collapses as it shrinks.
Fitting 87 real requests through a logging proxy in front of TabbyAPI (one RTX
3090) gives a = 0.447 s, r = 943 tok/s, R² = 0.953:

| uncached tokens | reported | actual time |
|-----------------|----------|-------------|
| 200             | 303 tok/s| 0.66 s      |
| 1,000           | 664 tok/s| 1.51 s      |
| 10,000          | 905 tok/s| 11.0 s      |
| 30,000          | 930 tok/s| 32.3 s      |

Same machine. A benchmark at 200-token prompts and one at 30,000 can differ 3x
and both be honest. A number you published last week may not reproduce today,
because your client changed how much of the prompt was already cached, and
nothing tells you.

It is not the cache, by the way: a cached token costs 0.009 ms, and adding the
cached count to the model moves R² by 0.0013. The cost is per request.

**What I cannot say from this data.** The fixed cost shows up in the streaming
requests (0.752 s, n=56, R²=0.947) and not measurably in the non-streaming ones
(0.114 s, n=31) — but the non-streaming group never exceeds 872 uncached tokens,
so that intercept is extrapolated from an empty region, and the streaming group
is entirely one client, which is also the only one that did not send
`stream_options.include_usage`. Streaming, injection and client are the same
partition of the data. I cannot separate them yet. That is the next experiment.

**Not checked:** Ollama (its docs describe `prompt_eval_duration` as "time to
evaluate the uncached prompt tokens", which sounds different, but I did not read
the source and I am not claiming anything), LM Studio (closed source), vLLM,
SGLang. Two engines verified from source is what this rests on.

Raw data, the script that produces every number above, and the tests:
[REPO LINK]
```

---

## X

The number is the hook. This fits in 280 characters, link excluded.

<!-- limit: 280 -- an X post -->

```
The "prompt tok/s" that llama.cpp and TabbyAPI report is:

uncached_tokens / time_to_first_token

Time-to-first-token holds everything that doesn't scale with your prompt. At 200 tokens the same machine reports 3x less than at 30,000.
```

**And below it, as a reply to your own post** — so the main post stays readable:

<!-- limit: 280 -- an X reply -->

```
Both engines track cached and processed prompt tokens separately, and divide by the processed ones. The numerator is right. The field is named like a throughput and it measures a latency.
```

---

## GitHub

The repository "About" field, 350 characters:

<!-- limit: 350 -- the About field of a GitHub repository -->

```
A measurement bench for local LLM inference. One variable at a time, raw data published, limits declared. Every number comes with the command that produced it.
```
