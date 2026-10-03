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
engine, that it varies by a factor of four across engines running the *same
weights*, and that five of the explanations one would reach for first are all
wrong.

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
fixed cost. The telemetry flag does not add one. Whatever the cost is, it is
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

The telemetry flag is innocent. So is streaming.

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

**The cached tokens are free.**

---

## 3. Four engines, three of them on one identical file

Which leaves the question the first piece could not answer, and this time it can
be answered properly, because every window here is the engine's own clock.
Nothing is a client measuring a server.

| engine | model | fixed cost | throughput | R² |
|---|---|---|---|---|
| Ollama 0.34.4 | `qwen3.8-27b-64k` | **0.058 s** | 1182 tok/s | 1.0000 |
| llama.cpp b427 | `qwen3.8-27b-llama` | **0.095 s** | 1105 tok/s | 0.9999 |
| LM Studio 69d945a | `uncensored@q4_k_m` | **0.228 s** | 714 tok/s | 0.9982 |
| TabbyAPI / exllamav3 | `qwen3.8-27b-4.0bpw` | 0.179 s | 1133 tok/s | 0.9959 |
| TabbyAPI / exllamav3 | `uncensored-4.0bpw` | 0.211 s | 1102 tok/s | 0.9938 |

**The first three rows are the same file.** Not the same model family — the same
bytes: `sha256 3445102e…`, 16,811 MB, loaded by three different engines. Same
weights, same card, same machine, and the per-request cost differs by a factor
of four, from 0.058 s to 0.228 s. The throughput differs too, by 1.7×, which is
not what this piece set out to measure and may be the more useful number of the
two.

**The last two rows are one engine on two different models**, 0.179 s and
0.211 s. That difference is 32 ms, on two runs made an hour apart, and it is not
enough to claim that the weights matter. It is enough to say they might, and
that the four engines here do not separate the engine from the model it is
running. The claim this piece will stand behind is the narrower one.

For someone running one long conversation none of this matters. For an agent
making four hundred short calls to do one task, it is 23 seconds of overhead
against 91.

---

## 4. Five explanations, all wrong

A fixed per-request cost of a tenth of a second invites an obvious reply: it is
obviously *something*. So each candidate was measured rather than argued about.

| candidate | how it was tested | result |
|---|---|---|
| the streaming | the four cells of D1 | **out** — intercepts 5 ms apart |
| the telemetry flag | the same four cells | **out** — same |
| re-reading the cached prefix | the 0% and 90% cells of D2 | **out** — cached tokens are free |
| preparing to generate | sweeping `--max-tokens` at 1, 64 and 256, everything else fixed | **out** — see below |
| the client's own clock | the engine's timings used throughout | **out** — the window is the engine's |

The generation test is the one that needed a new knob, and it is worth spelling
out, because the shape of the argument is the shape of all of them. If the
engine spends that time setting up to write, then letting it write more should
cost more:

| tokens allowed | fixed cost | throughput | R² |
|---|---|---|---|
| 1 | 0.212 s | 1124 tok/s | 0.9967 |
| 64 | 0.211 s | 1102 tok/s | 0.9938 |
| 256 | 0.192 s | 1152 tok/s | 0.9949 |

Allowing a model to write **256 times more** moves the fixed cost by 20
milliseconds, in the wrong direction and inside the noise. Generation setup is
not it.

**What is left is the part of the engine that receives a request and hands it to
the model.** Tokenisation, template rendering, slot allocation, whatever the
engine does at its own front door before the first forward pass begins. This
data does not separate those, and it would take someone who knows one of these
engines from the inside — or a much more invasive set of experiments — to do it.
Five explanations are excluded. The sixth is where the cost lives, and it is
named rather than measured.

---

## 5. What this does to the first piece

The first piece published a fixed cost of **0.75 s** for the streaming traffic,
fitted over requests that had been collected by accident. The controlled
measurement says **0.18 s** for the same engine on the base model, and 0.13 s on
the uncensored one, four to six times smaller.

Both numbers are honest and they are not the same number. The opportunistic fit
was over real traffic from real clients, with prompts of unknown shape, a cache
93% full on average, and two sessions a week apart. Every one of those is a
candidate explanation and this data cannot choose between them.

What it can say is the direction: **the opportunistic estimate was too high, and
the controlled one is lower.** That is the ordinary direction for this kind of
error, and it is why the first piece called its own number a hypothesis.

---

## 6. What was not done

- **The five engines do not run under identical settings.** Each was left on its
  own defaults — context length, batching, speculation — because that is what a
  user gets. LM Studio in particular was given a 64k context and reached 714
  tok/s where llama.cpp on the same file reached 1105. That gap is a fact about
  the default configurations, not necessarily about the engines underneath, and
  untangling it is another piece.
- **One machine, one card.** A 3090, on this system, in these sessions.
  Repeating this elsewhere remains the experiment worth doing.
- **The engines were measured one at a time**, because two do not fit on this
  card together. "In the same session" here means within the same hour, with the
  environment card captured alongside; it is not the same as interleaved.
- **The tool could not read every engine the same way.** Four engines, four
  shapes for the same number:

  | engine | where its window lives |
  |---|---|
  | TabbyAPI | `prompt_tokens_per_sec`, a rate, to be inverted |
  | llama.cpp | `prompt_n` and `prompt_ms`, two numbers to divide |
  | Ollama | `prompt_eval_duration`, nanoseconds, **native API only** |
  | LM Studio | `time_to_first_token`, ready, **native API only** |

  Two of the four publish no timing at all on the OpenAI-compatible endpoint
  that most clients actually use. Anyone comparing engines has been comparing
  whichever of these four they happened to be able to read.

---

## 7. Reproduce this

The raw data for everything above is in the repository, and the comparisons are
one command each.

```bash
# one file per engine and model. A wildcard would pool the control runs, and
# listing a subset gives a slightly different line -- which is the point of
# naming the files rather than globbing them.
python3 bench/compare_engines.py \
    data/2026-10-03-sweep-ollama.jsonl data/2026-10-03-sweep-llamacpp.jsonl \
    data/2026-10-03-d1-llamacpp.jsonl data/2026-10-03-sweep-lmstudio.jsonl \
    data/2026-10-03-sweep-tabbyapi.jsonl data/2026-10-03-d1-tabbyapi.jsonl
python3 bench/analyze_d1.py data/2026-10-03-d1-tabbyapi.jsonl
python3 bench/measure.py sweep --engine ollama --model qwen3.8-27b-64k \
    --lengths 300,1200,2000,4000 --repetitions 5 --out data/ollama.jsonl
```

`bench/measure.py` records the engine version on every row, because an engine
update moves these numbers and without the version a regression and a
configuration change look identical. `bench/environment.sh` prints the rest of
the card.
