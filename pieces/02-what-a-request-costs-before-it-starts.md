# What an engine charges you before it does any work

The first piece ended with a measurement it could not explain. On 98 real
requests through a proxy in front of TabbyAPI, the prompt window fitted

```
time_to_first_token = 0.447 s + uncached_tokens / 943 tok/s
```

and the fixed cost — the 0.447 s, the part that does not depend on how much you
sent — could not be attributed. It showed up in the streaming requests (0.752 s)
and not measurably in the ones that were not (0.114 s), but the two groups did
not overlap in length, one of them was a single client, and that client was the
only one that did not ask for telemetry. Three explanations, one dataset, no way
to separate them.

This is the controlled version. The answer is that the cost belongs to the
engine, and that engines differ by a factor of three.

---

## 1. Four cells, four lengths

The design is from the protocol, D1. The same prompt length, sent four ways —
streaming or not, crossed with the telemetry flag present or not — always from
the same measuring client, so the client is controlled by construction.

One length is not enough, and this is the part the first attempt got wrong. At a
single length, a cell with a larger fixed cost and a cell with a slower
throughput look the same: both take longer. Only by walking several lengths does
the intercept separate from the slope.

So each cell was measured at four lengths, five times each, and fitted
separately.

**TabbyAPI**, EXL3, `qwen3.8-27b-4.0bpw`, one RTX 3090:

| cell | fixed cost | throughput | R² |
|---|---|---|---|
| non-streaming, no flag | 0.179 s | 1133 tok/s | 0.9959 |
| non-streaming, with `stream_options` | 0.176 s | 1130 tok/s | 0.9957 |
| streaming, with `stream_options` | 0.174 s | 1124 tok/s | 0.9955 |

**The three intercepts are 5 milliseconds apart.** The streaming does not add a
fixed cost. The telemetry flag does not add one. Whatever the 0.18 s is, it is
there whichever way the request is made.

**llama.cpp**, same model family, `qwen3.8-27b-q4km.gguf`:

| cell | fixed cost | throughput | R² |
|---|---|---|---|
| non-streaming, no flag | 0.094 s | 1101 tok/s | 0.9999 |
| non-streaming, with the flag | 0.099 s | 1107 tok/s | 0.9999 |
| streaming, with the flag | 0.093 s | 1102 tok/s | 0.9999 |
| streaming, no flag | 0.100 s | 1106 tok/s | 0.9999 |

**Seven milliseconds apart, across all four.** llama.cpp reports its timings
whether or not the flag is sent, so here the fourth cell — streaming without
`stream_options`, the one cell that could not be measured at all on TabbyAPI —
has an engine number too, and it agrees with the rest.

The telemetry flag is innocent. So is streaming. The fixed cost is the engine's.

---

## 2. The cache cannot be imposed, and it is free anyway

D2 asks a different question: is the fixed cost per request or per token
re-read? The way to find out is to hold the prompt fixed and vary how much of it
is already in the cache.

The protocol is careful about the wording here, and running it shows why. **You
do not impose the cache, you ask for it and read back what happened.** The
engine reports `cached_tokens`, and that number — not the one requested — is the
measurement.

What came back:

| fraction asked for | times the cache engaged | prompt window |
|---|---|---|
| 0% | 0 / 5 | 1.98 s |
| 25% | 0 / 5 | 1.96 s |
| 50% | 0 / 5 | 1.96 s |
| 75% | 0 / 5 | 1.96 s |
| 90% | 4 / 5 | 0.35 s |
| 99% | 5 / 5 | 0.35 s |

**Asked for a quarter, a half, three quarters of the prompt cached, the engine
cached nothing.** The threshold sits between 75% and 90% of a 2,024-token
prompt, somewhere around 1,500 tokens of shared prefix, and below it the request
is worth nothing to the cache. It also fails once in five at 90%, which is why
the protocol asks for the interval and not only the median: a single number here
would be a number that is right four times out of five.

The two ends give the answer to the question. The same 2,024-token prompt, fully
uncached, takes 1.98 s. With 1,792 of those tokens already cached it takes
0.35 s. The line from D1 predicts 1.965 s and 0.384 s for those two points, and
across all thirty requests of D2 it is never off by more than 0.035 s.

**The cached tokens are free.** If re-reading the prefix cost anything, the
cached point would sit above the prediction. It sits slightly below.

---

## 3. Three engines, one machine

Which leaves the question the first piece could not answer, and this time it can
be answered properly, because all three numbers come from the same instrument.
Each engine reports the window in its own way — llama.cpp gives `prompt_n` and
`prompt_ms` side by side, Ollama gives `prompt_eval_duration` in nanoseconds, and
TabbyAPI gives a rate that has to be inverted — but all three are the engine's
own clock. Nothing here is a client measuring a server.

| engine | fixed cost | throughput | R² |
|---|---|---|---|
| Ollama 0.34.4 | **0.058 s** | 1182 tok/s | 1.0000 |
| llama.cpp b427 | **0.095 s** | 1105 tok/s | 0.9999 |
| TabbyAPI / exllamav3 1.5.2 | **0.179 s** | 1133 tok/s | 0.9959 |

**The throughput is the same on all three**, within 7%. **The per-request cost
is not**: TabbyAPI charges three times what Ollama charges, for the same work on
the same card.

This is the result the first piece was reaching for and could not get. For
someone running one long conversation it does not matter. For an agent making
four hundred short calls to do one task, it is the difference between 23 seconds
of overhead and 71.

---

## 4. What this does to the first piece

The first piece published a fixed cost of **0.75 s** for the streaming traffic,
fitted over requests that had been collected by accident. The controlled
measurement says **0.18 s**, four times smaller, on the same engine and the same
card.

Both numbers are honest and they are not the same number. The opportunistic fit
was over real traffic from real clients, with prompts of unknown shape, a
different model (`qwen3.8-27b-uncensored-4.0bpw`, not the base), a cache that was
93% full on average, and two sessions a week apart. Every one of those is a
candidate explanation and this data cannot choose between them.

What it can say is the direction: **the opportunistic estimate was too high, and
the controlled one is lower.** That is the ordinary direction for this kind of
error, and it is the reason the first piece called its own number a hypothesis.

---

## 5. What was not done

- **LM Studio was not measured.** No model is installed for it on this machine,
  so there is no fourth row. This is not a choice, it is an absence.
- **The weights are not the same file.** TabbyAPI ran EXL3 at 4.0 bits per
  weight, llama.cpp and Ollama the same model as GGUF Q4_K_M. The protocol's
  rule is to compare at equal nominal parameters and quantization and to say so;
  this is that. A difference in fixed cost between engines running different
  files could belong to the files.
- **One machine, one card.** As always: a 3090, on this system, in these
  sessions. Repeating this on another machine is the experiment worth doing and
  it has not been done.
- **The client's clock and the engine's clock are different clocks.** Where an
  engine reports nothing — Ollama's OpenAI-compatible endpoint reports no timing
  at all — the client can still measure a first token, but that measurement
  includes the network and the arrival of the first chunk. The engine comparison
  above uses only engine clocks for exactly this reason. Mixing them would have
  produced a difference belonging to the instrument.

---

## 6. Reproduce this

Four commands, and the raw data for all of them is in the repository.

```bash
python3 bench/measure.py sweep --engine ollama --model qwen3.8-27b-64k \
    --lengths 300,1200,2000,4000 --repetitions 5 --out data/ollama.jsonl
python3 bench/compare_engines.py data/ollama.jsonl
python3 bench/analyze_d1.py data/2026-10-03-d1-tabbyapi.jsonl
python3 bench/analyze_d1.py data/2026-10-03-d1-llamacpp.jsonl
```

`bench/measure.py` records the engine version on every row, because an engine
update moves these numbers and without the version a regression and a
configuration change look identical. `bench/environment.sh` prints the rest of
the card.
